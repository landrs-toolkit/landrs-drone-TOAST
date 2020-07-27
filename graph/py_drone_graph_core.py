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
# Class to house rdf graph core functions for drone
################################################################################


class py_drone_graph_core:
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
    2. utility functions like generating uuid etc.
    '''
    #################
    # class variables
    #################
    g = None  # graph
    Id = None  # local drone id
    files_loaded = False  # flag to prevent ontology reload
    my_host_name = None  # host_name
    BASE = None # base namespace

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
        # save hostname
        self.my_host_name = my_host_name + '/'

        # fix base
        self.BASE = rdflib.Namespace(my_base)

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
        ident = self.BASE.term(self.graph_name)

        # create and load graph
        self.g1 = Graph(self.store, identifier=ident)

        # vars for first graph context
        ident2 = self.BASE.term(self.graph_name + '_shape')

        # create and load graph
        self.g2 = Graph(self.store, identifier=ident2)

        # print graphs
        print("Graphs")
        for c in self.g.contexts():
            print("-- %s " % c)

        # add LANDRS and other namespaces, this converts the pythonized names to
        # something more readable
        self.g.namespace_manager.bind('landrs', LANDRS)
        self.g.namespace_manager.bind('sosa', SOSA)
        #self.g.namespace_manager.bind('base', BASE)
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
                                    if 'shape' in file_path:
                                        self.g2.load(
                                            file_path, format=graph_file_format, publicID=self.my_host_name)
                                    else:
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

    #############
    # create uuid
    #############
    def generate_uuid(self):
        return base64.urlsafe_b64encode(uuid.uuid4().bytes)[:-2].decode('utf-8')

    ######################
    # dump graph as turtle
    ######################
    def dump_graph(self, id):
        graph = self.g.get_context(self.BASE.term(id))
        if graph:
            return graph.serialize(format="turtle", base=self.my_host_name)
        else:
            return None

    #######################
    # dump graphs as turtle
    #######################
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
            id_node = self.BASE.term(uuid)
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
        g = self.g.get_context(self.BASE.term(id))
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
                    v['datatype'] = o.datatype

            # add the triple
            g_json[s][p].append(v)

        return json.dumps(g_json, indent=4)

###########################################
# end of py_drone_graph_core class
###########################################
