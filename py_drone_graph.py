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
import rdflib
from rdflib.serializer import Serializer
from rdflib import plugin, Graph, Literal, URIRef
from rdflib.store import Store
from rdflib.plugins.sparql.processor import processUpdate
from SPARQLWrapper import SPARQLWrapper, JSON

#namespaces
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
                           PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SSN, TIME, \
                           VOID, XMLNS, XSD

#for some reason the predefined sosa: points to ssn: bug in rdflib? insufficient understanding of linked data?
#I will add my version here
SOSA = rdflib.Namespace('http://www.w3.org/ns/sosa/')

#namespaces not pre-defined
QUDT_UNIT = rdflib.Namespace('http://qudt.org/2.1/vocab/unit#')
QUDT = rdflib.Namespace('http://qudt.org/2.1/schema/qudt#')

#setup our namespaces
LANDRS = rdflib.Namespace('http://schema.landrs.org/schema/')
BASE = rdflib.Namespace('http://ld.landrs.org/id/')

# Defines ######################################################################
#things I need to know
# information can be queried on ld.landrs.org
ontology_landrs = 'http://ld.landrs.org/query'
#ontology_landrs_file = "ttl/base.ttl"
ontology_landrs_file_format = "ttl"

#db file
ontology_db = "landrs_test"
ontology_db_location = "db/landrs_test.sqlite"
ontology_db_file = "ttl/base.ttl"

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

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
    #class variables
    #################
    g = None                #graph
    Id = None               #local drone id
    files_loaded = False    #flag to prevent ontology reload

    # initialization and graph i/o #############################################
    #######################
    # class initialization
    #######################
    def __init__(self, ontology_myid, graph_dict):
        '''
        Args:
            ontology_myid (str):    uuid for this drone
            graph_dict (dict.):     configuration data
        '''
        # set base id
        self.Id = ontology_myid

        #load graph, include ttl to load if required
        self.setup_graph(graph_dict)

    ##########################
    #setup and load graph
    ##########################
    def setup_graph(self, graph_dict):
        '''
        Args:
            graph_dict (dict.):     configuration data
        '''
        #get config for graph name, physical db location and it's format
        #added extraction of load_graph_file
        if 'name' in graph_dict.keys():
            graph_name = graph_dict['name']
        else:
            graph_name = ontology_db
        if 'db_location' in graph_dict.keys():
            graph_location = graph_dict['db_location']
        else:
            graph_location = ontology_db_location
        if 'graph_file_format' in graph_dict.keys():
            graph_file_format = graph_dict['graph_file_format']
        else:
            graph_file_format = ontology_landrs_file_format
        if 'graph_file' in graph_dict.keys():
            load_graph_file = graph_dict['graph_file']
        else:
            load_graph_file = ontology_db_file

        #added file reload startegy
        if 'graph_file_reload' in graph_dict.keys():
            graph_file_reload = graph_dict['graph_file_reload']
        else:
            graph_file_reload = 'False'

        #does the db exist?
        reload_db = True
        if graph_file_reload == 'False' and os.path.isfile(graph_location):
            reload_db = False

        #vars
        ident = URIRef(graph_name)
        uri = Literal("sqlite:///%(here)s/%(loc)s" % {"here": os.getcwd(), "loc": graph_location})

        #create and load graph
        store = plugin.get("SQLAlchemy", Store)(identifier=ident)
        self.g = Graph(store, identifier=ident)
        self.g.open(uri, create=True)

        #add LANDRS and other namespaces, this converts the pythonized names to
        #something more readable
        self.g.namespace_manager.bind('landrs', LANDRS)
        self.g.namespace_manager.bind('sosa', SOSA)
        self.g.namespace_manager.bind('base', BASE)
        #self.g.namespace_manager.bind('qudt-unit-1-1', QUDT_UNIT)
        self.g.namespace_manager.bind('qudt-1-1', QUDT)

        #Load graph?
        if load_graph_file and not self.files_loaded and reload_db:
            #folder or file?
            if os.path.isdir(load_graph_file):

                #get the list of files
                files_in_graph_folder = os.walk(load_graph_file)
                print("Folder provided for import.")
                #loop
                for (dirpath, dirnames, filenames) in files_in_graph_folder:
                    for file in filenames:
                        file_path = os.path.join(dirpath, file)
                        #each file if turtle
                        if os.path.splitext(file_path)[-1].lower() == "." + graph_file_format:
                            if os.path.isfile(file_path):
                                print("file", file_path)
                                self.files_loaded = True
                                #load the individual file
                                self.g.load(file_path, format=graph_file_format)

            else:
                print("File provided for import.")
                if os.path.isfile(load_graph_file):
                    self.files_loaded = True
                    self.g.load(load_graph_file, format=graph_file_format)

    ###################################
    #save graph, returns a turtle file
    ###################################
    def save_graph(self, save_graph_file):
        '''
        Args:
            save_graph_file (str): turtle filename to save
        '''
        #save graph?
        if save_graph_file:
            self.g.serialize(destination=save_graph_file, format='turtle', base=BASE)

    # interaction with ld.landrs.org to copy sub-graphs to drone ###############

    #############################################################
    #function to copy instance graph ld.landrs.org if not exist
    #############################################################
    def copy_remote_graph(self, ontology_myid):
        '''
        Args:
            ontology_myid (str): drone uuid for graph to copy

        Returns:
           dict.: information on node copying
        '''
        #return dictionary
        ret = {}
        #try and copy
        if self.copy_remote_node(ontology_myid):
            print(ontology_myid, "copied")
            ret.update({ontology_myid: "drone"})
        else:
            ret.update({"copied drone": "False", "status": "error"})
            return ret

        #test that id is a drone if we successfully copied
        if (BASE.term(ontology_myid), RDF.type, LANDRS.UAX) in self.g:
            print(ontology_myid, "is a", LANDRS.UAX)
        else:
            ret.update({"id a drone": "False", "status": "error"})
            return ret

        #lets look for components and sensors
        #get things that are part of my id
        for s, p, o in self.g.triples((None, LANDRS.isPartOf, BASE.term(ontology_myid))):
            print("level 1 {}  {}".format(s, o))
            #copy
            if self.copy_remote_node(s):
                print(s, "copied")
                ret.update({s: "copied level 1"})

            #get the things connected to those
            for sp, pp, op in self.g.triples((None, LANDRS.isPartOf, s)):
                print("level 2 {}  {}".format(sp, op))
                #copy
                if self.copy_remote_node(sp):
                    print(sp, "copied")
                    ret.update({sp: "copied level 2"})

                #get the things hosted on those
                for sph, pph, oph in self.g.triples((sp, SOSA.hosts, None)):
                    print("sensors/actuators {}  {}".format(sph, oph))
                    #copy
                    if self.copy_remote_node(oph):
                        print(oph, "copied")
                        ret.update({oph: "copied sensor/actuator"})
        #flag success
        ret.update({"status": "copied"})
        return ret

    #############################################################
    #function to copy graph node from ld.landrs.org if not exist
    #############################################################
    def copy_remote_node(self, node):
        '''
        Args:
            node (str): uuid of node to copy

        Returns:
           Boolean: success/fail
        '''
        #test if node exists locally
        if (BASE.term(node), None, None) in self.g:
            print("This graph contains triples about "+node)
            return False

        #query to find top level type
        q_type = ('SELECT * WHERE { ' \
                 '	<' + BASE.term(node) + '> a ?type .' \
                 '	filter not exists {' \
                 '    	?subtype ^a <' + BASE.term(node) + '> ;' \
                 '        		<' + RDFS.subClassOf + '> ?type . ' \
                 '    	filter ( ?subtype != ?type )' \
                 '	}' \
                 '}')

        #set wrapper to talk to landrs
        spql = SPARQLWrapper(ontology_landrs)

        #lets try and get it from ld.landrs.org
        spql.setQuery(q_type)
        spql.setReturnFormat(JSON)

        try :
            ret = spql.query().convert()
            wresult = ret['results']['bindings']
        except :
            print("error")
            return False
        #return json.dumps(ret)

        #bail if no match
        if not wresult:
            print("Type does not exist on ld.landrs.org", node)
            return False

        #set my top level type
        myType = wresult[0]['type']['value']

        if not myType:
            print("Could not extract type for node", node)
            return False

        #find my node data
        q = ('SELECT ?type ?attribute ' \
                'WHERE { ' \
                '   <' + BASE.term(node) + '>  ?type ?attribute .' \
                '} ')

        #put data into graph
        spql.setQuery(q)
        spql.setReturnFormat(JSON)

        try :
            ret = spql.query().convert()
            wresult = ret['results']['bindings']
        except :
            ret = {"status": "error"}

        #we have the node and its type, get remaining data
        # loop over rows returned, check for info
        info = {"status": "done", "myType": BASE.term(node)}
        types = []
        attributes = []
        for values in wresult:
            #skip other definitions of type
            if RDF.type in values['type']['value']:
                continue
            #print("info",values[0],values[1])
            #store in dictionary
            info.update({values['type']['value'] : values['attribute']['value']})
            #put into values with correct type
            if values['type']['type'] == 'uri':
                types.append(URIRef(values['type']['value']))
            else:
                types.append(Literal(values['type']['value']))
            if values['attribute']['type'] == 'uri':
                attributes.append(URIRef(values['attribute']['value']))
            else:
                attributes.append(Literal(values['attribute']['value']))

        #create new node in graph
        the_node = BASE.term(node)
        self.g.add((the_node, RDF.type, URIRef(myType)))

        #add data
        for i in range(0, len(types)):
            self.g.add((the_node, types[i], attributes[i]))

        #done
        return True

    # sparql endpoint ##########################################################

    ##########################
    #run a sparql query
    ##########################
    def run_sql(self, query, type):
        '''
        Args:
            query (str): sparql query
            type (str):  insert/query type

        Returns:
           dict.: query result

        Raises:
            Exceptions on error
        '''
        #query
        if type == "insert":
            #we call this to update, either returns for success
            #or throws an exception (try block in calling code)
            processUpdate(self.g, query)
            ret = json.dumps({"status": "success"})
        else:
            result = self.g.query(query)
            # convert to JSON
            ret = result.serialize(format="json")

        #print("json",ret)
        #return
        return ret

    # api endpoint support functions ###########################################

    ##########################
    #get triples for an id
    ##########################
    def get_id_data(self, id):
        '''
        Args:
            id (str): uuid to query

        Returns:
           dict.: query result
        '''
        #dictionary
        id_data = {}

        #get id's triples
        for s, p, o in self.g.triples((BASE.term(id), None, None)):
            print("{} is a {}".format(p, o))
            id_data.update( {p : o} )

        #return info
        return id_data

    ##################################
    #get sensors attached to my drone
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
        #storage
        sensors = []
        #get things that are part of my drone
        for s, p, o in self.g.triples((None, LANDRS.isPartOf, BASE.term(self.Id))):
            print("level 1 {}  {}".format(s, o))
            #get the things connected to those
            for sp, pp, op in self.g.triples((None, LANDRS.isPartOf, s)):
                print("level 2 {}  {}".format(sp, op))
                #get the things hosted on those
                for sph, pph, oph in self.g.triples((sp, SOSA.hosts, None)):
                    print("sensors/actuators {}  {}".format(sph, oph))
                    #get the things that are sensors
                    for sphs, pphs, ophs in self.g.triples((oph, RDF.type, LANDRS.Sensor)):
                        print("sensors {}  {}".format(sphs, ophs))
                        sensors.append(sphs)

        #return info
        return sensors

    # data storage support functions ###########################################

    #################################################
    #store data for sensor, creates SOSA.Observation
    #################################################
    def store_data_point(self, collection_id, sensor_id, value, time_stamp):
        '''
        Args:
            collection_id (str):    uuid for observation collection
                                    '*' to create new
            sensor_id (str):        uuid for sensor to associate data
            value (str):            value to store
            time_stamp (str):       time stamp to store

        Returns:
           dict.: query result
        '''
        #add data to return
        ret = {"id": sensor_id, "value": value, "time_stamp": time_stamp}

        # check if collection exists
        # if collection_id is '*' then create a new one
        if collection_id != '*':
            if (BASE.term(collection_id), RDF.type, SOSA.ObservationCollection) in self.g:
                print(collection_id, "is a", SOSA.ObservationCollection)
            else:
                ret.update({"status": False})
                return ret

        #check it is a sensor
        if (BASE.term(sensor_id), RDF.type, LANDRS.Sensor) in self.g:
            print(sensor_id, "is a", LANDRS.Sensor)
        else:
            ret.update({"status": False})
            return ret

        #store data
        #new uuid
        id = base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode('utf-8')
        ret.update({"uuid": id})

        #create new node in graph
        the_node = BASE.term(id)
        self.g.add((the_node, RDF.type, SOSA.Observation))

        #add data
        self.g.add((the_node, SOSA.madeBySensor, BASE.term(sensor_id)))
        # sosa:hasResult
        self.g.add((the_node, SOSA.hasResult, Literal(QUDT.QuantityValue, datatype = RDF.type)))
        self.g.add((the_node, SOSA.hasResult, Literal(value, datatype = QUDT.numericValue)))
        self.g.add((the_node, SOSA.hasResult, Literal(QUDT_UNIT.PPM, datatype = QUDT.unit)))
        # sosa:resultTime
        self.g.add((the_node, SOSA.resultTime, Literal(XSD.dateTime, datatype = RDF.type)))
        self.g.add((the_node, SOSA.resultTime, Literal(time_stamp, datatype = XSD.dateTimeStamp)))
        #TODO: test to see if we need common value for collection
        #self.g.add((the_node, SOSA.hasFeatureOfInterest, Literal("house/134/kitchen")))

        # if collection_id is '*' then create a new one
        if collection_id == '*':
            #new uuid
            collection_id = base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode('utf-8')
            ret.update({"collection uuid": collection_id})

            #create new node in graph
            the_collection_node = BASE.term(collection_id)
            self.g.add((the_collection_node, RDF.type, SOSA.ObservationCollection))
            self.g.add((the_collection_node, RDFS.label, Literal("Drone data collection")))
            #TODO: test to see if we need common value for collection
            #self.g.add((the_collection_node, SOSA.hasFeatureOfInterest, Literal("house/134/kitchen")))

        #add data point id to collection
        the_collection_node = BASE.term(collection_id)
        self.g.add((the_collection_node, SOSA.hasMember, BASE.term(id)))

        #return success
        ret.update({"status": True})
        return ret

###########################################
#end of py_drone_graph class
###########################################
