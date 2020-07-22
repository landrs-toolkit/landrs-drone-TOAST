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
import logging

# flask imports
import flask
from flask import request, jsonify, send_from_directory
from flask import render_template, Response, redirect, url_for
from flask_cors import CORS
from jinja2.exceptions import TemplateNotFound

# thread Imports
from threading import Thread
from queue import Queue

# LANDRS imports
import graph.py_drone_graph as ldg
import py_drone_mavlink
from config.config_generate_form import generate_form
from config.config_form2rdf import Form2RDFController

# Defines ######################################################################
# things I need to know

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

# configuration file
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
# read configuation file?
config = configparser.ConfigParser()
config.read(config_file)

# retrive data from config


def get_config(key, name, name_default):
    '''
    Args:
        key (str):          main key in config
        name (str):         second key in config
        name_default (str): return if not found

    Returns:
       dict.: information on node copying
    '''
    # det default
    ret = name_default

    # check dictionary
    if key in config.keys():
        # get uuid
        if name in config[key].keys():
            ret = config[key][name]

    # return value
    return ret


# Set logging configuration ####################################################
try:
    logging_level = int(get_config('DEFAULT', 'logging_level', '20'))
except:
    logging_level = 10
logging_file = get_config('DEFAULT', 'logging_file', 'landrs.log')
logging.basicConfig(filename=logging_file, filemode='w', level=logging_level)

# get drone id
ontology_myID = get_config('DRONE', 'drone_uuid', ontology_myID)
print("config:ontology_myID", ontology_myID)

# get graph dictionary
graph_dict = {}
if 'GRAPH' in config.keys():
    # get dictionary
    graph_dict = config['GRAPH']

# get graph dictionary
mavlink_dict = {}
if 'MAVLINK' in config.keys():
    # get dictionary
    mavlink_dict = config['MAVLINK']

# load the data to serve on the API ############################################
'''
Create instance of the drone Graph
also create and load graph,
optional ttl file load.
Now added graph dictionary from configuration.
'''
# get my base
my_base = get_config('DEFAULT', 'base', 'http://ld.landrs.org/id/')
my_host_name = get_config('DEFAULT', 'host_name', 'http://ld.landrs.org/')

# instantiate graph
d_graph = ldg.py_drone_graph(ontology_myID, graph_dict, my_base, my_host_name)

#get port. here as sent to mavlink##############################################
port = int(get_config('DEFAULT', 'port', '5000'))

################################################################################
# start mavlink thread, start as daemon so terminates with the main program
################################################################################
# create queue
q_to_mavlink = Queue()

# create thread for mavlink link, send api callback
t1 = Thread(target=py_drone_mavlink.mavlink, daemon=True,
            args=(q_to_mavlink, mavlink_dict, 'http://localhost:' + str(port) + '/api/v1/store/'))

# Start mavlink thread if required,
# NOTE: In this instance 'http://localhost:5000/api/v1/mavlink?action=start/stop'
# will have no effect as task started before Flask fork.
# RECOMMENDATION: set run_at_start = False and start with
# 'http://localhost:5000/api/v1/mavlink?action=start'.
if mavlink_dict.get('run_at_start', 'False').lower() == 'true':
    t1.start()

################################################################################
# Main Flask program to provide API for drone interface
################################################################################
# create my api server
app = flask.Flask(__name__)
# DANGER WILL ROBERTSON!!
# I want to be able to point Sebastian's "demo" vue app at the drone.
if get_config('DEFAULT', 'CORS', 'True') == 'True':
    # CORS(app, resources={r"*": {"origins": "http://localhost:5000"}})
    CORS(app)

# debug?
if get_config('DEFAULT', 'DEBUG', 'True') == 'True':
    app.config["DEBUG"] = True

# start of API creation ########################################################

##########################################################################
# Setup root to return OpenAPI compilent response with drone ontology data
##########################################################################
#@app.route('/', methods=['GET', 'POST'])
@app.route('/api', methods=['GET'])
@app.route('/api/v1', methods=['GET'])
def home():
    # Only if the request method is POST
    if request.method == 'POST':

        # get id
        myid = request.args.get('id')
        print("post", myid)
        # parse_kg()

    # Swagger v2.0 uses basePath as the api root
    # setup dictionary to return
    op_dict = drone_dict.copy()
    op_dict.update(d_graph.get_id_data(d_graph.Id, True))  # get drone data
    # get attached sensors
    op_dict.update({"sensors": d_graph.get_attached_sensors()})

    # dump
    return json.dumps(op_dict), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

####################################################
# control mavlink thread
####################################################


@app.route('/api/v1/mavlink', methods=['GET', 'POST'])
def mavlink():
    # get request as dict to send to mavlink
    request_dict = request.args.to_dict()

    # preset response in case 'action' not sent
    response = False

    # get action
    if 'action' in request.args:
        action = request.args.get('action', type=str)

        # set returned data to thread is alive flag
        response = t1.is_alive()

        # start?
        if action == "start":
            # if its not alive, start
            if not t1.is_alive():
                response = "started"
                t1.start()
        #     else:
        #         # else send a message to start
        #         q_to_mavlink.put("start")

        # # tell thread to stop if running
        # if action == "stop" and t1.is_alive():
        #     q_to_mavlink.put("stop")

    # if thread is running then send the payload
    if t1.is_alive():
        response = "message sent"

        #message
        q_to_mavlink.put(request_dict)

    return json.dumps({"thread": response}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

####################################################
# Setup Sensors function to return a list of sensors
####################################################


@app.route('/api/v1/sensors', methods=['GET', 'POST'])
def sensors_list():
    return json.dumps({"sensors": d_graph.get_attached_sensors()}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

################################################################################
# Setup sparql endpoint
################################################################################


@app.route('/api/v1/sparql', methods=['GET', 'POST'])
def sparql_endpoint():
    '''
    Works with http://localhost:5000/api/v1/sparql?query=SELECT ?type  ?attribute
    WHERE { <http://ld.landrs.org/id/MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==>
    ?type  ?attribute  }
    '''
    for arg in request.form:
        print("ARG", arg)

    query = ""

    # do we have a query?
    if request.method == "POST":
        if 'query' in request.form:
            # get id
            query = request.form.get('query', type=str)
            q_type = "query"

        if 'update' in request.form:
            # get id
            query = request.form.get('update', type=str)
            q_type = "insert"

    if request.method == "GET":
        if 'query' in request.args:
            # get id
            query = request.args.get('query', type=str)
            q_type = "query"

        if 'update' in request.args:
            # get id
            query = request.args.get('update', type=str)
            q_type = "insert"

    print("Query", query, "Type", q_type)

    if query != "":
        # lets query the graph!
        try:
            # query
            ret, ret_type = d_graph.run_sql(
                query, q_type, request.headers.get('Accept'))

            # return results
            return ret, 200, {'Content-Type': '{}; charset=utf-8'.format(ret_type)}

        except:
            # return error
            return json.dumps({"error": "query failed"}), 500, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}
    else:
        return json.dumps({"error": "no query"}), 500, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

#######################################################################
# Static page to provide yasgui interface
#######################################################################


@app.route('/sparql')
def sparql():
    '''
    This webpage allows the user to perform sparql queries
    using the yasgui interface (see ld.landrs.org/sparql to see example)
    '''
    # note, this file is in templates as flask's default location
    heading = get_config('DEFAULT', 'yasgui_heading', 'SPARQL')

    # render it
    return render_template('sparql.html', name=heading)

###################################################
# Download the entire graph as turtle
###################################################


@app.route("/api/v1/turtle/<path:path>")
def get_graph_file(path):
    '''
    Provide your preferred filename e.g. dgraph.ttl
    actually creates the file on the drone in /files
    may need to clean this up periodically
    (or allways use the same filename)
    '''
    # create file
    d_graph.save_graph(os.path.join("./files", path))
    # and download file
    return send_from_directory("./files", path, as_attachment=True)

####################################
# list graphs
####################################


@app.route("/api/v1/graph")
def list_graphs():
    '''
    Returns:
       json: list of graphs
    '''
    ret = d_graph.list_graphs()

    return ret, 200, {'Content-Type': 'text/turtle; charset=utf-8'}

####################################
# dump graph in turtle format
####################################


@app.route("/api/v1/graph/<string:id>")  # uuid
def dump_graph(id):
    '''
    Args:
        id (str): uuid graph

    Returns:
       turtle: the data in the graph in turtle format
    '''
    # get info from id
    try:
        # serialize graph
        ret = d_graph.dump_graph(id)

        # good result?
        if ret:
            # return data
            return ret, 200, {'Content-Type': 'text/turtle; charset=utf-8'}
        else:
            # no such graph
            return json.dumps({"error": "graph: " + id + " does not exist"}), 500, \
                {'Content-Type': 'application/sparql-results+json; charset=utf-8'}
    except:
        # error
        return json.dumps({"error": "could not retreive graph"}), 500, \
            {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

###################
# Sensors endpoint,
###################


@app.route("/api/v1/sensors/<string:id>")  # uuid
def get_sensor_data(id):
    '''
    Args:
        id (str): uuid of sensor or other object

    Returns:
       json: the data it has on a uuid
    '''
    # get info from id
    ret = d_graph.get_id_data(id, True)

    # return data as json
    # #find my drone data
    return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

####################################
# Id endpoint,
####################################


@app.route("/api/v1/id/<string:id>")
@app.route("/id/<string:id>")
def get_id_data(id):
    '''
    Args:
        id (str): uuid of id or other object

    Returns:
       turtle: the data it has on a uuid
    '''
    # get info from id
    ret = d_graph.get_id_data(id)

    # return data as turtle
    # #find my drone data
    return ret, 200, {'Content-Type': 'text/turtle; charset=utf-8'}
    # return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}    # #find my drone data

###########################################################################
# Store data point
###########################################################################


# uuid
@app.route("/api/v1/store/<string:collection_id>/<string:sensor_id>", methods=['POST'])
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
    # get sensor data
    #dict = request.args.to_dict()
    if 'data' in request.args:
        # typical data {"type": "co2", "co2": "342", "time_stamp": "2020-07-11T15:25:10.106776"}
        data = json.loads(request.args.get('data', type=str))
        # print(data)

        # call store function
        ret = d_graph.store_data_point(collection_id, sensor_id, data)

        # return status
        return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

    return json.dumps({"error": "no data"}), 500, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# TEST AREA ####################################################################
@app.route('/')
def form():
    try:
        return render_template('form_contents.html')
    except TemplateNotFound:
        return render_template('generate_form_prompt.html')

@app.route('/generate_form')
def gen_form():
    form_filepath = 'templates/form_contents.html'
    map_filepath = 'ttl/map.ttl'
    try:
        # find shape (dictionary)
        shape = d_graph.get_shape('http://example.org/ex#PersonShape1')
        # generate form
        new_shape = generate_form(shape, form_destination=form_filepath, map_destination=map_filepath)
        # create map file
        d_graph.create_rdf_map(new_shape, map_filepath)

    except FileNotFoundError:
        return Response('No SHACL shapes file provided.',
                        status=500,
                        mimetype='text/plain')
    return redirect(url_for('form'))

@app.route('/post', methods=['POST'])
def post():
    form2rdf_controller = Form2RDFController('http://example.org/ex#')
    try:
        rdf_result = form2rdf_controller.convert(request, 'ttl/map.ttl')
    except ValueError as e:
        return Response(str(e))
    except FileNotFoundError:
        return Response('Map.ttl is missing!', status=500, mimetype='text/plain')
    #rdf_result.serialize(destination='ttl/result.ttl', format='turtle')
    d_graph.add_graph(rdf_result)
    return render_template('post.html')

# copy node to drone
@app.route("/api/v1/test/<string:id>")  # uuid
def set_id_data(id):
    ret = d_graph.copy_remote_node(id)

    # return error
    return json.dumps({"status": ret}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# testing
@app.route("/api/v1/testing")  # uuid
def testing():
    # d_graph.get_attached_sensors()
    ret = d_graph.copy_remote_graph(
        "CRS2NmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==")
    return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# END TEST AREA ################################################################

##############################################
# Catch all of incorrect api endpoint accesses
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
# #get port
# port = int(get_config('DEFAULT', 'port', '5000'))


# start
app.run(host='0.0.0.0', port=port)
