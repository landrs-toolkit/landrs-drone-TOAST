## Graphs
The TOAST project is based on RDF graphs stored and manipulated via RDFLib https://github.com/RDFLib/rdflib.

### Sources
The main LANDRS Ontology and instances are stored as Turtle files in the working repository https://github.com/landrs-toolkit/landrsOntTest. We are currently using the ```config``` branch for testing TOAST.

### Configuration
The ```py_drone_graph_core.py``` Python file contains the graph initialization code configured via the ```[GRAPH]``` section in ```py_drone.ini```.
```
[GRAPH]
name = landrs_test
db_location = db/${name}

#for Pricila's repo
file = ../landrsOntTest/
#sample file
#file = ttl/base.ttl

file_format = ttl
file_reload = False

# check created instances with pyshacl?
pyshacl = False

# shacl filenames
shacl_filename = *shape.${file_format}
shacl_constraint_filename = *shapes.${file_format}
flight_shacl_filename = ttl/

# ontology filename
ontology_filename = ontology.${file_format}
```

### Storage
The graph interface code resides in the ```graph``` folder of the TOAST repository, utilizing the ```py_drone_graph``` class. 

The graphs are stored in a SQLITE database named as ```db/landrs_test``` and contains the following graphs,
#### Main graphs
1. landrs_test, the main graph containing the ontology and instances from ```landrsOntTest```. Internally named ```g1```.
1. landrs_test_shape, the SHACL shapes from ```landrsOntTest```.  Internally named ```g2```.

#### Configuration graphs
These graphs are populated from the shape files in ```/ttl```. The graph name is defined by the filename up to the collective shape naming convention ```*shapes.${file_format}```. So ```Flight_constraint_shapes.ttl``` -> ```Flight_constraint```.
1. Drone_input, configuration shapes for the drone.
1. Flight_input, shapes that define the flight specific nodes to be created and the "graph boundaries" that require user input to resolve. Used to auto-generate the Flight input form.
1. Flight_constraint, shapes that define constraints for the "graph boundaries". For example the feature of interest must have an observable property and a sensor that can observe it.
1. Flight_store, shapes that define the nodes to be generated/updated during the flight. Includes the observation etc.
1. Sensor_parse, shapes that define the sensor.

#### All graphs
All graphs can also be accessed via the ```Conjunctive``` graph internally named ```g```.

### Loading
If the SQLITE database does not exist then the files are re-loaded into a new database. The turtle files can be reloaded each time the code is run by setting ```file_reload = True```.

### PySHACL
Newly created instances can be rigorously checked against their SHACL files with PySHACL by setting ```pyshacl = True```.
