#
# Simple drone emulator that,
# 1) takes an id
# 2) queries ld.landers.org to find its configuration
# 3) generates an API for access to sensor data
#
# Chris Sweet 06/24/2020
# University of Notre Dame, IN
#

#library https://pypi.org/project/sparql-client/
import sparql
import flask
from flask import request, jsonify
import json
import sys

#things I need to know
# information can be queried on ld.landrs.org
ontology_landrs = 'http://ld.landrs.org/query'
# part I need to remove from landrs returns to get ids
ontology_prefix = 'http://ld.landrs.org/id/'

# I am a LANDRS drone
#ontology_drone = "http://schema.landrs.org/schema/UAV"
#ontology_drone = "http://schema.landrs.org/schema/FlightControllerBoard"
# an id of which which is a
#ontology_drone_type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"

# I have parts that belong to me
ontology_parts = "http://schema.landrs.org/schema/isPartOf"
# my parts host things
ontology_hosts = "http://www.w3.org/ns/sosa/hosts"
# some of the things I host are sensors
ontology_sensors = "http://www.w3.org/ns/sosa/Sensor"

# I have a unique ID that some nice person setup for me (probably Chris)
ontology_myID = "Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg=="

###################################
#function to handle sensor queries
###################################
def sensors():
    global Sensors, SensorData
    #get rule that called us
    rule = request.url_rule

    #loop over sensors to see if this is quierying them
    for i in range(0,len(Sensors)):
        #name in rule?
        if Sensors[i] in rule.rule:
            print("page",rule.rule)
            return json.dumps(SensorData[i]), 200

    #not found sensor if here
    return json.dumps({ "error": "URL not found"
                        }), 500

#######################################
#function to parse kg on ld.landrs.org
#######################################
def parse_kg():
    global drone_dict, Drone, Sensors, SensorData, sensor_count

    # set drone id
    Drone = ontology_prefix + ontology_myID

    #find my drone data
    q = ('SELECT * ' \
            'WHERE { ' \
            '   <' + Drone + '>  ?type ?attribute .' \
            '} ' \
            'LIMIT 10')

    #grab the result and find my data
    result = sparql.query('http://ld.landrs.org/query', q)

    #bail if no match
    if not result:
        return

    # loop over rows returned, check for my id
    for row in result:
        values = sparql.unpack_row(row)

        #put data in dictionary
        #NOTE: this is unique so misses multiples!
        if values[0] in drone_dict.keys():
            drone_dict[values[0]].append(values[1])
        else:
            drone_dict.update( {values[0] : [values[1]]} )

    # if I exist find configuration
    print("Found", ontology_myID)

    # get the sensors
    #lets hunt down ispartof parts
    q = ('SELECT ?sub ?h ?x WHERE { ' \
        	'  ?sub <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/ns/sosa/Sensor> .' \
          	'  ?h <http://www.w3.org/ns/sosa/hosts> ?sub .' \
          	'  ?h <http://schema.landrs.org/schema/isPartOf> ?x .' \
          	'  ?x <http://schema.landrs.org/schema/isPartOf> <'+Drone+'> .' \
            '} ')

    #grab the result and find sensors
    result_sensor = sparql.query(ontology_landrs, q)

    # loop over rows returned, check for my id
    for row_sensor in result_sensor:
        values_sensor = sparql.unpack_row(row_sensor)

        #save host/partof in drone data
        if ontology_hosts in drone_dict.keys():
            if values_sensor[1] not in drone_dict[ontology_hosts]:
                drone_dict[ontology_hosts].append(values_sensor[1])
        else:
            drone_dict.update( {ontology_hosts : [values_sensor[1]]} )

        #save host/partof in drone data
        if ontology_parts in drone_dict.keys():
            if values_sensor[2] not in drone_dict[ontology_parts]:
                drone_dict[ontology_parts].append(values_sensor[2])
        else:
            drone_dict.update( {ontology_parts : [values_sensor[2]]} )

        # save host and its partof
        sensor_dict = {ontology_hosts: values_sensor[1], ontology_parts: values_sensor[2]}

        #find sensor data
        q = ('SELECT * ' \
                'WHERE { ' \
                '   <' + values_sensor[0] + '>  ?type ?attribute .' \
                '} ' \
                'LIMIT 10')
        #grab the result and find my sensors
        resultc = sparql.query(ontology_landrs, q)

        # loop over rows returned, check for my id
        for rowc in resultc:
            valuesc = sparql.unpack_row(rowc)
            sensor_dict.update( {valuesc[0] : valuesc[1]} )

        #api counter
        sensor_count = sensor_count + 1

        #anounce sensor
        print("sensor",values_sensor[0])

        #create api endpoint
        app.add_url_rule(
            '/api/v1/sensors/'+values_sensor[0].replace(ontology_prefix, ''), #this is the actual url
            'sensor_' + str(sensor_count) # this is the name used for url_for
        )
        app.view_functions['sensor_' + str(sensor_count)] = sensors

        #save sensor data
        Sensors.append(values_sensor[0].replace(ontology_prefix, ''))

        #save data
        SensorData.append(sensor_dict)

    #add sensors
    drone_dict.update({ ontology_sensors: Sensors})

#####################################
#function to setup swagger 3 headers
#####################################
def swagger_setup(drone_dict):
    drone_dict.update( \
                                { "openapi": "3.0.0", \
                                    "info":{ \
                                          "title": "Priscila's Drone API", \
                                          "description": "Python drone simulation for Knowledge Graph testing.", \
                                          "version": "0.0.1" \
                                    }, \
                                    "servers":{
                                        "url": "http://localhost:5000/api/v1", \
                                        "description": "Flask API running on drone.", \
                                    }, \
                                    "paths":{ \
                                        "/sensors":{ \
                                            "get":{ \
                                                "summary": "Returns a list of sensors.", \
                                                "description": "Sensors hosted on flight controller board.", \
                                                "responses":{ \
                                                    '200': {   # status code \
                                                        "description": "A JSON array of sensor ids", \
                                                        "content":{ \
                                                            "application/json":{ \
                                                                "schema":{ \
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
                                    "basePath": "/api/v1" })

#variables
Drone = ""
Sensors = []
SensorData = []

#openAPI/Swagger headers, https://swagger.io/docs/specification/basic-structure/
drone_dict = {}
sensor_count = 0

#get inline parameter version of myID
if len(sys.argv) < 2:
    print("Please provide a Drone id")
else:
    ontology_myID = sys.argv[1]

#create my api server
app = flask.Flask(__name__)
app.config["DEBUG"] = True

#setup swagger headers
swagger_setup(drone_dict)

#parse the kg on ld.landrs.org
parse_kg()

#setup root
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
    return json.dumps(drone_dict), 200

#setup Sensors
@app.route('/api/v1/sensors', methods=['GET','POST'])
def sensors_list():
    return json.dumps({"sensors": Sensors}), 200

#run the api server
app.run(host='0.0.0.0')
