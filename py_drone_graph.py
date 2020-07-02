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
                           PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SOSA, SSN, TIME, \
                           VOID, XMLNS, XSD
#from rdflib import Namespace
from SPARQLWrapper import SPARQLWrapper, JSON

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

# I have parts that belong to me
ontology_parts = "http://schema.landrs.org/schema/isPartOf"
# my parts host things
ontology_hosts = "http://www.w3.org/ns/sosa/hosts"
# some of the things I host are sensors
ontology_sensors = "http://schema.landrs.org/schema/Sensor" #"http://www.w3.org/ns/sosa/Sensor"
# which is a
ontology_sensor_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

###########################################
# Class to house graph functions for drone
###########################################
class py_drone_graph:
    #################
    #class variables
    #################
    g = None #graph
    drone_dict = {} #dictionary of drone data
    Drone = None
    Id = None
    Sensors = []
    SensorData = []
    files_loaded = False

    # # class initialization
    # def __init__(self):
    #     self.drone_dict = {}

    #############################################################
    #function to copy graph node from la.landrs.org if not exist
    #############################################################
    def copy_remote_node(self, node):

        #test if node exists locally
        if (URIRef(ontology_prefix + node), None, None) in self.g:
            print("This graph contains triples about "+node)
            return json.dumps({"status": "Id exists on drone"})

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
            return json.dumps({"status": "error"})
        #return json.dumps(ret)

        #bail if no match
        if not wresult:
            #print("Type does not exist on ld.landrs.org", node)
            return json.dumps({"status": "Type does not exist on ld.landrs.org"})

        #set my top level type
        myType = wresult[0]['type']['value']

        if not myType:
            #print("Could not extract type for node", node)
            return json.dumps({"status": "Could not extract type for node"})

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
        return json.dumps(info)

    #######################################################
    #function to parse kg on local graph based on drone id
    #######################################################
    def parse_kg(self, ontology_myid):
        endpoints = []  #save endpoints

        # set base id
        self.Id = ontology_myid

        # set drone id
        self.Drone = ontology_prefix + ontology_myid

        #find my drone data
        q = ('SELECT ?type ?attribute ' \
                'WHERE { ' \
                '   <' + self.Drone + '>  ?type ?attribute .' \
                '} ')

        #grab the result and find my data
        result = self.g.query(q)

        #bail if no match
        if not result:
            return

        # loop over rows returned, check for my id
        for values in result:

            #put data in dictionary
            #NOTE: this is unique so misses multiples!
            if values[0] in self.drone_dict.keys():
                #create list if so
                val = self.drone_dict[values[0]]
                if isinstance(val, list):
                    val.append(values[1])
                else:
                    val = [val, values[1]]
                self.drone_dict.update( {values[0] : val} )
            else:
                self.drone_dict.update( {values[0] : values[1]} )
            # if values[0] in drone_dict.keys():
            #     drone_dict[values[0]].append(values[1])
            # else:
            #     drone_dict.update( {values[0] : [values[1]]} )

        # if I exist find configuration
        print("Found", ontology_myid)

        # get the sensors
        #lets hunt down ispartof parts that belong to me. It woild be nice if isPartOf was transitive!
        q = ('SELECT ?sub ?h ?x WHERE { ' \
            	'  ?sub <' + ontology_sensor_type + '> <' + ontology_sensors + '> .' \
              	'  ?h <http://www.w3.org/ns/sosa/hosts> ?sub .' \
              	'  ?h <http://schema.landrs.org/schema/isPartOf> ?x .' \
              	'  ?x <http://schema.landrs.org/schema/isPartOf> <' + self.Drone + '> .' \
                '} ')

        #grab the result and find sensors
        result_sensor = self.g.query(q)

        # loop over rows returned, check for my id
        for values_sensor in result_sensor:
            print("vs",values_sensor)
            #save host/partof in drone data
            if ontology_hosts in self.drone_dict.keys():
                if values_sensor[1] not in self.drone_dict[ontology_hosts]:
                    self.drone_dict[ontology_hosts].append(values_sensor[1])
            else:
                self.drone_dict.update( {ontology_hosts : [values_sensor[1]]} )

            #save host/partof in drone data
            if ontology_parts in self.drone_dict.keys():
                if values_sensor[2] not in self.drone_dict[ontology_parts]:
                    self.drone_dict[ontology_parts].append(values_sensor[2])
            else:
                self.drone_dict.update( {ontology_parts : [values_sensor[2]]} )

            # save host and its partof
            sensor_dict = {ontology_hosts: values_sensor[1], ontology_parts: values_sensor[2]}

            #find sensor data
            q = ('SELECT ?type ?attribute ' \
                    'WHERE { ' \
                    '   <' + values_sensor[0] + '>  ?type ?attribute .' \
                    '} ')
            #grab the result and find my sensors
            resultc = self.g.query(q)

            # loop over rows returned, check for my id
            for valuesc in resultc:
                print("Sensor value",valuesc[0],values_sensor[0])
                sensor_dict.update( {valuesc[0] : valuesc[1]} )

            #anounce sensor
            print("sensor",values_sensor[0])

            #create api endpoint, add to list and let Flask create them
            endpoints.append(values_sensor[0].replace(ontology_prefix, ''))

            #save sensor data
            self.Sensors.append(values_sensor[0].replace(ontology_prefix, ''))

            #save data
            self.SensorData.append(sensor_dict)

        #add sensors
        self.drone_dict.update({ ontology_sensors: self.Sensors})

        #return endpoint list
        return endpoints

    #####################################
    #function to setup swagger 3 headers
    #####################################
    def swagger_setup(self):
        #openAPI/Swagger headers, https://swagger.io/docs/specification/basic-structure/
        self.drone_dict.update( \
            {"openapi": "3.0.0",
                "info": {
                      "title": "Priscila's Drone API",
                      "description": "Python drone simulation for Knowledge Graph testing.",
                      "version": "0.0.1"
                },
                "servers": {
                    "url": "http://localhost:5000/api/v1",
                    "description": "Flask API running on drone.",
                },
                "paths": {
                    "/sensors": {
                        "get": {
                            "summary": "Returns a list of sensors.",
                            "description": "Sensors hosted on flight controller board.",
                            "responses": {
                                '200': {   # status code \
                                    "description": "A JSON array of sensor ids", \
                                    "content": { \
                                        "application/json": { \
                                            "schema": { \
                                                "type": "array", \
                                                "items": { \
                                                    "type": "string"
                                                }, \
                                            }, \
                                        }, \
                                    }, \
                                }, \
                            }, \
                        }, \
                    }, \
                }, \
                "basePath": "/api/v1"})

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

        print("json",ret)
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
        return json.dumps(id_data)

    ##################################
    #get sensors attached to my drone
    ##################################
    def get_attached_sensors(self):
        # '  ?sub <' + ontology_sensor_type + '> <' + ontology_sensors + '> .' \
        # '  ?h <http://www.w3.org/ns/sosa/hosts> ?sub .' \
        # '  ?h <http://schema.landrs.org/schema/isPartOf> ?x .' \
        # '  ?x <http://schema.landrs.org/schema/isPartOf> <' + self.Drone + '> .' \

        #storage
        sensors = []
        #get things that are part of my drone
        for s, p, o in self.g.triples((None, URIRef(ontology_parts), URIRef(self.Drone))):
            print("level 1 {}  {}".format(s, o))
            #get the things connected to those
            for sp, pp, op in self.g.triples((None, URIRef(ontology_parts), s)):
                print("level 2 {}  {}".format(sp, op))
                #get the things hosted on those
                for sph, pph, oph in self.g.triples((sp, URIRef(ontology_hosts), None)):
                    print("sensors/actuators {}  {}".format(sph, oph))
                    #get the things that are sensors
                    for sphs, pphs, ophs in self.g.triples((oph, URIRef(RDF.type), ontology_sensors)):
                        print("sensors {}  {}".format(sphs, ophs))
                        sensors.append(sphs)

        #return info
        return sensors

###########################################
#end of py_drone_graph class
###########################################
