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
import flask
from flask import request, jsonify, send_from_directory
import json
import sys
import os
import random
import datetime

from flask import render_template
from flask_cors import CORS

#LANDRS imports
import py_drone_graph as ldg

# Defines ######################################################################
#things I need to know

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

#OpenAPI definitions
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
#also create and load graph
#optional ttl file load
d_graph = ldg.py_drone_graph(ontology_myID, load_graph_file)

# start of API creation ########################################################

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
    #setup dictionary to return
    op_dict = drone_dict.copy()
    op_dict.update(d_graph.get_id_data(d_graph.Id)) #get drone data
    op_dict.update({ "sensors": d_graph.get_attached_sensors() }) #get attached sensors

    #dump
    return json.dumps(op_dict), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

#setup Sensors function to return a list of sensors
@app.route('/api/v1/sensors', methods=['GET','POST'])
def sensors_list():
    return json.dumps({"sensors": d_graph.get_attached_sensors()}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

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
@app.route("/api/v1/turtle/<path:path>")
def get_graph_file(path):
    #create file
    d_graph.save_graph(os.path.join("./files", path))
    #and download file
    return send_from_directory("./files", path, as_attachment=True)

#id/sensors endpoint
@app.route("/api/v1/sensors/<string:id>") #uuid
@app.route("/api/v1/id/<string:id>") #uuid
def get_id_data(id):
    #get info from id
    ret = d_graph.get_id_data(id)

    #return data
    return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}    # #find my drone data

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

#store data point
@app.route("/api/v1/store/<string:sensor_id>") #uuid
def store_data_point(sensor_id):
    #generate data
    co2 = random.uniform(250, 440)
    ts = datetime.datetime.now().isoformat()

    #call store function
    ret = d_graph.store_data_point(sensor_id, co2, ts)

    #return status
    return json.dumps(ret), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# END TEST AREA ################################################################

#catch all of incorrect api endpoint
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
    return json.dumps({"status": "no endpoint: " + path}), 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# run the api server ###########################################################
app.run(host='0.0.0.0')
