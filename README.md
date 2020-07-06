# py_drone_simulator

Python LANDRS Drone simulator designed to enable testing of scenarios on the evolving LANDRS drone ontology/knowledge graphs and provide a test platform for drone interfaces.
Planned enhancements,
* generate a hydra http://www.hydra-cg.com compliant api.
* emulate flights to generate data.
* Add endpoint to set/get drone configuration.

Versions,
1. py_drone_simulator.py, sparql queries using rdflib and local base.ttl file
2. py_drone_simulator_ld_landrs.py, sparql queries on ld.landrs.org

### Using the simulator
The program uses a configuration file (py_drone.ini) to select parameters such as the uuid of the drone, source of the turtle files to load initially etc.
Typical values for uuid and .ttl location,
```
[DRONE]
drone_uuid = MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==

[GRAPH]
file = ../landrsOntTest/
```
where ../landrsOntTest/ represents the current LANDRS test KG at https://github.com/landrs-toolkit/landrsOntTest.
To run,
```
python3 py_drone_simulator.py
```
this will parse the graph for for UAV (drone) MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg== and setup an api on port 5000. It will also load the ttl files from ../landrsOntTest.

Accessing ```/```, ```/api``` or ```/api/v1```
```
http://localhost:5000/
```
returns
```json
{
    "openapi": "3.0.0",
    "info": {
        "title": "Priscila's Drone API",
        "description": "Python drone simulation for Knowledge Graph testing.",
        "version": "0.0.1"
    },
    "servers": {
        "url": "http://localhost:5000/api/v1",
        "description": "Flask API running on drone."
    },
    "paths": {
        "/sensors": {
            "get": {
                "summary": "Returns a list of sensors.",
                "description": "Sensors hosted on flight controller board.",
                "responses": {
                    "200": {
                        "description": "A JSON array of sensor ids",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    },
    "basePath": "/api/v1",
    "http://schema.landrs.org/FlightControllerBoard": "http://ld.landrs.org/id/Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg==",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type": [
        "http://www.w3.org/2000/01/rdf-schema#Resource",
        "http://schema.org/Thing",
        "http://www.w3.org/ns/sosa/system",
        "http://schema.landrs.org/schema/FlightControllerBoard",
        "http://schema.landrs.org/schema/Product",
        "http://schema.landrs.org/schema/Thing"
    ],
    "http://www.w3.org/ns/sosa/hosts": [
        "http://ld.landrs.org/id/MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==",
        "http://ld.landrs.org/id/Y2U1YThiZTYtZTljMC00ZWY3LTlmMzItZGZhZDk4MTJkNDExCg==",
        "http://ld.landrs.org/id/OTNkMDI1YTctZGE4Ny00Y2IyLWI3MzgtMTU2YzVmMDU1MDI4Cg=="
    ],
    "http://www.wikidata.org/prop/direct/P31": "http://www.wikidata.org/entity/Q220858",
    "http://www.w3.org/ns/sosa/Sensor": [
        "MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==",
        "Y2U1YThiZTYtZTljMC00ZWY3LTlmMzItZGZhZDk4MTJkNDExCg=="
    ]
}
```
which lists the 2 sensors. To look directly at the sensor list,
```
http://localhost:5000/api/v1/sensors
```
yeilds,
```json
{
    "sensors": [
        "MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==",
        "Y2U1YThiZTYtZTljMC00ZWY3LTlmMzItZGZhZDk4MTJkNDExCg=="
    ]
}
```

To view a sensor,
```
http://localhost:5000/api/v1/sensors/MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==
```
returns,
```json
{
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type": "http://www.w3.org/ns/sosa/Sensor",
    "http://www.w3.org/2000/01/rdf-schema#label": "iSentek Three-axis Magnetometer",
    "http://www.w3.org/2000/01/rdf-schema#comment": "iSentek’s three-axis magnetometers use anisotropic magneto resistance (AMR)technology. They offer high spatial resolution, high precision and low power consumption performance. ",
    "http://schema.org/sameAs": "http://www.isentek.com/en/the_product.php?pid=4",
    "http://www.wikidata.org/prop/direct/P31": "http://www.wikidata.org/entity/Q333921",
    "http://www.w3.org/ns/sosa/isHostedBy": "http://ld.landrs.org/id/Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg==",
    "http://www.w3.org/ns/sosa/observableProperty": "http://sweetontology.net/propSpaceLocation/Position"
}
```

### Available endpoints
* ```/sparql``` The drone hosts a yasgui SPARQL editor webpage here, pointed to the endpoint below. Allows insert as well as query.
* ```/api/v1/sparql``` The actual query endpoint. Allows insert as well as query.
* ```/api/v1/turtle/FILENAME``` download a turtle file of the entire graph to FILENAME.
* ```/api/v1/store/OBSERVATIONCOLLECTION/OBSERVATION>``` save a random value, with timestamp 'now' to OBSERVATION in OBSERVATIONCOLLECTION. * creates OBSERVATIONCOLLECTION.
* ```/api/v1/id/uuid``` retrive information on a uuid.
* ```/api/v1/sensors/uuid``` retrive information on a sensor by uuid.
* ```/api/v1/sensors``` get a list of sensor uuids.
* ```/api/v1``` get this drone information and some (now outdated) openAPI information.

### Other information
1. Uses SQLite database via SQLAlchemy.

