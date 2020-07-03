#
# Graph Class for simple drone emulator that,
# 1) takes an id
# 2) queries ld.landers.org to find its configuration OR
# 2) Loads a set of ttl files and runs sparql queries locally
# 3) generates an API for access to sensor data
#
# Chris Sweet 07/02/2020
# University of Notre Dame, IN
#

# Imports ######################################################################
#library https://pypi.org/project/sparql-client/
import json
import os
import rdflib
from rdflib.serializer import Serializer
from rdflib import plugin, Graph, Literal, URIRef
from rdflib.store import Store
from rdflib.plugins.sparql.processor import processUpdate
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
                           PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SSN, TIME, \
                           VOID, XMLNS, XSD
#from rdflib import Namespace
from SPARQLWrapper import SPARQLWrapper, JSON

#setup our namespace
LANDRS = rdflib.Namespace('http://schema.landrs.org/schema/')
SOSA = rdflib.Namespace('http://www.w3.org/ns/sosa/')

# Defines ######################################################################
#things I need to know
# information can be queried on ld.landrs.org
ontology_landrs = 'http://ld.landrs.org/query'
#ontology_landrs_file = "ttl/base.ttl"
ontology_landrs_file_format = "ttl"

#db file
ontology_db = "landrs_test"
ontology_db_location = "db/landrs_test.sqlite"

# part I need to remove from landrs returns to get ids
ontology_prefix = 'http://ld.landrs.org/id/'

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

###########################################
# Class to house graph functions for drone
###########################################
class py_drone_graph:
    #################
    #class variables
    #################
    g = None                #graph
    Id = None               #local drone id
    files_loaded = False    #flag to prevent ontology reload

    #######################
    # class initialization
    #######################
    def __init__(self, ontology_myid, load_graph_file):
        # set base id
        self.Id = ontology_myid

        #load graph, include ttl to load if required
        self.setup_graph(load_graph_file)

    #############################################################
    #function to copy instance graph ld.landrs.org if not exist
    #############################################################
    def copy_remote_graph(self, ontology_myid):
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
        if (URIRef(ontology_prefix + ontology_myid), URIRef(RDF.type), LANDRS.UAX) in self.g:
            print(ontology_myid, "is a", LANDRS.UAX)
        else:
            ret.update({"id a drone": "False", "status": "error"})
            return ret

        #lets look for components and sensors
        #get things that are part of my id
        for s, p, o in self.g.triples((None, LANDRS.isPartOf, URIRef(ontology_prefix + ontology_myid))):
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

        #test if node exists locally
        if (URIRef(ontology_prefix + node), None, None) in self.g:
            print("This graph contains triples about "+node)
            return False

        #query to find top level type
        q_type = ('SELECT * WHERE { ' \
                 '	<' + ontology_prefix + node + '> a ?type .' \
                 '	filter not exists {' \
                 '    	?subtype ^a <' + ontology_prefix + node + '> ;' \
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
                '   <' + ontology_prefix + node + '>  ?type ?attribute .' \
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
        info = {"status": "done", myType: ontology_prefix + node}
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
        the_node = URIRef(ontology_prefix + node)
        self.g.add((the_node, RDF.type, URIRef(myType)))

        #add data
        for i in range(0, len(types)):
            self.g.add((the_node, types[i], attributes[i]))

        #done
        return True

    ##########################
    #setup and load graph
    ##########################
    def setup_graph(self, load_graph_file):
        #vars
        ident = URIRef(ontology_db)
        uri = Literal("sqlite:///%(here)s/%(loc)s" % {"here": os.getcwd(), "loc": ontology_db_location})

        #create and load graph
        store = plugin.get("SQLAlchemy", Store)(identifier=ident)
        self.g = Graph(store, identifier=ident)
        self.g.open(uri, create=True)

        #add LANDRS namespace
        self.g.namespace_manager.bind('LANDRS', LANDRS)
        self.g.namespace_manager.bind('SOSA', SOSA)

        #Load graph?
        if load_graph_file and not self.files_loaded:
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
                        if os.path.splitext(file_path)[-1].lower() == ".ttl":
                            if os.path.isfile(file_path):
                                print("file", file_path)
                                self.files_loaded = True
                                #load the individual file
                                self.g.load(file_path, format=ontology_landrs_file_format)

            else:
                print("File provided for import.")
                if os.path.isfile(load_graph_file):
                    self.files_loaded = True
                    self.g.load(load_graph_file, format=ontology_landrs_file_format)

    ##########################
    #save graph
    ##########################
    def save_graph(self, save_graph_file):
        #save graph?
        if save_graph_file:
            self.g.serialize(destination=save_graph_file, format='turtle')

    ##########################
    #run a sparql query
    ##########################
    def run_sql(self, query, type):
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

    ##########################
    #get triples for an id
    ##########################
    def get_id_data(self, id):
        #dictionary
        id_data = {}

        #get id's triples
        for s, p, o in self.g.triples((URIRef(ontology_prefix + id), None, None)):
            print("{} is a {}".format(p, o))
            id_data.update( {p : o} )

        #return info
        return id_data

    ##################################
    #get sensors attached to my drone
    ##################################
    def get_attached_sensors(self):
        # '  ?sub <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.landrs.org/sch ema/Sensor> .' \
        # '  ?h <http://www.w3.org/ns/sosa/hosts> ?sub .' \
        # '  ?h <http://schema.landrs.org/schema/isPartOf> ?x .' \
        # '  ?x <http://schema.landrs.org/schema/isPartOf> <' + ontology_prefix + ontology_myid + '> .' \

        #storage
        sensors = []
        #get things that are part of my drone
        for s, p, o in self.g.triples((None, LANDRS.isPartOf, URIRef(ontology_prefix + self.Id))):
            print("level 1 {}  {}".format(s, o))
            #get the things connected to those
            for sp, pp, op in self.g.triples((None, LANDRS.isPartOf, s)):
                print("level 2 {}  {}".format(sp, op))
                #get the things hosted on those
                for sph, pph, oph in self.g.triples((sp, SOSA.hosts, None)):
                    print("sensors/actuators {}  {}".format(sph, oph))
                    #get the things that are sensors
                    for sphs, pphs, ophs in self.g.triples((oph, URIRef(RDF.type), LANDRS.Sensor)):
                        print("sensors {}  {}".format(sphs, ophs))
                        sensors.append(sphs)

        #return info
        return sensors

###########################################
#end of py_drone_graph class
###########################################
