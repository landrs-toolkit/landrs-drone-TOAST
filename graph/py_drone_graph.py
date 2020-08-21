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

# my imports
from graph.py_drone_graph_core import py_drone_graph_core, LANDRS, LDLBASE
from graph.py_drone_graph_core import SOSA, QUDT_UNIT, QUDT, GEO, RDFG, \
        ontology_landrs, ontology_myID
from graph.py_drone_graph_store import py_drone_graph_store
from config.config_graph_shacl import config_graph_shacl

# namespaces from rdflib
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
    PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SSN, TIME, \
    VOID, XMLNS, XSD

# setup logging ################################################################
logger = logging.getLogger(__name__)

################################################################################
# Class to house rdf graph functions for drone
# inherits from,
#  py_drone_graph_core
#  py_drone_graph_store
################################################################################


class py_drone_graph(py_drone_graph_core, py_drone_graph_store, config_graph_shacl):
    '''
    sample instantiation,
    d_graph = ldg.py_drone_graph(ontology_myID, load_graph_file)
    where,
    1. ontology_myID, uuid for this drone
      e.g. "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="
    2. load_graph_file, turtle file or (folder) for db initialization
      e.g. base.ttl

    has the following sections,
    1. interaction with ld.landrs.org to copy sub-graphs to drone
    3. sparql endpoint
    4. api endpoint support functions
    '''

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
        # call the super class py_drone_graph_core
        super().__init__(ontology_myid, graph_dict, my_base, my_host_name)

    ##################################################
    # find or create a graph for ObservationCollection
    ##################################################

    def observation_collection_graph(self, obs_col, collection_type, dataset):
        '''
        Args:
            uuid (str): uuid of observation collection to associate with graph
        Returns:
            graph: graph object
        '''
        # graph created as dataset?
        if dataset:
            # try to get context
            g_context = self.g.get_context(dataset)
            if g_context:
                return g_context

            else:
                # create graph
                gn = Graph(self.store, identifier=dataset)

                # add the obs_col to graph
                gn.add((obs_col, RDF.type, collection_type))
                # should get labeled during config

                logger.info('graph created: %s.' % str(dataset))

                # return graph
                return gn

        # else fall back to original method, for testing
        # strip uri part
        obs_col_uuid = None
        pos = obs_col.rfind('/')
        if pos > 0:
            obs_col_uuid = obs_col[pos + 1:len(obs_col)]

        if not obs_col_uuid:
            logger.info('graph creation failed.')
            return None

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
        the_graph_node = self.BASE.term(the_graph_name)
        graph = self.g.get_context(self.BASE.term(self.graph_name))
        graph.add((the_graph_node, RDF.type, RDFG.Graph))
        graph.add((the_graph_node, RDFS.label, Literal(obs_col_uuid)))

        # create graph
        gn = Graph(self.store, identifier=the_graph_node)

        # add the obs_col to graph
        gn.add((self.BASE.term(obs_col_uuid), RDF.type, collection_type))

        logger.info('graph created: %s.' % the_graph_name)

        # return graph
        return gn

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
        if (self.BASE.term(ontology_myid), RDF.type, LANDRS.UAX) in self.g:
            print(ontology_myid, "is a", LANDRS.UAX)
        else:
            ret.update({"id a drone": "False", "status": "error"})
            return ret

        # lets look for components and sensors
        # get things that are part of my id
        for s, p, o in self.g.triples((None, LANDRS.isPartOf, self.BASE.term(ontology_myid))):
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
        if (self.BASE.term(node), None, None) in self.g:
            print("This graph contains triples about "+node)
            return False

        # query to find top level type
        q_type = ('SELECT * WHERE { '
                  '	<' + self.BASE.term(node) + '> a ?type .'
                  '	filter not exists {'
                  '    	?subtype ^a <' + self.BASE.term(node) + '> ;'
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
             '   <' + self.BASE.term(node) + '>  ?type ?attribute .'
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
        info = {"status": "done", "myType": self.BASE.term(node)}
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
        the_node = self.BASE.term(node)
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

    ####################################
    # get data store graphs to my drone
    ####################################
    def get_data_graphs(self):
        '''
        Returns:
           dict.: graph ids
        '''
        graphs = []

        # find the graphs in g1
        for s, p, o in self.g.triples((None, RDF.type, RDFG.Graph)):
            # check there is a label
            label = self.g.value(s, RDFS.label, None)
            if not label:
                label = self.g.value(s, DCTERMS.title, None)
            if label:
                # store
                graphs.append( {"graph": str(s), "label": str(label)} )
            else:
                # store
                graphs.append( {"graph": str(s), "label": str(s)} )

        # return graph info
        return {"graphs": graphs}

###########################################
# end of py_drone_graph class
###########################################
