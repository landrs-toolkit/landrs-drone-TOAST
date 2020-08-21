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
from configparser import ConfigParser, ExtendedInterpolation
import logging
import urllib

# flask imports
import flask
from flask import request, jsonify, send_from_directory, render_template_string
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

# setup web file locations
TEMPLATES_DIR = 'config/templates'
STATIC_DIR = 'config/static'

################################################################################
# Main initialization section
################################################################################
'''
Use configuration file to load information
'''
# read configuation file?
config = ConfigParser(interpolation=ExtendedInterpolation())
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

# get mavlink dictionary
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

# instantiate flight
# get flight dictionary
flight_dict = {}
if 'FLIGHT' in config.keys():
    # get dictionary
    flight_dict = config['FLIGHT']

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

# Start mavlink thread
t1.start()

################################################################################
# Main Flask program to provide API for drone interface
################################################################################
# create my api server
app = flask.Flask(__name__, template_folder=TEMPLATES_DIR,
                  static_folder=STATIC_DIR)
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
# @app.route('/', methods=['GET', 'POST'])


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
    request_dict = request.form.to_dict()
    print(request_dict)

    # return data
    ret = {}

    # preset response in case 'action' not sent
    response = None

    # get action
    if 'action' in request.form:
        response = request.form.get('action', type=str)
        # should we add list of graphs fir Ajax?
        if response == 'stop':
            data_graph_info = d_graph.get_data_graphs()
            # render graph list
            graph_list = render_template('graph.html', data_graphs=data_graph_info['graphs'])
            ret.update( {'graphs': graph_list} )

    # if thread is running then send the payload
    if t1.is_alive():
        # status message
        response = "message sent: " + response

        # message to thread
        q_to_mavlink.put(request_dict)

    # update return
    ret.update({"status": response, "thread": t1.is_alive()})

    # go
    return ret, 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

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
@app.route("/api/v1/store/<string:collection_id>", methods=['POST'])
def store_data_point(collection_id):
    '''
    Generates random data with "now" time stamp.

    Args:
        collection_id (str):    uuid of collection. if '*' passed for observation
                                collection uuid the it will create one.

    Returns:
       json:    return new collection uuid (if created) for future stores.
                status information on store.
    '''
    # get sensor data
    #dict = request.args.to_dict()
    if 'data' in request.args:
        # typical data {"type": "co2", "co2": "342", "time_stamp": "2020-07-11T15:25:10.106776"}
        data = json.loads(request.args.get('data', type=str))
        #print(data)

        # configured?
        if 'flight' in flight_dict.keys():

            # call store function
            ret = d_graph.store_data_point(collection_id, data, flight_dict)

            # return status
            return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

        else:
            return json.dumps({"error": "not configured for logging."}), 500, {'Content-Type': 'application/json; charset=utf-8'}

    return json.dumps({"error": "no data"}), 500, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

##############################################
# base of web server, display config. options
##############################################


@app.route('/')
def form():
    # get list of shapes
    shapes_list = d_graph.get_shapes()
    shapes_list.sort()

    # output list
    shape_list = []
    # put into list for web page
    for i in range(0, len(shapes_list)):
        shape_list.append(
            {"shape": shapes_list[i], "encoded": urllib.parse.quote(shapes_list[i], safe='')})

    # get the data graphs
    data_graph_info = d_graph.get_data_graphs()

    # check flight exists
    flight_name, flight_description = d_graph.check_flight(flight_dict)

    # show comm ports?
    comms_ports = []
    if mavlink_dict.get('list_ports', 'False') == 'True':
        comms_ports = py_drone_mavlink.get_serial_ports()

    # render main page
    return render_template('index.html', shape_list=shape_list, myid=ontology_myID,
                           data_graphs=data_graph_info['graphs'], comms_ports=comms_ports, 
                            flight={'name': flight_name, 'description': flight_description})

################################
# generate the appropriate form
################################


@app.route('/generate_form/<string:id>')
def gen_form(id):
    # get shape to use
    shape_type = urllib.parse.unquote(id)

    try:
        # find shape (dictionary)
        shape = d_graph.get_shape(shape_type)

        # generate form
        new_shape, pre_rend = generate_form(shape)

        # create map file
        map_ttl = d_graph.create_rdf_map(new_shape)

        # render
        return render_template_string(pre_rend, map_ttl=urllib.parse.quote(map_ttl, safe=''))

    except FileNotFoundError:
        return Response('No SHACL shapes file provided.',
                        status=500,
                        mimetype='text/plain')
    return redirect(url_for('form'))

#####################################
# post the form here for proccessing
#####################################


@app.route('/post', methods=['POST'])
def post():
    form2rdf_controller = Form2RDFController(
        d_graph.BASE)  # 'http://example.org/ex#')
    try:
        # , map_ttl) #'ttl/map.ttl')
        rdf_result, uuid = form2rdf_controller.convert(request)
    except ValueError as e:
        return Response(str(e))
    except FileNotFoundError:
        return Response('Map.ttl is missing!', status=500, mimetype='text/plain')
    #rdf_result.serialize(destination='ttl/result.ttl', format='turtle')
    ret_error = d_graph.add_graph(rdf_result)

    # OK?
    if not ret_error:
        return render_template('post.html', uuid=uuid)
    else:
        return render_template('post_error.html', error=ret_error)

# Flight generation ###########################################################


@app.route('/flight')
def flight():
    # get required inputs from SHACL file
    # add any substitutions using info in flight_dict
    boundarys = d_graph.flight_shacl_requirements(flight_dict)

    # render flight page
    return render_template('flight.html', boundarys=boundarys)


@app.route('/flight_create', methods=['POST'])
def flight_create():
    # get request as dict to send to mavlink
    request_dict = request.form.to_dict()
    #print("REQ", request_dict)

    # process request and create flight sub-graph
    try:
        # create
        mission_dict = d_graph.process_flight_graph(request_dict, flight_dict)

        # success?
        if mission_dict['status'] == 'OK':

            # get new oc/sensor
            obs_col = mission_dict['obs_col']
            flt_name = mission_dict['flt_name']
            dataset = mission_dict['dataset']

            # setup config file
            config.set('MAVLINK', 'observation_collection', obs_col)
            config.set('MAVLINK', 'dataset', dataset)

            # remove old sensor data
            prop_label = flight_dict.get('flight_sensor', 'sensor')
            k_remove = [key for key, val in mavlink_dict.items() if prop_label == key[:len(prop_label)]]
            for kr in k_remove:
                mavlink_dict.pop(kr)

            # load sensor data
            for sensor in mission_dict['sensors']:
                for k in sensor:
                    config.set('MAVLINK', k, sensor[k])

            config.set('FLIGHT', 'flight', flt_name)

            # Writing our configuration file
            with open(config_file, 'w') as configfile:
                config.write(configfile)

            # mavlink running? if its not alive, start
            if not t1.is_alive():
                t1.start()

            # message to thread
            request_dict = {'action': 'set_oc_sensor',
                            'obs_col': obs_col, 'sensors': mission_dict['sensors']}
            q_to_mavlink.put(request_dict)

        else:
            # fail, return status
            return mission_dict, 200, {'Content-Type': 'application/json; charset=utf-8'}

    except Exception as ex:
        print("Could not create flight: " + str(ex))
        return json.dumps({"status": "Could not create flight: " + str(ex)}), 200, {'Content-Type': 'application/json; charset=utf-8'}

    # return flight info
    return mission_dict, 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# TEST AREA ####################################################################

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
