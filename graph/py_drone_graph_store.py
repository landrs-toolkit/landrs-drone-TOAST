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
import re

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

    ##################################################
    # store data for sensor, creates SOSA.Observation
    ##################################################
    def store_data_point(self, collection_id, sensor_id, values, store_dict):
        '''
        Args:
            collection_id (str):    uuid for observation collection
                                    '*' to create new
            sensor_id (str):        uuid for sensor to associate data
            value (str):            dictionary values to store, with time
            store_dict (dict.):     dictionary of storage input, like graph types

        Returns:
           dict.: query result
        '''
        # return dict
        ret = {}

        ## What we know #######################################################
        # collection_id, sensor_id
        sensor_label = 'sensor_label'

        # find sensor type
        sensor_type = URIRef(store_dict[sensor_label])  # LANDRS.Sensor #

        # check it is a sensor, from ld.landres.org?
        sensor_id_node = self.find_node_from_uuid(sensor_id, sensor_type)
        if not sensor_id_node:
            ret.update({"status": False, "Error": "sensor not found."})
            return ret

        # find collection type
        # SOSA.ObservationCollection #
        collection_type = URIRef(store_dict['collection_type'])

        # create?
        if collection_id != '*':
            collection_id_node = self.find_node_from_uuid(
                collection_id, collection_type)
            if not collection_id_node:
                ret.update({"status": False, "Error": "collection not found."})
                return ret

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

        # if we get here find or create graph to store
        graph = self.observation_collection_graph(
            collection_id, collection_type)

        # end store?
        if 'end_store' in values.keys():
            # bail if end
            if values['end_store']:
                #print("ENDSTORE", values['time_stamp'])
                # create with existing classes
                collection_label = re.split('[#/]', collection_type)[-1]
                dict_of_nodes = {sensor_label: sensor_id_node,
                         collection_label: collection_id_node}

                # and for observation
                date_time_now = Literal(values['time_stamp'], datatype=URIRef(
                    store_dict['startTime']))  # XSD.dateTime
                dict_of_nodes.update({'endTime': date_time_now})

                # create flight
                if not self.create_flight(dict_of_nodes, 'Store_shape_end', graph):
                    return {"status": False, "Error": "Could not end store."}

                # ended if here
                ret.update({"status": True, "action": 'end store'})
                return ret

        ## create dictionary of nodes #########################################
        # create with existing classes
        collection_label = re.split('[#/]', collection_type)[-1]
        dict_of_nodes = {sensor_label: sensor_id_node,
                         collection_label: collection_id_node}

        # add co2 and GPS
        # create geosparql point from gps and add to blank node
        point = 'POINT(%s %s %s)' % (
            values['lat'], values['lon'], values['alt'])
        dict_of_nodes.update({'sensor_quantity': Literal(
            values['sensor_value_1'], datatype=URIRef(store_dict['sensor_quantity']))})  # XSD.double
        dict_of_nodes.update({'sensor_quantity_geo_fix': Literal(point, datatype=URIRef(
            store_dict['sensor_quantity_geo_fix']))})  # GEOSPARQL.wktLiteral

        # and for observation
        date_time_now = Literal(values['time_stamp'], datatype=URIRef(
            store_dict['startTime']))  # XSD.dateTime
        dict_of_nodes.update({'startTime': date_time_now})

        # add PPM
        dict_of_nodes.update({'sensor_quantity_unit': URIRef(
            store_dict['sensor_quantity_unit'])})

        # create flight
        #store_shape = flight_dict.get('flight_store_shape', 'Store_shape')
        if not self.create_flight(dict_of_nodes, 'Store_shape', graph):
            return {"status": False, "Error": "Could not create store."}

        # return success
        ret.update({"status": True, 'collection uuid': collection_id})
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
                instances.append({"uri": str(s), "label": str(label)})
            else:
                instances.append({"uri": str(s), "label": str(s)})

        # return list
        return sorted(instances, key = lambda i: i['label'])  

    #################################################
    # Populate an instance of a graph
    #################################################
    def populate_instance(self, shape_target, flight_shape, dict_of_nodes, graph):
        '''
        Args:
            shape_target (URIRef):  target class to create
            flight_shape (dict.):   dictionary of shape dictionaries
            dict_of_nodes (dict.):  dictionary of nodes related to/part of flight
            graph (rdflib graph):   graph to append to

        Returns:
           URIRef: the created node URIRef
        '''
        # get shape for shape_target class
        shape = flight_shape[shape_target]

        # find target class
        target_class = shape['target_class']

        # get dict label
        label = re.split('[#/]', target_class)[-1] 
        if 'name' in shape.keys():
            label = shape['name']

        # blank node?
        blankNode = 'nodeKind' in shape.keys() and shape['nodeKind'] == str(SH.BlankNode)

        # does it exist? then return uri
        if label in dict_of_nodes.keys():
                oc_node = dict_of_nodes[label]
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
            dict_of_nodes.update({label: oc_node})

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
            elif 'class' in property.keys():
                # get dict label
                prop_label = re.split('[#/]', str(property['class']))[-1]
                if 'name' in property.keys():
                    prop_label = property['name']

                if property['nodeKind'] == str(SH.IRI) or property['nodeKind'] == str(SH.BlankNode):
                    # Example, 'path': 'http://www.w3.org/ns/sosa/madeBySensor', 'class': 'http://www.w3.org/ns/sosa/Sensor',
                    if prop_label in dict_of_nodes.keys():
                        # add path to existing
                        graph.add(
                            (oc_node, URIRef(property['path']), dict_of_nodes[prop_label]))
                    else:
                        #print("Not found", property['class'], property['path'])
                        # create missing class instance recursively
                        new_node = self.populate_instance(prop_label, flight_shape, dict_of_nodes, graph)
                        if new_node:
                            # add to dictionary of created nodes
                            dict_of_nodes.update( {prop_label: new_node} )

                            # add to graph
                            graph.add((oc_node, URIRef(property['path']), new_node))

        # return node
        return oc_node

    #################################################
    # Get all flight shacl shapes
    #################################################
    def get_flight_shapes(self, flight_label):
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
            if self.g_config.value(ashape, RDFS.label) == Literal(flight_label):
                # find target class
                shape_dict = self.get_shape(ashape)

                # get dict label
                label = re.split('[#/]', str(shape_dict['target_class']))[-1] 
                if 'name' in shape_dict.keys():
                    label = shape_dict['name']

                #shape_target_class = shape_dict['target_class']

                flight_shapes.update({label: shape_dict})

        # return the shapes
        return flight_shapes

    #################################################
    # Create all class instances for a flight
    #################################################
    def create_flight(self, dict_of_nodes, flight_shape, graph):
        '''
        Args:
            dict_of_nodes (dict.):  dictionary of the boundary instances 
                                    required to setup flight

        Returns:
           str: Obsevation Collection id, Flight id
        '''
        # get shapes #################################################################
        # just use those that define the non boundary nodes
        flight_shapes = self.get_flight_shapes(flight_shape)

        # did we get any?
        if len(flight_shapes) == 0:
            print("No flight shapes")
            return False

        # create ObservationCollection and other class instances ######################
        for shape_target in flight_shapes.keys():
            #print("shape target", shape_target)
            # populate
            oc_node = self.populate_instance(shape_target, flight_shapes, dict_of_nodes, graph)

        #print("DICT", dict_of_nodes)

        # OK if here
        return True

    ######################################################
    # Get unsatisfied requirements from flight shacl file
    ######################################################
    def flight_shacl_requirements(self, flight_dict):
        # get shapes #############################################
        flight_shape = flight_dict.get('flight_shape', 'Flight_shape')

        flight_shapes = self.get_flight_shapes(flight_shape)

        # boundary label
        flight_graph_boundary = flight_dict.get(
            'flight_graph_boundary', ',graph_boundary')

        # parse shapes for graph boundaries #
        boundarys = []

        # loop
        for shape_target in flight_shapes.keys():
            #print("shape target", shape_target)
            shape = flight_shapes[shape_target]

            # loop over proberties defined in shape
            for property in shape['properties']:

                # deal with strings? Now using graph boundary labeling
                if 'label' in property.keys() and property['label'] == flight_graph_boundary and 'name' in property.keys():
                    prop_dict = {'name': property['name']}
                    order = 100
                    if 'order' in property.keys():
                        if property['order'] == None:
                            prop_dict.update({'order': 100})
                        else:
                            order = int(property['order'])
                            prop_dict.update({'order': int(property['order'])})
                    if 'datatype' in property.keys():
                        prop_dict.update({'datatype': property['datatype']})
                    if 'class' in property.keys():
                        prop_dict.update({'class': property['class']})
                    if 'description' in property.keys():
                        prop_dict.update(
                            {'description': property['description']})
                    if 'defaultValue' in property.keys():
                        prop_dict.update(
                            {'defaultValue': property['defaultValue']})

                    # substitutions from ini file?
                    if property['name'] in flight_dict.keys():
                        mode = flight_dict.get(
                            property['name'] + '_mode', 'None')

                        # substitute mode
                        if mode == 'SUBSTITUTE':
                            prop_dict.update(
                                {'defaultValue': flight_dict[property['name']]})

                        # files mode
                        if mode == 'FILES':
                            files = self.get_files_list(
                                flight_dict.get(property['name'], './'))
                            prop_dict.update({'in': files})

                    # add dictionary
                    if order < 100:
                        # add instances if class
                        if 'class' in prop_dict.keys():
                            inst = self.get_labeled_instances(
                                prop_dict['class'])
                            prop_dict.update({'in': inst})
                        # add to list
                        if prop_dict not in boundarys:
                            boundarys.append(prop_dict)
                    else:
                        if prop_dict not in boundarys:
                            boundarys.append(prop_dict)
        # sort
        boundarys = sorted(boundarys, key=lambda i: i['order'])

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
                        missions.append(
                            {"uri": file_path, "label": os.path.basename(file_path)})

        # return info
        return sorted(missions, key = lambda i: i['label']) 

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
        f = open(mission_file, "r")
        lines = f.readlines()

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
                ' ' + str(min_long) + ', ' + str(max_lat) + ' ' \
                + str(max_long) + ' ))'
            # return polygon
            return polygon_string
        else:
            return None

    #####################################################################
    # find collection from flight
    #####################################################################
    def find_collection(self, collection_label):
        # setup return
        oc_id = None
        # find collection
        flight_ids = self.g1.subjects(RDFS.label, Literal(collection_label))
        for flight_id in flight_ids:
            str_node = str(flight_id)
            # strip uri part
            pos = str_node.rfind('/')
            if pos > 0:
                oc_id = str_node[pos + 1:len(str_node)]
        # return id
        return oc_id

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
        flight_name = request_dict['flight']
        if len(flight_name) == 0:
            return {"status": "Error: no flight name."}

        # check flight does not exist
        if (None, None, Literal(flight_name)) in self.g1:
            return {"status": "Error: Flight Name '" + flight_name + "' exists."}

        # valid description?
        description = request_dict['description']
        if len(description) == 0:
            return {"status": "Error: no flight description."}

        # create dictionary of nodes
        dict_of_nodes = {}

        # we need the sensor id for logging
        sensor_id = None

        # get name substitution
        flight_name_substutute = '$' + \
            flight_dict.get('flight_name_substutute', 'flight_name')

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
                                polygon_string = self.get_geometry(
                                    request_dict[flight_dict[name]])

                                # add to dictionary
                                if polygon_string:
                                    dict_of_nodes.update({name: Literal(
                                        polygon_string, datatype=GEOSPARQL.asWKT)})
                                else:
                                    # if no polygon then bail
                                    return {"status": "Error: no coordinates in " + request_dict[flight_dict[name]] + '.'}

            # get inputs that have a type
            if '_type' not in input_data and input_data + '_type' in request_dict.keys():
                #print("INPUT", input_data, request_dict[input_data], request_dict[input_data + '_type'])

                # if its a string handle differently
                # TODO the dictionary should have keys of names not types.
                if request_dict[input_data + '_type'] == 'http://www.w3.org/2001/XMLSchema#string':
                    req_str = request_dict[input_data]
                    if flight_name_substutute in req_str:
                        req_str = req_str.replace(
                            flight_name_substutute, flight_name)
                    dict_of_nodes.update({input_data: req_str})
                else:
                    # classes
                    dict_of_nodes.update(
                        {input_data: URIRef(request_dict[input_data])})

                    # grab sensor id?
                    if input_data == 'sensor':
                        sensor_uuid = request_dict[input_data]
                        # strip uri part
                        pos = sensor_uuid.rfind('/')
                        if pos > 0:
                            sensor_id = sensor_uuid[pos + 1:len(sensor_uuid)]

        #print("DICTNODES", dict_of_nodes)

        # do the class instances meet the constraint reqirement of the shape file?
        # e.g. if we have ObservableProperty it must be isPropertyOf of FeatureOfInterest
        # get flight constraint shapes
        flight_constraint = flight_dict.get(
            'flight_constraint', 'Flight_constraint')

        flight_constraints = self.get_flight_shapes(flight_constraint)
        # check each constraint
        for constraint in flight_constraints:
            # does the constarint exist in the boundary list?
            # TODO if not bail?
            if constraint in dict_of_nodes.keys():
                # print(dict_of_nodes[constraint])
                # if so then find properties to test
                for property in flight_constraints[constraint]['properties']:
                    # get the path and target class
                    c_path = property['path']
                    c_class = property['class']
                    # is the target class in the boundary list?
                    # TODO if not bail?
                    if URIRef(c_class) in dict_of_nodes.keys():
                        # if so does it have the correct relationship with our constarint class?
                        # TODO can there be multiples? Need different indexing
                        if self.g1.value(dict_of_nodes[constraint], URIRef(c_path)) != dict_of_nodes[URIRef(c_class)]:
                            #print("MATCH ERROR")
                            return {"status": "Error: \n" + str(dict_of_nodes[constraint]) + '\nNOT\n' + str(c_path) + '\nOF\n' + str(dict_of_nodes[URIRef(c_class)])}

        # do we have sensor?
        if not sensor_id:
            return {"status": "Error: no sensor found."}

        # dictionary OK?
        if not dict_of_nodes:
            return {"status": "Error: could not load all input instances."}

        # create flight
        flight_shape = flight_dict.get('flight_shape', 'Flight_shape')

        if not self.create_flight(dict_of_nodes, flight_shape, self.g1):
            return {"status": "Error: could not create flight."}

        # find oc from graph
        oc_id = None

        # should be label assigned to collection
        # get label suffix
        flight_collection_suffix = flight_dict.get(
            'flight_collection_suffix', ',flight_collection')

        # find collection
        oc_id = self.find_collection(flight_name + flight_collection_suffix)

        # test?
        if not oc_id:
            return {"status": "Error: could not find flight collection."}

        # return data
        return {"status": "OK", "sensor_id": sensor_id, "oc_id": oc_id, "flt_name": flight_name}

    #####################################################################
    # Configure storage dictionary
    #####################################################################
    def flight_store_config(self, flight_dict, flt_name, oc_id, sensor_id):
        '''
        Args:
            flight_dict (dict): Flight section of ini dictionary

        Returns:
           None:
        '''
        # get name
        flight_name = flight_dict.get('flight', '')
        #print("FLIGHT", flight_name)

        # get label suffix
        flight_collection_suffix = flight_dict.get(
            'flight_collection_suffix', ',flight_collection')

        # boundary label
        flight_graph_boundary = flight_dict.get(
            'flight_graph_boundary', ',graph_boundary')

        # get type
        oc_type = self.g1.value(self.BASE.term(oc_id), RDF.type)

        if not oc_type:
            return False

        # initialize dictionary
        temp_dict = {'collection_type': str(oc_type)}

        # get storage shape label
        flight_store_shape = flight_dict.get(
            'flight_store_shape', 'Store_shape')

        # get shapes
        flight_store_shapes = self.get_flight_shapes(flight_store_shape)

        # loop over shapes
        for target_class in flight_store_shapes.keys():

            # loop over properties defined in shape
            for prop in flight_store_shapes[target_class]['properties']:

                # deal with strings? Now using graph boundary labeling
                if 'label' in prop.keys() and prop['label'] == flight_graph_boundary and 'name' in prop.keys():
                    if 'class' in prop.keys():
                        temp_dict.update({prop['name']: prop['class']})
                    if 'datatype' in prop.keys():
                        temp_dict.update({prop['name']: prop['datatype']})

        # print
        # print(temp_dict)

        # success
        return temp_dict

    #####################################################################
    # Check flight exists
    #####################################################################
    def check_flight(self, flight_dict):
        # get name
        flight_name = flight_dict.get('flight', None)

        # find collection
        flight_ids = list(self.g1.subjects(RDFS.label, Literal(flight_name)))

        # exactly one match?
        if len(flight_ids) == 1:
            description = self.g1.value(flight_ids[0], SCHEMA.description)
            # return data
            return flight_name, description
        
        else:
            return None, None
 
###########################################
# end of py_drone_graph_store class
###########################################
