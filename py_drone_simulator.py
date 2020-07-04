'''
Simple drone emulator that,
1) takes a uuid (base64 encoded)
2) queries ld.landers.org to find its configuration OR
2) Loads a set of ttl files and runs sparql queries locally
3) generates an API for access to sensor data
4) provides other functionality in support of Landrs development.

Chris Sweet 06/24/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

Typical call would be,
python3 py_drone_simulator.py MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg== ../landOntTest/
where MjlmNmV... is the drone uuid and
../landOntTest/ is the location of the turtle files I want to load into
the database (here I pulled out Priscila's ontology file set repo. to this
location).
Note: the database is persistent, you only need to load the files once,
subsequent runs will pull from the database.
Database is SQLite via SQLAlchemy.

This code provides the flask driven API, which utilizes py_drone_graph, for
acessing and manipulating the rdf graph.

Repo. structure
py_drone_simulator.py, this file
py_drone_graph.py,     the rdflib based class
requirements.txt,      file containing the dependences for this code
templates/sparql.html, yasgui webpage for sparql access, hosted on drone
db/landrs_test.sqlite, sample database containing base.ttl
ttl/base.ttl,          sample turtle file
files/,                location for the graph dump turtle files
'''

# Imports ######################################################################
import json
import sys
import os
import random
import datetime
import configparser

#flask imports
import flask
from flask import request, jsonify, send_from_directory
from flask import render_template
from flask_cors import CORS

#LANDRS imports
import py_drone_graph as ldg

# Defines ######################################################################
#things I need to know

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

#configuration file
config_file = "py_drone.ini"

#OpenAPI definitions, work in progress and only covers sensors #################
drone_dict = {"openapi": "3.0.0",
        "info": {
              "title": "Priscila's Drone API",
              "description": "Python drone simulation for Knowledge Graph testing.",
              "version": "0.0.2"
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
        "basePath": "/api/v1"}

################################################################################
# Main Flask program to provide API for drone interface
################################################################################
'''
Use configuration file to load information
'''
#read configuation file?
config = configparser.ConfigParser()
config.read(config_file)

#get drone id
if 'DRONE' in config.keys():
    #get uuid
    if 'drone_uuid' in config['DRONE'].keys():
        ontology_myID = config['DRONE']['drone_uuid']
        print("config:ontology_myID", ontology_myID)

#get turtle file and graph dictionary
graph_dict = {}
if 'GRAPH' in config.keys():
    #get dictionary
    graph_dict = config['GRAPH']

    #get graph file
    if 'graph_file' in graph_dict.keys():
        load_graph_file = graph_dict['graph_file']
        print("config:load_graph_file", load_graph_file)

#create my api server
app = flask.Flask(__name__)
#DANGER WILL ROBERTSON!!
# I want to be able to point Sebastian's "demo" vue app at the drone.
CORS(app)

app.config["DEBUG"] = True

# load the data to serve on the API ############################################
'''
Create instance of the drone Graph
also create and load graph,
optional ttl file load.
Now added graph dictionary from configuration.
'''
d_graph = ldg.py_drone_graph(ontology_myID, graph_dict)

# start of API creation ########################################################

##########################################################################
#Setup root to return OpenAPI compilent response with drone ontology data
##########################################################################
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
    #setup dictionary to return
    op_dict = drone_dict.copy()
    op_dict.update(d_graph.get_id_data(d_graph.Id)) #get drone data
    op_dict.update({ "sensors": d_graph.get_attached_sensors() }) #get attached sensors

    #dump
    return json.dumps(op_dict), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

####################################################
#Setup Sensors function to return a list of sensors
####################################################
@app.route('/api/v1/sensors', methods=['GET','POST'])
def sensors_list():
    return json.dumps({"sensors": d_graph.get_attached_sensors()}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

################################################################################
#Setup sparql endpoint
################################################################################
@app.route('/api/v1/sparql', methods=['GET','POST'])
def sparql_endpoint():
    '''
    Works with http://localhost:5000/api/v1/sparql?query=SELECT ?type  ?attribute
    WHERE { <http://ld.landrs.org/id/MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==>
    ?type  ?attribute  }
    '''
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

#######################################################################
#Static page to provide yasgui interface
#######################################################################
@app.route('/sparql')
def sparql():
    '''
    This webpage allows the user to perform sparql queries
    using the yasgui interface (see ld.landrs.org/sparql to see example)
    '''
    #note, this file is in templates as flask's default location
    return render_template('sparql.html')

###################################################
#Download the entire graph as turtle
###################################################
@app.route("/api/v1/turtle/<path:path>")
def get_graph_file(path):
    '''
    Provide your preferred filename e.g. dgraph.ttl
    actually creates the file on the drone in /files
    may need to clean this up periodically
    (or allways use the same filename)
    '''
    #create file
    d_graph.save_graph(os.path.join("./files", path))
    #and download file
    return send_from_directory("./files", path, as_attachment=True)

####################################
#Id/sensors endpoint,
####################################
@app.route("/api/v1/sensors/<string:id>") #uuid
@app.route("/api/v1/id/<string:id>") #uuid
def get_id_data(id):
    '''
    Args:
        id (str): uuid of sensor or other object
        type (str):  insert/query type

    Returns:
       json: the data it has on a uuid
    '''
    #get info from id
    ret = d_graph.get_id_data(id)

    #return data
    return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}    # #find my drone data

###########################################################################
#Store data point
###########################################################################
@app.route("/api/v1/store/<string:collection_id>/<string:sensor_id>") #uuid
def store_data_point(collection_id, sensor_id):
    '''
    Generates random data with "now" time stamp.

    Args:
        collection_id (str):    uuid of collection. if '*' passed for observation
                                collection uuid the it will create one.
        sensor_id (str):        sensor uuid to associate data with

    Returns:
       json:    return new collection uuid (if created) for future stores.
                status information on store.
    '''
    #generate data
    co2 = random.uniform(250, 440)
    ts = datetime.datetime.now().isoformat()

    #call store function
    ret = d_graph.store_data_point(collection_id, sensor_id, co2, ts)

    #return status
    return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# TEST AREA ####################################################################
#copy node to drone
@app.route("/api/v1/test/<string:id>") #uuid
def set_id_data(id):
    print("Id", id)
    ret = d_graph.copy_remote_node(id)

    #return error
    return json.dumps({"status": ret}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

#testing
@app.route("/api/v1/testing") #uuid
def testing():
    #d_graph.get_attached_sensors()
    ret = d_graph.copy_remote_graph("CRS2NmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==")
    return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# END TEST AREA ################################################################

##############################################
#Catch all of incorrect api endpoint accesses
##############################################
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    '''
    Args:
        path (str): path user has attempted to access

    Returns:
       json: informs the user of their mistake
    '''
    return json.dumps({"status": "no endpoint: " + path}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# run the api server ###########################################################
app.run(host='0.0.0.0')
