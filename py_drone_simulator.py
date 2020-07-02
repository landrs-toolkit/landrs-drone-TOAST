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

from flask import render_template
from flask_cors import CORS

#LANDRS imports
import py_drone_graph as ldg

# Defines ######################################################################
#things I need to know

# part I need to remove from landrs returns to get ids
ontology_prefix = 'http://ld.landrs.org/id/'

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="

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
d_graph = ldg.py_drone_graph()

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
@app.route("/api/v1/turtle/<path:path>")
def get_graph_file(path):
    #create file
    d_graph.save_graph(os.path.join("./files", path))
    #and download file
    return send_from_directory("./files", path, as_attachment=True)

#id endpoint
@app.route("/api/v1/id/<string:id>") #uuid
def get_id_data(id):

    #build query
    q = ('SELECT ?type ?attribute ' \
            'WHERE { ' \
            '   <' + ontology_prefix + id + '>  ?type ?attribute .' \
            '} ')
    #query
    ret = d_graph.run_sql(q, "query")

    #return data
    return ret, 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}    # #find my drone data

#copy node to drone
@app.route("/api/v1/test/<string:id>") #uuid
def set_id_data(id):
    print("Id", id)
    ret = d_graph.copy_remote_node(id)
    #return error
    return ret, 200, {'Content-Type': 'application/sparql-results+json; charset=utf-8'}

# run the api server ###########################################################
app.run(host='0.0.0.0')
