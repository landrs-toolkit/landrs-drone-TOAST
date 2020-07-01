#
# Simple drone emulator that,
# 1) takes an id
# 2) queries ld.landers.org to find its configuration OR
# 2) Loads a set of ttl files and runs sparql queries locally
# 3) generates an API for access to sensor data
#
# Chris Sweet 06/24/2020
# University of Notre Dame, IN
#

# Imports ######################################################################
#library https://pypi.org/project/sparql-client/
import sparql
import flask
from flask import request, jsonify, send_from_directory
import json
import sys
import os
import rdflib
from rdflib.serializer import Serializer
from rdflib import plugin, Graph, Literal, URIRef
from rdflib.store import Store
from rdflib.plugins.sparql.processor import processUpdate

from flask import render_template
from flask_cors import CORS

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
class drone_graph:
    #################
    #class variables
    #################
    g = None #graph
    drone_dict = {} #dictionary of drone data
    Drone = None
    Sensors = []
    SensorData = []
    files_loaded = False

    # # class initialization
    # def __init__(self):
    #     self.drone_dict = {}

    #############################################################
    #function to copy graph node from la.landrs.org if not exist
    #############################################################
    def copy_remote_id(self, ontology_myid):
        # set drone id
        self.Drone = ontology_prefix + ontology_myid

        #find my drone data
        q = ('SELECT ?type ?attribute ' \
                'WHERE { ' \
                '   <' + self.Drone + '>  ?type ?attribute .' \
                '} ')

        #grab the result and find my data
        result = self.g.query(q)

        #bail if exists
        if result:
            print("Id exists", ontology_myid)
            return

        #lets try and get it from ld.landrs.org
        result = sparql.query('http://ld.landrs.org/query', q)

        #bail if no match
        if not result:
            print("Id does not exist on ld.landrs.org", ontology_myid)
            return

        #if we are here then it exists on our server
        # loop over rows returned, check for my id
        for row in result:
            values = sparql.unpack_row(row)

            #put data into graph



    #######################################################
    #function to parse kg on local graph based on drone id
    #######################################################
    def parse_kg(self, ontology_myid):
        endpoints = []  #save endpoints
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
            processUpdate(self.g, query)
            ret = json.dumps({"status": "success"})
        else:
            result = self.g.query(query)
            # convert to JSON
            ret = result.serialize(format="json")

        print("json",ret)
        #return
        return ret

########################################################
# Main Flask program to provide API for drone interface
########################################################
#get inline parameter version of myID
if len(sys.argv) < 2:
    print("Please provide a Drone id")
else:
    ontology_myID = sys.argv[1]

#load ttl file?
load_graph_file = ""
if len(sys.argv) >= 3:
    load_graph_file = sys.argv[2]
    print("Load",load_graph_file)

#create my api server
app = flask.Flask(__name__)
#DANGER WILL ROBERTSON!!
CORS(app)

app.config["DEBUG"] = True

# load the data to serve on the API ############################################
#create instance of the drone Graph
d_graph = drone_graph()

#setup swagger headers
d_graph.swagger_setup()

#create and load graph
d_graph.setup_graph(load_graph_file)

#save?
#d_graph.save_graph("base_plus_shape.ttl")

#parse the kg in the db
Endpoints = d_graph.parse_kg(ontology_myID)

# start of API creation ########################################################
#create function to handle sensor queries
def sensors():
    #get rule that called us
    rule = request.url_rule

    #loop over sensors to see if this is quierying them
    for i in range(0,len(d_graph.Sensors)):
        #name in rule?
        if d_graph.Sensors[i] in rule.rule:
            print("page",rule.rule)
            return json.dumps(d_graph.SensorData[i]), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

    #not found sensor if here
    return json.dumps({ "error": "URL not found"
                        }), 500, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

#create endpoints based on the sensor function
sensor_count = 0
for endpoint in Endpoints:
    #print("ep",endpoint)
    #api counter
    sensor_count = sensor_count + 1

    #add API endpoint
    app.add_url_rule(
        '/api/v1/sensors/'+endpoint, #this is the actual url
        'sensor_' + str(sensor_count) # this is the name used for url_for
    )
    app.view_functions['sensor_' + str(sensor_count)] = sensors

#setup root to return OpenAPI compilent response with drone ontology data
@app.route('/', methods=['GET','POST'])
@app.route('/api', methods=['GET'])
@app.route('/api/v1', methods=['GET'])
def home():
    # Only if the request method is POST
    if request.method == 'POST':

        #get id
        myid = request.args.get('id')
        print("post",myid)
        #parse_kg()

    #Swagger v2.0 uses basePath as the api root
    return json.dumps(d_graph.drone_dict), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

#setup Sensors function to return a list of sensors
@app.route('/api/v1/sensors', methods=['GET','POST'])
def sensors_list():
    return json.dumps({"sensors": d_graph.Sensors}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

#setup sparql endpoint
# works with http://localhost:5000/api/v1/sparql?query=SELECT ?type  ?attribute
#   WHERE { <http://ld.landrs.org/id/MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==>
#   ?type  ?attribute  }
@app.route('/api/v1/sparql', methods=['GET','POST'])
def sparql_endpoint():
    for arg in request.form:
        print("ARG",arg)

    query = ""

    #do we have a query?
    if request.method == "POST":
        if 'query' in request.form:
            #get id
            query = request.form.get('query',type = str)
            q_type = "query"

        if 'update' in request.form:
            #get id
            query = request.form.get('update',type = str)
            q_type = "insert"

    if request.method == "GET":
        if 'query' in request.args:
            #get id
            query = request.args.get('query',type = str)
            q_type = "query"

        if 'update' in request.args:
            #get id
            query = request.args.get('update',type = str)
            q_type = "insert"

    print("Query",query,"Type", q_type)

    if query != "":
        #lets query the graph!
        try:
            #query
            ret = d_graph.run_sql(query, q_type)

            #return results
            return ret, 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

        except:
            #return error
            return json.dumps({"error": "query failed"}), 500, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}
    else:
        return json.dumps({"error": "no query"}), 500, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

#static page to provide yasgui interface
@app.route('/sparql')
def sparql():
    return render_template('sparql.html')

#download the entire graph as turtle
@app.route("/files/<path:path>")
def get_graph_file(path):
    #create file
    d_graph.save_graph(path)
    #and download file
    return send_from_directory("./", path, as_attachment=True)

# run the api server ###########################################################
app.run(host='0.0.0.0')
