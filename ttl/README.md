## SHACL Flight/Drone Configuration
This folder contains the SHACL files for configuring ```Flights``` and the drone,

1. ```Flight_input_shapes.ttl```, shapes that define the flight specific nodes to be created and the "graph boundaries" that require user input to resolve. Used to auto-generate the Flight input form.
1. ```Flight_constraint_shapes.ttl```, shapes that define constraints for the "graph boundaries". For example the feature of interest must have an observable property and a sensor that can observe it.
1. ```Flight_store_shapes.ttl```, shapes that define the nodes to be generated/updated during the flight. Includes the observation etc.
1. ```Sensor_parse_shapes.ttl```, shapes that define the sensor.
1. ```Drone_input_shapes.ttl```, shapes required for drone configuration.

### The Problem
Using Knowledge Graphs to configure the data acquisition section of scientific drones provides the opportunity to provide both context to the data and allow constraints to be applied to the data to make sure the correct relationships are adhered to. 

When implementing Knowledge Graphs in a drone environment it is tempting to hard code the graph directly using RDFLib. While this is straightforward, any changes to the knowledge graph will require code updates to mirror the change. This is particularly problematic when implementing immature ontologies such as LANDRS where rapid changes by the knowledge engineers would need to be followed by the software engineers.

### SHACL to the rescue
The Shapes Constraint Language (SHACL) is a language for validating RDF graphs against a set of conditions and can be used to validate graph implementations (i.e. the edge relationships are correct and there are the right number of them). It is also possible to use shape files as a prior to ensure compliance, and this has seen increased use in generating input forms that yield correctly formed data for generating graph node instances. 

### Concept
The LANDRS DroneDataBuddy software will be implemented as a thin layer between the drone hardware and the knowledge graphs. i.e. the code will be "knowledge graph agnostic" but provide the following abilities,
* auto-generate input forms for the user to configure the drone data acquisition process (i.e. set up missions)
* collect drone generated data and push to a compliant storage graph, or other "semantically" defined storage method.

We will use SHACL shape files to provide the graph agnostic functionality, it should be possible to change the knowledge graph/SHACL without updating the software. See figure below.

![Graph](https://raw.githubusercontent.com/wiki/landrs-toolkit/landrs-drone-TOAST/images/SHACL-TOAST.png)

### Implementation
We will provide the example of implementing the KG for a flight/mission. This will have the following stages,
1. Form input for flight/mission generation, the user will be presented with a auto-generated form to populate with the required flight information
1. The flight, the drone will acquire data such as GPS, CO2 readings etc. which must be stored in a context compliant manner
1. Post flight finalization, after the flight the data must be updated with end times and added to data collections etc.

Each of these stages are documented below.

#### Form input for flight/mission generation
There are a number of problems to consider
1. Graph nodes will be partially configured, for example start and end times will not be known
1. We need to generate the relevant graph node instances for the flight. however these nodes need to connect to existing node instances of the KG, I have termed this the "boundary graph"

#### Approach
##### Form
I have created a separate Shape graph (you can find it here https://github.com/landrs-toolkit/landrs-drone-TOAST/blob/master/ttl/flight_shapes.ttl) to define the required nodes and the mandatory edges, and labeled the SHACL nodes as ```Flight_shape```. e.g.
```
landrs:Flight_ObservationCollectionShape
    a sh:NodeShape ;
    sh:targetClass sosa:ObservationCollection ;
    rdfs:label 'Flight_shape' ;
sh:property [
    sh:path prov:wasInformedBy ;
    sh:nodeKind sh:IRI ;
    sh:class landrs:Flight ;
    sh:severity sh:Violation ;
    sh:minCount 1 ;
    sh:maxCount 1 ;
    sh:severity sh:Violation ;
] ...
```

I have labeled edges (defined by a ```sh:property```) that connect to "boundary nodes" with ```rdfs:label 'graph_boundary'```, e.g.
```
sh:property [
    sh:path rdfs:label ;
    sh:name 'flight_collection' ;
    sh:datatype xsd:string ;
    rdfs:label 'graph_boundary' ;
    sh:description 'Flight collection name' ;
    sh:defaultValue  '$flight_name,flight_collection' ;
    sh:minCount 1 ;
    sh:maxCount 1 ;
    sh:severity sh:Violation ;
] ;
```
To determine the form inputs we just parse the graph for ```graph_boundary``` properties. The form can then be generated according to the type. e.g. ```sh:datatype xsd:string``` will generate a text box for input, ```sh:class sosa:ObservableProperty``` will generate an option list of available Observable Properties etc. We use ```sh:order``` to order the form elements and can have defaults using ```sh:defaultValue```.

There are a couple of enhancements, for example we need a mission file that we use to extract a geometry for the flight. This would work with a text input but is a poor user experience as you need to know the file location, we need an option box. I introduced a set of reserved keywords. In the software config. (ini) file,
```
mission_file = ../ardupilot/Tools/autotest/ArduPlane_Tests/Mission/
mission_file_mode = FILES
```
which matches SHACL,
```
sh:property [
    sh:path ssn:hasInput ;
    sh:name "mission_file" ;   
    sh:datatype xsd:string ;
    rdfs:label 'graph_boundary' ;
    sh:description 'Select mission file' ;
    sh:defaultValue '../ardupilot/Tools/autotest/ArduPlane_Tests/Mission/CMAC-soar.txt' ;
    sh:minCount 1 ;
    sh:maxCount 1 ;
    sh:severity sh:Violation ;
    sh:order 2 ;
] ;
```
In this case when we see a ```sh:name``` is a reserved keyword we look for its MODE and then change the form accordingly. We notice that we used ```sh:defaultValue``` to define our preferred file and the ini entry gives the file location to search for files.

A simpler case is just substitution, where we have ```sh:defaultValue  '$flight_name,flight_collection'``` that matches ```flight_name_substutute = flight_name``` in the ini file we substitute the user selected flight name for ```$flight_name```.

![Form screen](https://raw.githubusercontent.com/wiki/landrs-toolkit/landrs-drone-TOAST/images/Form_screen.png)

##### Form data validation
The input form data has constraints, e.g.
* the Observable Property must be property of the selected FeatureOfInterest
* the Sensor must have ```observes``` for the selected ObservableProperty

We have a separate SHACL graph (SHACL nodes labeled ```Flight_constraint```) to perform this and inform the user of any errors. e.g. for Observable Property,
```
landrs:Flight_ObservablePropertyShape
    a sh:NodeShape ;
    sh:targetClass sosa:ObservableProperty ;
    rdfs:label 'Flight_constraint' ;
sh:property [
    sh:path ssn:isPropertyOf ;
    sh:nodeKind sh:IRI ;
    sh:class sosa:FeatureOfInterest ;
    sh:minCount 1 ;
    sh:maxCount 1 ;
    sh:severity sh:Violation ;
] .
```

##### Node creation
Once the form has been returned with the boundary data, and validated, we can generate the KG instances. The process is,
1. Create a Python list of the boundary class instances from the form
1. From the SHACL graph add the required class instances to this list
1. Call a recursive function that runs through the list, creates instances where required and then adds the edges to this instances (creating the target class instance where required, hence the recursion)
1. Collect graph metadata on edges related to storing sensor values and append to the ```ini``` file

By following this process the software only needs to assume that there is a sensor and some sort of collection object as follows,
1. the label for the Observation Collection, but not its type 
1. the selected sensor id, again its type and other information is not required. At some point it would be noice to include data like its interface (```i2c```?) etc.

This gets passed on to the storage function, described below.

#### Storage of data during flight
We follow a similar process for data storage, for each sensor we need (our boundary graph)
* a quantity, e.g. CO2 PPM (random data but should read the sensor)
* a GPS fix for the quantity (from MavLink)
* the quantity units (from the ini file, see below)
* a timestamp (from the Raspberry Pi)

During the configuration above in Section ```Node creation```, we automatically append graph metadata information on each of these to the ini file,
```
[STORE]
collection_type = http://www.w3.org/ns/sosa/ObservationCollection
starttime = http://www.w3.org/2001/XMLSchema#dateTime
sensor_type = http://schema.landrs.org/schema/Sensor
observation_result_quantity = http://www.w3.org/2001/XMLSchema#double
observation_result_quantity_unit = http://qudt.org/2.1/vocab/unit#PPM
observation_result_quantity_geo_fix = http://www.opengis.net/ont/geosparql#wktLiteral
```
Given the collection and sensor instance ids we can,
1. generate a Python list of boundary graph types using GPS, sensor reading and the ```[STORE]``` data entries above
1. From a new "storage" SHACL graph (SHACL nodes labeled ```Store_shape ```) add the required class instances to this list
1. Call a recursive function that runs through the list, creates instances where required and then adds the edges to this instances (creating the target class instance where required, hence the recursion)

Actual example,
```
@base <http://127.0.0.1:5000/> .
@prefix geosparql: <http://www.opengis.net/ont/geosparql#> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix qudt-1-1: <http://qudt.org/2.1/schema/qudt#> .
@prefix qudt-unit-2-1: <http://qudt.org/2.1/vocab/unit#> .
@prefix sosa: <http://www.w3.org/ns/sosa/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<id/tKHkaM_TR-KrrSWBfNbLSw> a sosa:ObservationCollection ;
    prov:endedAtTime "2020-08-13T15:22:59.291394"^^xsd:dateTime ;
    prov:startedAtTime "2020-08-13T15:22:36.925123"^^xsd:dateTime ;
    sosa:hasMember <id/F1h_LAszQJOnl8TB6WIXew>,
        <id/g0jkmW1dSFWspuG5c89bXA>,
        <id/hbubL-TXRXqRhkn89P86Pw> ;
    sosa:madeBySensor <id/CfJDfMLMTu2ZcfMcGADlYg> .

<id/F1h_LAszQJOnl8TB6WIXew> a sosa:Observation ;
    sosa:hasResult [ a qudt-1-1:QuantityValue ;
            qudt-1-1:numericValue 4.331e+02 ;
            qudt-1-1:unit qudt-unit-2-1:PPM ;
            geosparql:hasGeometry [ a geosparql:Geometry ;
                    geosparql:asWKT "POINT(-35.363262299999995 149.1652378 584.1)"^^geosparql:wktLiteral ] ] ;
    sosa:madeBySensor <id/CfJDfMLMTu2ZcfMcGADlYg> ;
    sosa:resultTime [ a xsd:dateTime ;
            xsd:dateTimeStamp "2020-08-13T15:22:46.942278"^^xsd:dateTime ] .

<id/g0jkmW1dSFWspuG5c89bXA> a sosa:Observation ;
    sosa:hasResult [ a qudt-1-1:QuantityValue ;
            qudt-1-1:numericValue 4.417e+02 ;
            qudt-1-1:unit qudt-unit-2-1:PPM ;
            geosparql:hasGeometry [ a geosparql:Geometry ;
                    geosparql:asWKT "POINT(-35.363262399999996 149.1652378 584.0500000000001)"^^geosparql:wktLiteral ] ] ;
    sosa:madeBySensor <id/CfJDfMLMTu2ZcfMcGADlYg> ;
    sosa:resultTime [ a xsd:dateTime ;
            xsd:dateTimeStamp "2020-08-13T15:22:56.851911"^^xsd:dateTime ] .

<id/hbubL-TXRXqRhkn89P86Pw> a sosa:Observation ;
    sosa:hasResult [ a qudt-1-1:QuantityValue ;
            qudt-1-1:numericValue 3.722e+02 ;
            qudt-1-1:unit qudt-unit-2-1:PPM ;
            geosparql:hasGeometry [ a geosparql:Geometry ;
                    geosparql:asWKT "POINT(-35.363262299999995 149.1652377 584.0)"^^geosparql:wktLiteral ] ] ;
    sosa:madeBySensor <id/CfJDfMLMTu2ZcfMcGADlYg> ;
    sosa:resultTime [ a xsd:dateTime ;
            xsd:dateTimeStamp "2020-08-13T15:22:36.925123"^^xsd:dateTime ] .
```
#### Post flight operations
Once the flight is complete we need to do the following,
1. Update various instances with the end time/date
1. Add the dataset to the data service (work in progress)

Again we follow exactly the same procedure as in the previous sections
1. generate a Python list of boundary graph types such as end time
1. From a new "end of storage" SHACL graph (SHACL nodes labeled ```Store_shape_end```) add the required class instances to this list (including those to be updated like the collection)
1. Call a recursive function that runs through the list, creates instances where required and then adds the edges to this instances (creating the target class instance where required, hence the recursion)
#### Knowledge Graph
![KG](https://raw.githubusercontent.com/wiki/landrs-toolkit/landrs-drone-TOAST/images/New_Flight.png)
Key,
1. Purple nodes are prerequisites for flights.
1. Yellow nodes get created during the flight
1. Red nodes need to be created before the flight with partial data
1. Orange nodes, need to be created after the flight
1. Grey nodes, inheritance only
1. Green node, the GCS file, not really a node. 

### Appendix
The recursion (https://github.com/landrs-toolkit/landrs-drone-TOAST/blob/master/graph/py_drone_graph_store.py#L215), note this is at an early stage. Will add functionality as required.
```
    #################################################
    # Populate an instance of a graph
    #################################################
    def populate_instance(self, shape_target, blankNode, flight_shape, dict_of_nodes, graph, populate_all):
        '''
        Args:
            shape_target (URIRef):  target class to create
            flight_shape (dict.):   dictionary of shape dictionaries
            dict_of_nodes (dict.):  dictionary of nodes related to/part of flight

        Returns:
           URIRef: the created node URIRef
        '''
        # get shape for shape_target class
        shape = flight_shape[shape_target]

        # find target class
        target_class = shape['target_class']
        # print(shape['target_class'])

        # does it exist? then return uri
        if URIRef(target_class) in dict_of_nodes.keys():
            if not populate_all:
                return dict_of_nodes[URIRef(target_class)]
            else:
                oc_node = dict_of_nodes[URIRef(target_class)]
        else:
            if blankNode:
                oc_node = BNode()
            else:
                # new uuid
                oc_id = self.generate_uuid()

                # create new node in graph
                oc_node = self.BASE.term(oc_id)

            graph.add((oc_node, RDF.type, target_class))

            # add to dictionary of created nodes
            dict_of_nodes.update({target_class: oc_node})

        # loop over proberties defined in shape
        for property in shape['properties']:
            # deal with strings?
            if 'datatype' in property.keys():
                ##print(property['datatype'], property['path'], property['name'])

                # check if maxcount or if under maxcount
                if 'maxCount' not in property.keys() or len(list(graph.objects(oc_node, URIRef(property['path'])))) < int(property['maxCount']):
                    # if OK update
                    if property['datatype'] == str(XSD.string):
                        graph.add((oc_node, URIRef(property['path']), Literal(
                            dict_of_nodes[property['name']])))
                    else:
                        graph.add(
                            (oc_node, URIRef(property['path']), dict_of_nodes[property['name']]))

            # deal with sh:nodeKind sh:IRI
            if 'nodeKind' in property.keys():
                if property['nodeKind'] == str(SH.IRI) or property['nodeKind'] == str(SH.BlankNode):
                    # print(property['nodeKind'])
                    # Example, 'path': 'http://www.w3.org/ns/sosa/madeBySensor', 'class': 'http://www.w3.org/ns/sosa/Sensor',
                    if URIRef(property['class']) in dict_of_nodes.keys():
                        #print("Class", property['class'])
                        graph.add(
                            (oc_node, URIRef(property['path']), dict_of_nodes[URIRef(property['class'])]))
                    else:
                        #print("Not found", property['class'], property['path'])

                        if property['nodeKind'] == str(SH.BlankNode):
                            blanknode = True
                        else:
                            blanknode = False
                        # create missing class instance recursively
                        new_node = self.populate_instance(URIRef(
                            property['class']), blanknode, flight_shape, dict_of_nodes, graph, populate_all)
                        if new_node:
                            # add to dictionary of created nodes
                            dict_of_nodes.update(
                                {URIRef(property['class']): new_node})

                            # add to graph
                            graph.add(
                                (oc_node, URIRef(property['path']), new_node))

        # return node
        return oc_node
```

