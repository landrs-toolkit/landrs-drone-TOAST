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
python3 py_drone_toast.py

For configuration,
[DRONE]
drone_uuid = MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==
gets the drone uuid and
[GRAPH]
file = ../landrsOntTest/
is the location of the turtle files I want to load into the database
(here I pulled out Priscila's ontology file set repo. to this location).
Note: the database is persistent, you only need to load the files once,
subsequent runs will pull from the database. Set,
[GRAPH]
file_reload = True
to reload each time.

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

#thread Imports
from threading import Thread
from queue import Queue

#LANDRS imports
import py_drone_graph as ldg
import py_drone_mavlink

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
# Main initialization section
################################################################################
'''
Use configuration file to load information
'''
#read configuation file?
config = configparser.ConfigParser()
config.read(config_file)

#retrive data from config
def get_config(key, name, name_default):
    '''
    Args:
        key (str):          main key in config
        name (str):         second key in config
        name_default (str): return if not found

    Returns:
       dict.: information on node copying
    '''
    #det default
    ret = name_default

    #check dictionary
    if key in config.keys():
        #get uuid
        if name in config[key].keys():
            ret = config[key][name]

    #return value
    return ret

#get drone id
ontology_myID = get_config('DRONE', 'drone_uuid', ontology_myID)
print("config:ontology_myID", ontology_myID)

#get graph dictionary
graph_dict = {}
if 'GRAPH' in config.keys():
    #get dictionary
    graph_dict = config['GRAPH']

#get graph dictionary
mavlink_dict = {}
if 'MAVLINK' in config.keys():
    #get dictionary
    mavlink_dict = config['MAVLINK']

# load the data to serve on the API ############################################
'''
Create instance of the drone Graph
also create and load graph,
optional ttl file load.
Now added graph dictionary from configuration.
'''
d_graph = ldg.py_drone_graph(ontology_myID, graph_dict)

################################################################################
# start mavlink thread, start as daemon so terminates with the main program
################################################################################
# thread that consumes data from mavlink
def mavlink_consumer(in_q, obs_collection, sensor_id):
    #save obs, coll
    collection_id = obs_collection

    #loop
    while True:
        # Get some data
        gps = in_q.get()

        # Process the data, if we got it
        if 'lat' in gps.keys():
            print("GPS lat", gps['lat'],"long", gps['lon'], "alt", gps['alt'])
            gps.update({ "type": "gps"})

            try:
                #scale mavlink
                gps['lat'] = str(float(gps['lat']) * 1e-7)
                gps['lon'] = str(float(gps['lon']) * 1e-7)
                gps['alt'] = str(float(gps['alt']) * 1e-3)

                #create timestamp, may be in stream
                ts = datetime.datetime.now().isoformat()

                #call store function
                ret = d_graph.store_data_point(collection_id, sensor_id, gps, ts)

                #if we used * the we should get back a obs coll uuid
                if 'collection uuid' in ret.keys():
                    collection_id = ret['collection uuid']

            except:
                pass

#create queue
q = Queue()

#get obs. collection, sensor
mav_obs_collection = mavlink_dict.get('observation_collection', '*')
mav_sensor = mavlink_dict.get('sensor', 'MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==')

#create thread for mavlink link
t1 = Thread(target = py_drone_mavlink.mavlink_loop, daemon=True, args =(q, mavlink_dict))

#create consumer thread
t2 = Thread(target = mavlink_consumer, daemon=True, args =(q, mav_obs_collection, mav_sensor))

#start mavlink threads if required
if mavlink_dict.get('run_at_start', 'False').lower() == 'true':
    t1.start()
    t2.start()

################################################################################
# Main Flask program to provide API for drone interface
################################################################################
#create my api server
app = flask.Flask(__name__)
#DANGER WILL ROBERTSON!!
# I want to be able to point Sebastian's "demo" vue app at the drone.
if get_config('DEFAULT', 'CORS', 'True') == 'True':
    CORS(app)

#debug?
if get_config('DEFAULT', 'DEBUG', 'True') == 'True':
    app.config["DEBUG"] = True

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
            ret, ret_type = d_graph.run_sql(query, q_type, request.headers.get('Accept'))

            #return results
            return ret, 200, {'Content-Type': '{}; charset=utf-8'.format(ret_type)}

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
    heading = get_config('DEFAULT', 'yasgui_heading', 'SPARQL')

    #render it
    return render_template('sparql.html', name = heading)

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
    co2 = { "co2": random.uniform(250, 440), "type": "co2" } #, "lat": "123", "lon": "567", "alt": "1000" }
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
#get port
port = int(get_config('DEFAULT', 'port', '5000'))

#start
app.run(host='0.0.0.0', port=port)
