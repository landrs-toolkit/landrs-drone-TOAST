'''
Graph Class for simple drone emulator that,
1) takes an id
2) queries ld.landers.org to find its configuration OR
2) Loads a set of ttl files and runs sparql queries locally
3) generates an API for access to sensor data
4) provides other functionality in support of Landrs development.

Chris Sweet 07/02/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

This code provides py_drone_graph, the class for acessing and manipulating
the rdf graph.
'''

# Imports ######################################################################
import json
import os
import base64
import uuid
import logging

# RDFLIB
import rdflib
from rdflib.serializer import Serializer
from rdflib import plugin, Graph, Literal, URIRef, BNode
from rdflib.store import Store
from rdflib.plugins.sparql.processor import processUpdate
from SPARQLWrapper import SPARQLWrapper, JSON
from rdflib.graph import Graph, ConjunctiveGraph

# my imports
from graph.py_drone_graph_core import py_drone_graph_core, LANDRS, LDLBASE
from graph.py_drone_graph_core import SOSA, QUDT_UNIT, QUDT, GEO, RDFG, \
        ontology_landrs, ontology_myID

# namespaces from rdflib
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
    PROF, PROV, RDF, RDFS, SDO, SH, SKOS, TIME, \
    VOID, XMLNS, XSD

# namespaces not pre-defined
GEOSPARQL = rdflib.Namespace("http://www.opengis.net/ont/geosparql#")
LOCN = rdflib.Namespace("http://www.w3.org/ns/locn#")
SCHEMA = rdflib.Namespace("http://schema.org/")
DCT = rdflib.Namespace("http://purl.org/dc/terms/")
SSN = rdflib.Namespace("http://www.w3.org/ns/ssn/")

# setup logging ################################################################
logger = logging.getLogger(__name__)

################################################################################
# Class to house rdf graph storage functions for drone
################################################################################


class py_drone_graph_store():
    '''
    sample instantiation,
    d_graph = ldg.py_drone_graph(ontology_myID, load_graph_file)
    where,
    1. ontology_myID, uuid for this drone
      e.g. "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="
    2. load_graph_file, turtle file or (folder) for db initialization
      e.g. base.ttl

    has the following sections,
    1. data storage support functions
    '''

    # data storage support functions ###########################################

    #################################################
    # store data for sensor, creates SOSA.Observation
    #################################################
    def store_data_point(self, collection_id, sensor_id, values):
        '''
        Args:
            collection_id (str):    uuid for observation collection
                                    '*' to create new
            sensor_id (str):        uuid for sensor to associate data
            value (str):            dictionary values to store
            time_stamp (str):       time stamp to store

        Returns:
           dict.: query result
        '''
        # figure out what data we have to store
        type = ''
        value = '0'
        # check type
        if 'type' in values.keys():
            if values['type'] == 'co2':
                value = values['co2']
                type = 'co2'
            if values['type'] == 'gps':
                value = values['alt']
                type = 'gps'
        else:
            ret = {"status": False}
            return

        # check timestamp
        if 'time_stamp' in values.keys():
            time_stamp = values['time_stamp']
        else:
            ret = {"status": False}
            return

        # add data to return
        ret = {"id": sensor_id, "value": value,
               "time_stamp": time_stamp, "type": values['type']}

        # find sensor type
        sensor_type = self.g_config.value(LANDRS.Store_SensorShape, SH.targetClass)

        # check it is a sensor, from ld.landres.org?
        sensor_id_node = self.find_node_from_uuid(sensor_id, sensor_type)
        if not sensor_id_node:
            ret.update({"status": False, "error": "sensor not found."})
            return ret

        # check if collection exists
        # if collection_id is '*' then create a new one
        collection_id_node = LDLBASE.term(
            collection_id)  # from ld.landres.org?

        # find collection type
        collection_type = self.g_config.value(LANDRS.Store_ObservationCollectionShape, SH.targetClass)

        # create?
        if collection_id != '*':
            collection_id_node = self.find_node_from_uuid(collection_id, collection_type)
            if not collection_id_node:
                ret.update({"status": False, "error": "collection not found."})
                return ret

            # if we get here find or create graph to store
            graph = self.observation_collection_graph(collection_id, collection_type)
        else:  # collection_id is '*'
            # find existing graph associated with obs. coll. or create
            # new uuid
            collection_id = self.generate_uuid()
            ret.update({"collection uuid": collection_id})

            # create new node in graph
            collection_id_node = self.BASE.term(collection_id)
            # TODO: do we nned to add to both graphs?
            self.g1.add((collection_id_node, RDF.type, collection_type))
            self.g1.add((collection_id_node, RDFS.label,
                         Literal("Drone data collection")))

            # create new graph 
            graph = self.observation_collection_graph(collection_id, collection_type)
            # now auto-adds obs_col to new graph

        # store data
        # new uuid
        id = self.generate_uuid()
        ret.update({"uuid": id})

        # create new node in graph
        the_node = self.BASE.term(id)

        # get type
        observation_type = self.g_config.value(LANDRS.Store_ObservationShape, SH.targetClass)
 
        # create
        graph.add((the_node, RDF.type, observation_type))

        # get shape for shape_target class
        shape = self.get_shape(LANDRS.Store_ObservationShape)

        # loop over properties defined in shape, get sensor predicate
        sensor_pred = None
        for property in shape['properties']:
            # sensor?
            if URIRef(property['class']) == sensor_type: #self.g1.value(sensor_id_node, RDF.type):
                sensor_pred = URIRef(property['path'])
        
        # did we get it?
        if not sensor_pred:
            ret.update({"status": False, "error": "could not find Observation data."})
            return ret

        # add data
        graph.add((the_node, sensor_pred, sensor_id_node))

        # sosa:hasResult
        hasResult = BNode()
        # gps data?
        if type == 'gps':
            graph.add((hasResult, RDF.type, GEO.Point))
            graph.add((hasResult, GEO.lat, Literal(
                values['lat'], datatype=XSD.decimal)))
            graph.add((hasResult, GEO.long, Literal(
                values['lon'], datatype=XSD.decimal)))
            graph.add((hasResult, GEO.alt, Literal(
                values['alt'], datatype=XSD.decimal)))
        else:
            # then co2
            graph.add((hasResult, RDF.type, QUDT.QuantityValue))
            graph.add((hasResult, QUDT.numericValue, Literal(value)))
            graph.add((hasResult, QUDT.unit, QUDT_UNIT.PPM))

        graph.add((the_node, SOSA.hasResult, hasResult))
        # self.g.add((the_node, SOSA.hasResult, Literal(QUDT.QuantityValue, datatype = RDF.type)))
        # self.g.add((the_node, SOSA.hasResult, Literal(value, datatype = QUDT.numericValue)))
        # self.g.add((the_node, SOSA.hasResult, Literal(QUDT_UNIT.PPM, datatype = QUDT.unit)))
        # sosa:resultTime
        resultTime = BNode()
        graph.add((resultTime, RDF.type, XSD.dateTime))
        graph.add((resultTime, XSD.dateTimeStamp, Literal(time_stamp)))

        graph.add((the_node, SOSA.resultTime, resultTime))
        # self.g.add((the_node, SOSA.resultTime, Literal(XSD.dateTime, datatype = RDF.type)))
        # self.g.add((the_node, SOSA.resultTime, Literal(time_stamp, datatype = XSD.dateTimeStamp)))
        # TODO: test to see if we need common value for collection
        #self.g.add((the_node, SOSA.hasFeatureOfInterest, Literal("house/134/kitchen")))

        # add data point id to collection
        date_time_now = Literal(time_stamp, datatype = XSD.dateTime)

        # get shape for shape_target class
        shape = self.get_shape(LANDRS.Store_ObservationCollectionShape)

        # loop over properties defined in shape
        for property in shape['properties']:
            # observation?
            if URIRef(property['class']) == graph.value(the_node, RDF.type):
                # store
                graph.add((collection_id_node, URIRef(property['path']), the_node))

            # time?
            if URIRef(property['class']) == XSD.dateTime:
                # start
                if property['label'] == 'start_time':
                    # check for start time
                    if (collection_id_node, URIRef(property['path']), None) not in graph:
                        graph.add((collection_id_node, URIRef(property['path']), date_time_now))

                # end?
                if property['label'] == 'end_time':
                    # add as end time, will keep getting updated
                    graph.set((collection_id_node, URIRef(property['path']), date_time_now))

        # return success
        ret.update({"status": True})
        return ret

    # flight creation support functions (graph) ################################

    #################################################
    # get instances and their labels
    #################################################
    def get_labeled_instances(self, type):
        '''
        Returns:
           list: OPs found
        '''
        # create list
        instances = []
        # exist?
        for s in self.g1.subjects(RDF.type, URIRef(type)):
            label = self.g1.value(s, RDFS.label)
            if label:
                instances.append({ "uri": str(s), "label": str(label) })
            else:
                instances.append({ "uri": str(s), "label": str(s) })

        # return list
        return instances

    # #################################################
    # # get the Observable Properties and their labels
    # #################################################
    # def get_observable_Properties(self):
    #     '''
    #     Returns:
    #        list: OPs found
    #     '''
    #     # create list
    #     instances = []
    #     # exist?
    #     for s in self.g1.subjects(RDF.type, SOSA.ObservableProperty):
    #         instances.append({ "uri": str(s), "label": str(self.g1.value(s, RDFS.label)) })

    #     # return list
    #     return instances

    # #################################################
    # # get the sensor for a given OP
    # #################################################
    # def get_sensor_for_obs_prop(self, obs_prop):
    #     '''
    #     Args:
    #         obs_prop (str): OP uri

    #     Returns:
    #        list: sensors found
    #     '''
    #     # create list
    #     instances = []
    #     # exist?
    #     for s in self.g1.subjects(SOSA.observes, URIRef(obs_prop)):
    #         instances.append(str(s))

    #     # return list
    #     return instances

    # #################################################
    # # get the pilots and their names
    # #################################################
    # def get_pilots(self):
    #     '''
    #     Returns:
    #        list: pilots found
    #     '''
    #     # create list
    #     instances = []
    #     # exist?
    #     for s in self.g1.subjects(RDF.type, PROV.Agent):
    #         name = self.g1.value(s, FOAF.givenName)
    #         if name:
    #             instances.append( { "uri": str(s), "label": str(name) } )

    #     # return list
    #     return instances

    #################################################
    # Populate an instance of a graph
    #################################################
    def populate_instance(self, shape_target, flight_shape, dict_of_nodes):
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
        print(shape['target_class'])

        # does it exist? then return uri
        if URIRef(target_class) in dict_of_nodes.keys():
            return dict_of_nodes[URIRef(target_class)]

        # new uuid
        oc_id = self.generate_uuid()

        # create new node in graph
        oc_node = self.BASE.term(oc_id)
        self.g1.add((oc_node, RDF.type, target_class ))

        # add to dictionary of created nodes
        dict_of_nodes.update({target_class: oc_node})

        # loop over proberties defined in shape
        for property in shape['properties']:
            # deal with strings?
            if 'datatype' in property.keys():
                if property['datatype'] == str(XSD.string):
                    print(property['datatype'])
                    self.g1.add((oc_node, URIRef(property['path']), Literal(dict_of_nodes[property['name']]))) 

            # deal with sh:nodeKind sh:IRI
            if 'nodeKind' in property.keys():
                if property['nodeKind'] == str(SH.IRI):
                    print(property['nodeKind'])
                    # Example, 'path': 'http://www.w3.org/ns/sosa/madeBySensor', 'class': 'http://www.w3.org/ns/sosa/Sensor',
                    if URIRef(property['class']) in dict_of_nodes.keys():
                        print("Class", property['class'])
                        self.g1.add((oc_node, URIRef(property['path']), dict_of_nodes[URIRef(property['class'])])) 
                    else:
                        print("Not found", property['class'], property['path'])

                        # create missing class instance recursively
                        new_node = self.populate_instance(URIRef(property['class']), flight_shape, dict_of_nodes)
                        if new_node:
                            # add to dictionary of created nodes
                            dict_of_nodes.update({URIRef(property['class']): new_node})

                            # add to graph
                            self.g1.add((oc_node, URIRef(property['path']), new_node )) 

        # return node
        return oc_node

    #################################################
    # Get all flight shacl shapes
    #################################################
    def get_flight_shapes(self):
        '''
        Returns:
           dict.: dictionary of shapes
        '''
        # get shapes #################################################################
        flight_shapes = {}
        # get sh:NodeShape
        shapes = self.g_config.subjects(RDF.type, SH.NodeShape)
        for ashape in shapes:
            # we labeled the shapes of interest Flight_shape
            if self.g_config.value(ashape, RDFS.label) == Literal('Flight_shape'):
                # find target class
                shape_dict = self.get_shape(ashape)
                shape_target_class = shape_dict['target_class']

                flight_shapes.update( { shape_target_class: shape_dict } )

        # return the shapes
        return flight_shapes

    #################################################
    # Create all class instances for a flight
    #################################################
    def create_flight(self, dict_of_nodes):
        '''
        Args:
            dict_of_nodes (dict.):  dictionary of the boundary instances 
                                    required to setup flight

        Returns:
           str: Obsevation Collection id, Flight id
        '''
        # get shapes #################################################################
        flight_shapes = self.get_flight_shapes()

        # required returns
        oc_id = None
        flt_id = None

        # did we get any?
        if len(flight_shapes) == 0:
            print("No flight shapes")
            return oc_id, flt_id

        # create ObservationCollection and other class instances ######################
        for shape_target in flight_shapes.keys():
            print("shape target", shape_target)
            # populate
            oc_node = self.populate_instance(shape_target, flight_shapes, dict_of_nodes)

            # we need the Observation Collection id for mavlink
            #TODO get type from shacl
            obs_coll_type = self.g_config.value(LANDRS.Flight_ObservationCollectionShape, SH.targetClass)
            # is it obs_col?
            if shape_target == obs_coll_type: #SOSA.ObservationCollection:
                str_node = str(oc_node)
                # strip uri part
                pos = str_node.rfind('/')
                if pos > 0:
                    oc_id = str_node[pos + 1:len(str_node)]

            # we need the Flight id for mavlink
            #TODO get type from shacl
            flight_type = self.g_config.value(LANDRS.Flight_FlightShape, SH.targetClass)
            # is it flight_type?
            if shape_target == flight_type: #LANDRS.Flight:
                str_node = str(oc_node)
                # strip uri part
                pos = str_node.rfind('/')
                if pos > 0:
                    flt_id = str_node[pos + 1:len(str_node)]

        #print("DICT", dict_of_nodes)

        # now setup MavLink for the correct obs_prop and sensor
        return oc_id, flt_id

    ######################################################
    # Get unsatisfied requirements from flight shacl file
    ######################################################
    def flight_shacl_requirements(self, flight_dict):
        # get shapes #############################################
        flight_shapes = self.get_flight_shapes()

        # parse shapes for graph boundaries #
        boundarys = []

        # loop
        for shape_target in flight_shapes.keys():
            #print("shape target", shape_target)
            shape = flight_shapes[shape_target]

            # loop over proberties defined in shape
            for property in shape['properties']:

                # deal with strings?
                if 'label' in property.keys() and 'name' in property.keys():
                    prop_dict = {'name': property['name']}
                    order = 100
                    if 'order' in property.keys():
                        if property['order'] == None:
                            prop_dict.update( {'order': 100} )
                        else:
                            order = int(property['order'])
                            prop_dict.update( {'order': int(property['order'])} )
                    if 'datatype' in property.keys():
                        prop_dict.update( {'datatype': property['datatype']} )
                    if 'class' in property.keys():
                        prop_dict.update( {'class': property['class']} )
                    if 'description' in property.keys():
                        prop_dict.update( {'description': property['description']} )
                    if 'defaultValue' in property.keys():
                        prop_dict.update( {'defaultValue': property['defaultValue']} )

                    # substitutions from ini file?
                    if property['name'] in flight_dict.keys():
                        mode = flight_dict.get(property['name'] + '_mode', 'None')

                        # substitute mode
                        if mode == 'SUBSTITUTE':
                            prop_dict.update( {'defaultValue': flight_dict[property['name']]} )

                        # files mode
                        if mode == 'FILES':
                            files = self.get_files_list(flight_dict.get(property['name'], './'))
                            prop_dict.update( {'in': files} )

                    # add dictionary
                    if order < 100:
                        # add instances if class
                        if 'class' in prop_dict.keys():
                            inst = self.get_labeled_instances(prop_dict['class'])
                            prop_dict.update( {'in': inst} )
                        # add to list
                        if prop_dict not in boundarys:
                            boundarys.append(prop_dict)
                    else:
                        if prop_dict not in boundarys:
                            boundarys.append(prop_dict)
        # sort
        boundarys = sorted(boundarys, key = lambda i: i['order']) 

        # print
        # for boundary in boundarys:
        #     print(boundary)

        # reurn lists of requirements for the form
        return boundarys

    # flight creation support functions (interface) ############################

    #################################################
    # get a list of possible mission files
    #################################################
    def get_files_list(self, mission_files):
        '''
         Args:
            mission_files (str):   location of mission files
         Returns:
           list: missions, list of mission name/filename pairs
           list: self.default_file, default file from list
        '''
        # create a list
        missions = []
        # get the list of files
        files_in_graph_folder = os.walk(mission_files)

        # loop
        for (dirpath, dirnames, filenames) in files_in_graph_folder:
            for file in filenames:
                file_path = os.path.join(dirpath, file)
                # each file if txt
                if os.path.splitext(file_path)[-1].lower() == ".txt":
                    if os.path.isfile(file_path):
                        #print("file", file_path)
                        missions.append({"uri": file_path, "label": os.path.basename(file_path)})
        
        #return info
        return missions

    #####################################################################
    # process the selected mission file to get bounding box for location 
    #####################################################################
    def get_geometry(self, geometry_file):
        '''
        Args:
            geometry_file (str): file to parse

        Returns:
           str: polygon string
        '''
        # get lat long, guarenteed file from get_files_list
        mission_file = geometry_file
        f=open(mission_file, "r")
        lines=f.readlines()

        # find bounding box
        max_lat = -10000
        max_long = -10000
        min_lat = 10000
        min_long = 10000
        # split lines to get lat/long
        for x in lines:
            cols = x.split()
            # go if no data or zeros
            if len(cols) < 10 or (float(cols[8]) == 0 and float(cols[9]) == 0):
                continue

            latf = float(cols[8])
            longf = float(cols[9])

            # min
            if min_lat > latf:
                min_lat = latf
            if min_long > latf:
                min_long = latf

            # max
            if max_lat < longf:
                max_lat = longf
            if max_long < longf:
                max_long = longf

        f.close()

        # bounding box, if we have valid coordinates
        polygon_string = None

        # check we have valid bounds
        if min_lat < 10000 and min_long < 10000 and max_lat > -10000 and max_long > -10000:
            polygon_string = 'POLYGON (( ' + str(min_lat) + ' ' + str(max_long) + ', ' + \
                                str(min_lat) + ' ' + str(min_long) + ', ' + str(max_lat) + \
                                    ' ' + str(min_long) + ', ' +  str(max_lat) + ' ' \
                                        + str(max_long) + ' ))'
            # return polygon
            return polygon_string
        else:
            return None

    #####################################################################
    # process the flight graph request
    #####################################################################
    def process_flight_graph(self, request_dict, flight_dict):
        '''
        Args:
            request_dict (dict): POST request with mission file
            flight_dict (dict):  ini file flight dict.

        Returns:
           dict.: uuid and status
        '''
        # valid name?
        flight = request_dict['flight']
        if len(flight) == 0:
            return { "status": "error: no flight name." }

        # valid description?
        description = request_dict['description']
        if len(description) == 0:
            return { "status": "error: no flight description." }

        # create dictionary of nodes
        dict_of_nodes = {}

        # we need the sensor id for logging
        sensor_id = None

        # parse input dict
        for input_data in request_dict.keys():
            # get inputs that only have a type, we need to post process
            if '_type' in input_data:
                # get actual name
                pos = input_data.rfind('_type')
                if pos > 0:
                    name = input_data[0:pos]

                    # check not handled by below
                    if name not in request_dict.keys():
                        # reserved name?
                        if name in flight_dict.keys():
                            # if geometry?
                            if flight_dict[name + '_mode'] == 'GEOMETRY':
                                # get string
                                polygon_string = self.get_geometry(request_dict[flight_dict[name]])

                                # add to dictionary
                                if polygon_string:
                                    dict_of_nodes.update( { URIRef(request_dict[input_data]): Literal(polygon_string, datatype = GEOSPARQL.asWKT) } )
                                else:
                                    # if no polygon then bail
                                    return { "status": "error: no coordinates in " + request_dict[flight_dict[name]] + '.'}

            # get inputs that have a type
            if '_type' not in input_data and input_data + '_type' in request_dict.keys():
                #print("INPUT", input_data, request_dict[input_data], request_dict[input_data + '_type'])

                # if its a string handle differently
                # TODO the dictionary should have keys of names not types.
                if request_dict[input_data + '_type'] == 'http://www.w3.org/2001/XMLSchema#string':
                    dict_of_nodes.update( { input_data: request_dict[input_data] } )
                else:
                    # classes
                    dict_of_nodes.update( { URIRef(request_dict[input_data + '_type']): URIRef(request_dict[input_data]) } )

                    # grab sensor id?
                    if input_data == 'sensor':
                        sensor_uuid = request_dict[input_data]
                        # strip uri part
                        pos = sensor_uuid.rfind('/')
                        if pos > 0:
                            sensor_id = sensor_uuid[pos + 1:len(sensor_uuid)]

        #print("DICTNODES", dict_of_nodes)
        # do we have sensor?
        if not sensor_id:
            return { "status": "error: no sensor found." } 

        # dictionary OK?
        if not dict_of_nodes:
            return { "status": "error: could not load all input instances." } 

        # create flight
        oc_id, flt_id = self.create_flight(dict_of_nodes)

        # test?
        if not oc_id or not flt_id:
            return { "status": "error: could not create flight." } 

        # return data
        return {"status": "OK", "sensor_id": sensor_id, "oc_id": oc_id, "flt_id": flt_id}

###########################################
# end of py_drone_graph_store class
###########################################
