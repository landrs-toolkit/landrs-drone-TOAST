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

#function to handle queries
def sensors():
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

#an altimiter
# <id/ZmI3YzQ5NzMtMGFhMi00MTNhLWJjNzUtZjBmNmMxNTBkNjA3Cg==> a sosa:Sensor ;
# rdfs:label "MS5611 Altimiter Pressure Sensor" ;
# rdfs:comment "Barometric pressure sensor optimized for altimeters and variometers with an altitude resolution of 10 cm" ;
# schema:sameAs <https://www.te.com/usa-en/product-CAT-BLPS0036.html> ;
# # instanceOf Altimiter
# wdt:P31 wdt:Q216197 ;
# sosa:isHostedBy <id/Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg==> ;
# sosa:observableProperty <http://sweetontology.net/propSpaceHeight/BarometricAltitude> ;
# ssn-system:hasOperatingRange <sensor/35-207306-844818-0/MS5611#AltimiterOperatingRange> .

# the id assigned to this drone
myID = 'Y2E5OTNkM2ItZjg0MS00NjE4LThmZDQtMDBmNzBjMzg0ZTY0' #'Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg=='

#get inline parameter version of myID
if len(sys.argv) < 2:
    print("Please provide a FlightControllerBoard id")
else:
    myID = sys.argv[1]

#create my api server
app = flask.Flask(__name__)
app.config["DEBUG"] = True

#lets look for FlightControllerBoards that may be me
q = ('PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> ' \
        'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>  ' \
        'SELECT * WHERE { ' \
        '    ?sub rdf:type <http://schema.landrs.org/schema/FlightControllerBoard> . ' \
        '}' \
        'LIMIT 10' )

#grab the result and find if I exist
result = sparql.query('http://ld.landrs.org/query', q)

#print(result.variables)
i_exist = False
FlightControllerBoard = ""
Sensors = []
SensorData = []

# loop over rows returned, check for my id
for row in result:
    #print('row:', row)
    values = sparql.unpack_row(row)
    if myID in values[0]:
        #print(values[0])
        i_exist = True
        FlightControllerBoard = values[0]

#dictionary of fc data
flightcontrollerboard_dict = { "drone:FlightControllerBoard": FlightControllerBoard, \
                                "basePath": "/api/v1" }

# if I exist find configuration
if i_exist:
    print("Found FlightControllerBoard", myID)

    #find my sensors
    q = ('PREFIX sosa: <http://www.w3.org/ns/sosa/> ' \
            'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> ' \
            'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> ' \
            'SELECT * ' \
            'WHERE { ' \
            '   <' + FlightControllerBoard + '>  ?type ?attribute .' \
            '} ' \
            'LIMIT 10')
    #grab the result and find my sensors
    result = sparql.query('http://ld.landrs.org/query', q)

    sensor_count = 0

    # loop over rows returned, check for my id
    for row in result:
        values = sparql.unpack_row(row)

        #put data in dictionary
        #NOTE: this is unique so misses multiples!
        if values[0] in flightcontrollerboard_dict.keys():
            #create list if so
            val = flightcontrollerboard_dict[values[0]]
            if isinstance(val, list):
                val.append(values[1])
            else:
                val = [val, values[1]]
            flightcontrollerboard_dict.update( {values[0] : val} )
        else:
            flightcontrollerboard_dict.update( {values[0] : values[1]} )

        #is it sensor?
        if values[0] == "http://www.w3.org/ns/sosa/hosts":
            #find sensor data
            q = ('PREFIX sosa: <http://www.w3.org/ns/sosa/> ' \
                    'PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> ' \
                    'PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> ' \
                    'SELECT * ' \
                    'WHERE { ' \
                    '   <' + values[1] + '>  ?type ?attribute .' \
                    '} ' \
                    'LIMIT 10')
            #grab the result and find my sensors
            resultc = sparql.query('http://ld.landrs.org/query', q)

            sensor_dict = {}

            sensor_type = False

            # loop over rows returned, check for my id
            for rowc in resultc:
                valuesc = sparql.unpack_row(rowc)
                sensor_dict.update( {valuesc[0] : valuesc[1]} )

                if valuesc[0] == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" and valuesc[1] == "http://www.w3.org/ns/sosa/Sensor":
                    sensor_type = True
                print("type ",valuesc[0],"attribute",valuesc[1])

            #check if was sensor, not actuator here
            if sensor_type:
                #api counter
                sensor_count = sensor_count + 1

                print("sensor",values[1])
                app.add_url_rule(
                    '/api/v1/'+values[1].replace('http://ld.landrs.org/id/', ''), #I believe this is the actual url
                    'sensor_' + str(sensor_count) # this is the name used for url_for (from the docs)
                )
                app.view_functions['sensor_' + str(sensor_count)] = sensors

                print("Sensor ",values[1].replace('http://ld.landrs.org/id/', ''))
                Sensors.append(values[1].replace('http://ld.landrs.org/id/', ''))

                #save data
                SensorData.append(sensor_dict)

    #add sensors
    flightcontrollerboard_dict.update({ "sosa:Sensor": Sensors})

#setup root
@app.route('/', methods=['GET'])
def home():
    #Swagger v2.0 uses basePath as the api root
    return json.dumps(flightcontrollerboard_dict), 200

#run the api server
app.run(host='0.0.0.0')
