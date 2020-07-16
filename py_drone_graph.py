'''
Graph Class for simple drone emulator that,
1) takes an id
2) queries ld.landers.org to find its configuration OR
2) Loads a set of ttl files and runs sparql queries locally
3) generates an API for access to sensor data
4) provides other functionality in support of Landrs development.

Chris Sweet 07/02/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

This code provides py_drone_graph, the class for acessing and manipulating
the rdf graph.
'''

# Imports ######################################################################
import json
import os
import base64
import uuid
import logging

# RDFLIB
import rdflib
from rdflib.serializer import Serializer
from rdflib import plugin, Graph, Literal, URIRef, BNode
from rdflib.store import Store
from rdflib.plugins.sparql.processor import processUpdate
from SPARQLWrapper import SPARQLWrapper, JSON
from rdflib.graph import Graph, ConjunctiveGraph

# namespaces
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
    PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SSN, TIME, \
    VOID, XMLNS, XSD

# for some reason the predefined sosa: points to ssn: bug in rdflib?
# insufficient understanding of linked data?
# I will add my version here
SOSA = rdflib.Namespace('http://www.w3.org/ns/sosa/')

# namespaces not pre-defined
QUDT_UNIT = rdflib.Namespace('http://qudt.org/2.1/vocab/unit#')
QUDT = rdflib.Namespace('http://qudt.org/2.1/schema/qudt#')
GEO = rdflib.Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
RDFG = rdflib.Namespace('http://www.w3.org/2004/03/trix/rdfg-1/')

# setup our namespaces
LANDRS = rdflib.Namespace('http://schema.landrs.org/schema/')
BASE = rdflib.Namespace('http://drone.landrs.org/id/')
LDLBASE = rdflib.Namespace('http://ld.landrs.org/id/')

# Defines ######################################################################
# things I need to know
# information can be queried on ld.landrs.org
ontology_landrs = 'http://ld.landrs.org/query'
#ontology_landrs_file = "ttl/base.ttl"
ontology_landrs_file_format = "ttl"

# db file
ontology_db = "landrs_test"
ontology_db_location = "db/landrs_test.sqlite"
ontology_db_file = "ttl/base.ttl"

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

# setup logging ################################################################
logger = logging.getLogger(__name__)

################################################################################
# Class to house rdf graph functions for drone
################################################################################


class py_drone_graph:
    '''
    sample instantiation,
    d_graph = ldg.py_drone_graph(ontology_myID, load_graph_file)
    where,
    1. ontology_myID, uuid for this drone
      e.g. "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="
    2. load_graph_file, turtle file or (folder) for db initialization
      e.g. base.ttl

    has the following sections,
    1. initialization and graph i/o
    2. interaction with ld.landrs.org to copy sub-graphs to drone
    3. sparql endpoint
    4. api endpoint support functions
    5. data storage support functions
    '''
    #################
    # class variables
    #################
    g = None  # graph
    Id = None  # local drone id
    files_loaded = False  # flag to prevent ontology reload
    my_host_name = None  # host_name

    # initialization and graph i/o #############################################
    #######################
    # class initialization
    #######################
    def __init__(self, ontology_myid, graph_dict, my_base, my_host_name):
        '''
        Args:
            ontology_myid (str):    uuid for this drone
            graph_dict (dict.):     configuration data
        '''
        global BASE

        # save hostname
        self.my_host_name = my_host_name + '/'

        # fix base
        BASE = rdflib.Namespace(my_base)

        # set base id
        self.Id = ontology_myid

        # load graph, include ttl to load if required
        self.setup_graph(graph_dict)

    ##########################
    # setup and load graph
    ##########################
    def setup_graph(self, graph_dict):
        '''
        Args:
            graph_dict (dict.):     configuration data
        '''
        # get config for graph name, physical db location and it's format
        # added extraction of load_graph_file
        self.graph_name = graph_dict.get('name', ontology_db)
        graph_location = graph_dict.get('db_location', ontology_db_location)
        graph_file_format = graph_dict.get(
            'file_format', ontology_landrs_file_format)
        load_graph_file = graph_dict.get('file', ontology_db_file)

        # added file reload startegy
        graph_file_reload = graph_dict.get('file_reload', 'False')

        # does the db exist?
        reload_db = True
        if graph_file_reload == 'False' and os.path.isfile(graph_location + '.sqlite'):
            reload_db = False

        # check any folders exist
        os.makedirs(os.path.dirname(graph_location), exist_ok=True)

        # store location
        uri = Literal("sqlite:///%(here)s/%(loc)s.sqlite" %
                      {"here": os.getcwd(), "loc": graph_location})

        # create store
        store_ident = URIRef('store_' + self.graph_name)
        self.store = plugin.get("SQLAlchemy", Store)(identifier=store_ident)

        # was self.g.open
        self.store.open(uri, create=True)

        # and ConjunctiveGraph
        self.g = ConjunctiveGraph(self.store)

        # vars for first graph context
        ident = BASE.term(self.graph_name)

        # create and load graph
        self.g1 = Graph(self.store, identifier=ident)

        # print graphs
        print("Graphs")
        for c in self.g.contexts():
            print("-- %s " % c)

        # add LANDRS and other namespaces, this converts the pythonized names to
        # something more readable
        self.g.namespace_manager.bind('landrs', LANDRS)
        self.g.namespace_manager.bind('sosa', SOSA)
        self.g.namespace_manager.bind('base', BASE)
        #self.g.namespace_manager.bind('qudt-unit-1-1', QUDT_UNIT)
        self.g.namespace_manager.bind('qudt-1-1', QUDT)
        self.g.namespace_manager.bind('geo', GEO)
        self.g.namespace_manager.bind('rdfg', RDFG)

        # Load graph?
        if load_graph_file and not self.files_loaded and reload_db:
            # folder or file?
            if os.path.isdir(load_graph_file):

                # get the list of files
                files_in_graph_folder = os.walk(load_graph_file)
                print("Folder provided for import.")
                # loop
                for (dirpath, dirnames, filenames) in files_in_graph_folder:
                    for file in filenames:
                        file_path = os.path.join(dirpath, file)
                        # each file if turtle
                        if os.path.splitext(file_path)[-1].lower() == "." + graph_file_format:
                            if os.path.isfile(file_path):
                                print("file", file_path)
                                self.files_loaded = True
                                # load the individual file
                                try:
                                    self.g1.load(
                                        file_path, format=graph_file_format, publicID=self.my_host_name)
                                except Exception as ex:
                                    print("Could not load graph file: " + str(ex))

            else:
                print("File provided for import.")
                if os.path.isfile(load_graph_file):
                    self.files_loaded = True
                    # load the file
                    try:
                        self.g1.load(load_graph_file, format=graph_file_format, publicID=self.my_host_name)
                    except Exception as ex:
                        print("Could not load graph file: " + str(ex))

    ##################################################
    # find or create a graph for ObservationCollection
    ##################################################

    def observation_collection_graph(self, obs_col_uuid):
        '''
        Args:
            uuid (str): uuid of observation collection to associate with graph
        Returns:
            graph: graph object
        '''
        # exist?
        for s, p, o in self.g1.triples((None, RDF.type, RDFG.Graph)):
            # check if graph matched collection
            if (s, RDFS.label, Literal(obs_col_uuid)) in self.g1:
                # found a match
                return self.g.get_context(s)

        # else get uuid
        graph_uuid = self.generate_uuid()

        # create new node in graph
        the_graph_name = graph_uuid
        the_graph_node = BASE.term(the_graph_name)
        graph = self.g.get_context(BASE.term(self.graph_name))
        graph.add((the_graph_node, RDF.type, RDFG.Graph))
        graph.add((the_graph_node, RDFS.label, Literal(obs_col_uuid)))

        # create graph
        gn = Graph(self.store, identifier=the_graph_node)
        logger.info('graph created: %s.' % the_graph_name)

        # return graph
        return gn

    #############
    # create uuid
    #############
    def generate_uuid(self):
        return base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode('utf-8')

    ###################################
    # save graph, returns a turtle file
    ###################################
    def save_graph(self, save_graph_file):
        '''
        Args:
            save_graph_file (str): turtle filename to save
        '''
        # save graph?
        if save_graph_file:
            # create folder if required
            os.makedirs(os.path.dirname(save_graph_file), exist_ok=True)
            # return the serialized graph
            self.g.serialize(destination=save_graph_file,
                             format='turtle', base=self.my_host_name)

    # interaction with ld.landrs.org to copy sub-graphs to drone ###############

    #############################################################
    # function to copy instance graph ld.landrs.org if not exist
    #############################################################
    def copy_remote_graph(self, ontology_myid):
        '''
        Args:
            ontology_myid (str): drone uuid for graph to copy

        Returns:
           dict.: information on node copying
        '''
        # return dictionary
        ret = {}
        # try and copy
        if self.copy_remote_node(ontology_myid):
            print(ontology_myid, "copied")
            ret.update({ontology_myid: "drone"})
        else:
            ret.update({"copied drone": "False", "status": "error"})
            return ret

        # test that id is a drone if we successfully copied
        if (BASE.term(ontology_myid), RDF.type, LANDRS.UAX) in self.g:
            print(ontology_myid, "is a", LANDRS.UAX)
        else:
            ret.update({"id a drone": "False", "status": "error"})
            return ret

        # lets look for components and sensors
        # get things that are part of my id
        for s, p, o in self.g.triples((None, LANDRS.isPartOf, BASE.term(ontology_myid))):
            print("level 1 {}  {}".format(s, o))
            # copy
            if self.copy_remote_node(s):
                print(s, "copied")
                ret.update({s: "copied level 1"})

            # get the things connected to those
            for sp, pp, op in self.g.triples((None, LANDRS.isPartOf, s)):
                print("level 2 {}  {}".format(sp, op))
                # copy
                if self.copy_remote_node(sp):
                    print(sp, "copied")
                    ret.update({sp: "copied level 2"})

                # get the things hosted on those
                for sph, pph, oph in self.g.triples((sp, SOSA.hosts, None)):
                    print("sensors/actuators {}  {}".format(sph, oph))
                    # copy
                    if self.copy_remote_node(oph):
                        print(oph, "copied")
                        ret.update({oph: "copied sensor/actuator"})
        # flag success
        ret.update({"status": "copied"})
        return ret

    #############################################################
    # function to copy graph node from ld.landrs.org if not exist
    #############################################################
    def copy_remote_node(self, node):
        '''
        Args:
            node (str): uuid of node to copy

        Returns:
           Boolean: success/fail
        '''
        # test if node exists locally
        if (BASE.term(node), None, None) in self.g:
            print("This graph contains triples about "+node)
            return False

        # query to find top level type
        q_type = ('SELECT * WHERE { '
                  '	<' + BASE.term(node) + '> a ?type .'
                  '	filter not exists {'
                  '    	?subtype ^a <' + BASE.term(node) + '> ;'
                  '        		<' + RDFS.subClassOf + '> ?type . '
                  '    	filter ( ?subtype != ?type )'
                  '	}'
                  '}')

        # set wrapper to talk to landrs
        spql = SPARQLWrapper(ontology_landrs)

        # lets try and get it from ld.landrs.org
        spql.setQuery(q_type)
        spql.setReturnFormat(JSON)

        try:
            ret = spql.query().convert()
            wresult = ret['results']['bindings']
        except:
            print("error")
            return False
        # return json.dumps(ret)

        # bail if no match
        if not wresult:
            print("Type does not exist on ld.landrs.org", node)
            return False

        # set my top level type
        myType = wresult[0]['type']['value']

        if not myType:
            print("Could not extract type for node", node)
            return False

        # find my node data
        q = ('SELECT ?type ?attribute '
             'WHERE { '
             '   <' + BASE.term(node) + '>  ?type ?attribute .'
             '} ')

        # put data into graph
        spql.setQuery(q)
        spql.setReturnFormat(JSON)

        try:
            ret = spql.query().convert()
            wresult = ret['results']['bindings']
        except:
            ret = {"status": "error"}

        # we have the node and its type, get remaining data
        # loop over rows returned, check for info
        info = {"status": "done", "myType": BASE.term(node)}
        types = []
        attributes = []
        for values in wresult:
            # skip other definitions of type
            if RDF.type in values['type']['value']:
                continue
            # print("info",values[0],values[1])
            #store in dictionary
            info.update(
                {values['type']['value']: values['attribute']['value']})
            # put into values with correct type
            if values['type']['type'] == 'uri':
                types.append(URIRef(values['type']['value']))
            else:
                types.append(Literal(values['type']['value']))
            if values['attribute']['type'] == 'uri':
                attributes.append(URIRef(values['attribute']['value']))
            else:
                attributes.append(Literal(values['attribute']['value']))

        # create new node in graph
        the_node = BASE.term(node)
        self.g.add((the_node, RDF.type, URIRef(myType)))

        # add data
        for i in range(0, len(types)):
            self.g.add((the_node, types[i], attributes[i]))

        # done
        return True

    # sparql endpoint ##########################################################

    ##########################
    # run a sparql query
    ##########################
    def run_sql(self, query, type, return_type):
        '''
        Args:
            query (str): sparql query
            type (str):  insert/query type

        Returns:
           dict.: query result

        Raises:
            Exceptions on error
        '''
        # set return
        ret_type = 'application/sparql-results+json'
        # query
        if type == "insert":
            # we call this to update, either returns for success
            # or throws an exception (try block in calling code)
            processUpdate(self.g, query)
            ret = json.dumps({"status": "success"})
        else:
            # run query for SELECT, ASK or now CONSTRUCT
            if 'DESCRIBE' in query:
                # get object
                actual_query = query.split('<', 1)[1].split('>')[0]
                print("describe", actual_query)
                node_graph = self.get_graph_with_node(URIRef(actual_query))
                ret_type = 'text/turtle'
                # return info
                return node_graph.serialize(format="turtle", base=self.my_host_name), ret_type

            # run query
            result = self.g.query(query)

            # check if CONSTRUCT as this returns a graph
            if result.type == 'CONSTRUCT':
                # test type
                if 'text/turtle' in return_type:
                    ret_type = 'text/turtle'
                    # convert graph to turtle
                    ret = result.serialize(format="turtle", base=self.my_host_name)
                else:
                    # convert graph to JSON
                    ret = self.graph_to_json(result.graph)
            else:
                # convert to JSON
                ret = result.serialize(format="json")

        # print("json",ret)
        # return
        return ret, ret_type

    # api endpoint support functions ###########################################

    ######################
    # dump graph as turtle
    ######################
    def dump_graph(self, id):
        graph = self.g.get_context(BASE.term(id))
        if graph:
            return graph.serialize(format="turtle", base=self.my_host_name)
        else:
            return None

    ######################
    # dump graph as turtle
    ######################
    def list_graphs(self):
        ret = '@prefix rdfg: <http://www.w3.org/2004/03/trix/rdfg-1/> .\n' + \
            '@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n' + \
            '@prefix rdflib: <http://rdflib.net/projects#> .\n\n'
        # loop over graphs and append
        for c in self.g.contexts():
            ret = ret + str(c) + '\n'

        # return it
        return ret

    ###########################################
    # find namespace for node from uuid
    # solves problem of having objects created
    # on ld.landrs.org OR the drone.
    # Also test existance.
    ###########################################
    def find_node_from_uuid(self, uuid, id_type=None):
        '''
        Args:
            uuid (str):    uuid to find

        Returns:
           URIRef: node associated with uuid
        '''
        # check drone definition exists and if it is local or on ld.landrs.org
        id_node = LDLBASE.term(uuid)
        if not (id_node, RDF.type, id_type) in self.g:
            # from myself?
            id_node = BASE.term(uuid)
            if not (id_node, RDF.type, id_type) in self.g:
                # return info
                return None

        # if here, exists and node resolved
        return id_node

    ##########################################
    # recursive drill down through blank nodes
    ##########################################
    def blank_node_recursion(self, blnk, grph):
        # check blank
        if isinstance(blnk, BNode):
            # get nodes
            for sn, pn, on in self.g.triples((blnk, None, None)):
                grph.add((sn, pn, on))
                # recurse
                self.blank_node_recursion(on, grph)

    #########################################
    # get graph with node and its blank nodes
    #########################################
    def get_graph_with_node(self, id_node):
        '''
        Args:
            id_node (str): node id to put into graph

        Returns:
           graph: graph of id_node
        '''
        node_graph = Graph()
        # get id's triples
        for s, p, o in self.g.triples((id_node, None, None)):
            node_graph.add((s, p, o))
            # if associated blank not, get its tripples
            self.blank_node_recursion(o, node_graph)

        # return the new graph
        return node_graph

    ##########################
    # get triples for an id
    ##########################
    def get_id_data(self, id, json=False):
        '''
        Args:
            id (str): uuid to query

        Returns:
           dict.: query result
        '''
        # dictionary
        id_data = {}

        # is the id a local graph?
        # if so return the graph as turtle
        g = self.g.get_context(BASE.term(id))
        if g:
            # return info
            return g.serialize(format="turtle", base=self.my_host_name)  # id_data

        # check drone definition exists and if it is local or on ld.landrs.org
        # we will support ld.landrs.org ids due to potential connectivity problems
        id_node = self.find_node_from_uuid(id)
        if not id_node:
            # return info
            return {"status": "id: " + id + " not found."}

        if not json:
            node_graph = self.get_graph_with_node(id_node)

            # return info
            return node_graph.serialize(format="turtle", base=self.my_host_name)  # id_data
        else:
            # get id's triples
            for s, p, o in self.g.triples((id_node, None, None)):
                print("{} is a {}".format(p, o))
                id_data.update({p: o})

            # return json here
            return id_data

    ##################################
    # get sensors attached to my drone
    ##################################
    def get_attached_sensors(self):
        '''
        Sparql original query,
        '  ?sub <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.landrs.org/sch ema/Sensor> .'
        '  ?h <http://www.w3.org/ns/sosa/hosts> ?sub .'
        '  ?h <http://schema.landrs.org/schema/isPartOf> ?x .'
        '  ?x <http://schema.landrs.org/schema/isPartOf> <' + ontology_prefix + ontology_myid + '> .'

        Returns:
           dict.: query result for sosa:Sensor ids
        '''
        # storage
        sensors = []

        # check drone definition exists and if it is local or on ld.landrs.org
        sensor_id_node = self.find_node_from_uuid(self.Id, LANDRS.UAV)
        if not sensor_id_node:
            # return info
            return sensors

        # get things that are part of my drone
        for s, p, o in self.g.triples((None, LANDRS.isPartOf, sensor_id_node)):
            print("level 1 {}  {}".format(s, o))
            # get the things connected to those
            for sp, pp, op in self.g.triples((None, LANDRS.isPartOf, s)):
                print("level 2 {}  {}".format(sp, op))
                # get the things hosted on those
                for sph, pph, oph in self.g.triples((sp, SOSA.hosts, None)):
                    print("sensors/actuators {}  {}".format(sph, oph))
                    # get the things that are sensors
                    for sphs, pphs, ophs in self.g.triples((oph, RDF.type, LANDRS.Sensor)):
                        print("sensors {}  {}".format(sphs, ophs))
                        sensors.append(sphs)

        # return info
        return sensors

    # data storage support functions ###########################################

    #################################################
    # store data for sensor, creates SOSA.Observation
    #################################################
    def store_data_point(self, collection_id, sensor_id, values):
        '''
        Args:
            collection_id (str):    uuid for observation collection
                                    '*' to create new
            sensor_id (str):        uuid for sensor to associate data
            value (str):            dictionary values to store
            time_stamp (str):       time stamp to store

        Returns:
           dict.: query result
        '''
        # figure out what data we have to store
        type = ''
        value = '0'
        # check type
        if 'type' in values.keys():
            if values['type'] == 'co2':
                value = values['co2']
                type = 'co2'
            if values['type'] == 'gps':
                value = values['alt']
                type = 'gps'
        else:
            ret = {"status": False}
            return

        # check timestamp
        if 'time_stamp' in values.keys():
            time_stamp = values['time_stamp']
        else:
            ret = {"status": False}
            return

        # add data to return
        ret = {"id": sensor_id, "value": value,
               "time_stamp": time_stamp, "type": values['type']}

        # check it is a sensor, from ld.landres.org?
        sensor_id_node = self.find_node_from_uuid(sensor_id, LANDRS.Sensor)
        if not sensor_id_node:
            ret.update({"status": False, "error": "sensor not found."})
            return ret

        # check if collection exists
        # if collection_id is '*' then create a new one
        collection_id_node = LDLBASE.term(
            collection_id)  # from ld.landres.org?
        # create?
        if collection_id != '*':
            collection_id_node = self.find_node_from_uuid(
                collection_id, SOSA.ObservationCollection)
            if not collection_id_node:
                ret.update({"status": False, "error": "collection not found."})
                return ret

            # if we get here find or create graph to store
            graph = self.observation_collection_graph(collection_id)
        else:  # collection_id is '*'
            # find existing graph associated with obs. coll. or create
            # new uuid
            collection_id = self.generate_uuid()
            ret.update({"collection uuid": collection_id})

            # create new node in graph
            collection_id_node = BASE.term(collection_id)
            # TODO: do we nned to add to both graphs?
            self.g1.add((collection_id_node, RDF.type,
                         SOSA.ObservationCollection))
            self.g1.add((collection_id_node, RDFS.label,
                         Literal("Drone data collection")))
            # TODO: test to see if we need common value for collection
            #self.g.add((collection_id_node, SOSA.hasFeatureOfInterest, Literal("house/134/kitchen")))
            # create new graph and get context
            # self.g.get_context(self.create_new_graph(collection_id))
            graph = self.observation_collection_graph(collection_id)
            graph.add((collection_id_node, RDF.type,
                       SOSA.ObservationCollection))
            graph.add((collection_id_node, RDFS.label,
                       Literal("Drone data collection")))

        # store data
        # new uuid
        id = self.generate_uuid()
        ret.update({"uuid": id})

        # create new node in graph
        the_node = BASE.term(id)
        graph.add((the_node, RDF.type, SOSA.Observation))

        # add data
        graph.add((the_node, SOSA.madeBySensor, sensor_id_node))
        # sosa:hasResult
        hasResult = BNode()
        # gps data?
        if type == 'gps':
            graph.add((hasResult, RDF.type, GEO.Point))
            graph.add((hasResult, GEO.lat, Literal(
                values['lat'], datatype=XSD.decimal)))
            graph.add((hasResult, GEO.long, Literal(
                values['lon'], datatype=XSD.decimal)))
            graph.add((hasResult, GEO.alt, Literal(
                values['alt'], datatype=XSD.decimal)))
        else:
            # then co2
            graph.add((hasResult, RDF.type, QUDT.QuantityValue))
            graph.add((hasResult, QUDT.numericValue, Literal(value)))
            graph.add((hasResult, QUDT.unit, QUDT_UNIT.PPM))

        graph.add((the_node, SOSA.hasResult, hasResult))
        # self.g.add((the_node, SOSA.hasResult, Literal(QUDT.QuantityValue, datatype = RDF.type)))
        # self.g.add((the_node, SOSA.hasResult, Literal(value, datatype = QUDT.numericValue)))
        # self.g.add((the_node, SOSA.hasResult, Literal(QUDT_UNIT.PPM, datatype = QUDT.unit)))
        # sosa:resultTime
        resultTime = BNode()
        graph.add((resultTime, RDF.type, XSD.dateTime))
        graph.add((resultTime, XSD.dateTimeStamp, Literal(time_stamp)))
        graph.add((the_node, SOSA.resultTime, resultTime))
        # self.g.add((the_node, SOSA.resultTime, Literal(XSD.dateTime, datatype = RDF.type)))
        # self.g.add((the_node, SOSA.resultTime, Literal(time_stamp, datatype = XSD.dateTimeStamp)))
        # TODO: test to see if we need common value for collection
        #self.g.add((the_node, SOSA.hasFeatureOfInterest, Literal("house/134/kitchen")))

        # add data point id to collection
        graph.add((collection_id_node, SOSA.hasMember, the_node))

        # return success
        ret.update({"status": True})
        return ret

    ##################################
    # routine to convert graph to json
    ##################################
    def graph_to_json(self, g):
        """
        Pass in a rdflib.Graph and get back a chunk of JSON using
        the Talis JSON serialization for RDF:
        http://n2.talis.com/wiki/RDF_JSON_Specification
        """
        g_json = {}

        # go through all the triples in the graph
        for s, p, o in g:

            # initialize property dictionary if we've got a new subject
            if not s in g_json.keys():
                # if not json.has_key(s):
                g_json[s] = {}

            # initialize object list if we've got a new subject-property combo
            if not p in g_json[s].keys():
                # if not json[s].has_key(p):
                g_json[s][p] = []

            # determine the value dictionary for the object
            v = {'value': o}
            if isinstance(o, rdflib.URIRef):
                v['type'] = 'uri'
            elif isinstance(o, rdflib.BNode):
                v['type'] = 'bnode'
            elif isinstance(o, rdflib.Literal):
                v['type'] = 'literal'
                if o.language:
                    v['lang'] = o.language
                if o.datatype:
                    v['datatype'] = unicode(o.datatype)

            # add the triple
            g_json[s][p].append(v)

        return json.dumps(g_json, indent=4)

###########################################
# end of py_drone_graph class
###########################################
