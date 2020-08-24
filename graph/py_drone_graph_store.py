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
from string import Template

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
    def store_data_point(self, values, flight_dict):
        '''
        Args:
            collection_id (str):    uuid for observation collection
                                    '*' to create new
            value (str):            dictionary values to store, with time

        Returns:
           dict.: query result
        '''
        # return dict
        ret = {}

        # observation_collection
        collection_name = values.get('observation_collection', '*')

        # get obs. col. label
        the_observation_collection = flight_dict.get('flight_collection', 'the_observation_collection')

        # dataset
        dataset = values.get('dataset', None)

        if not dataset and collection_name != '*':
            ret.update({"status": False, "Error": "no dataset found."})
            return ret

        # get label for sensors in 'per sensor storage' shacl section
        sensor_label = flight_dict.get('flight_sensor_label', 'sensor_label')

        # create?
        if collection_name != '*':
            collection_id_node = URIRef(collection_name) #self.find_node_from_uuid(collection_id) #, collection_type)
            if (collection_id_node, None, None) not in self.g1:
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
            self.g1.add((collection_id_node, RDF.type, SOSA.ObservationCollection))
            self.g1.add((collection_id_node, RDFS.label,
                         Literal("Drone data collection")))

        # if we get here find or create graph to store
        collection_type = self.g1.value(collection_id_node, RDF.type)
        graph = self.observation_collection_graph(collection_id_node, collection_type, dataset)
        if not graph:
            ret.update({"status": False, "Error": "could not attach graph."})
            return ret

        # end store?
        if 'end_store' in values.keys():
            # bail if end
            if values['end_store']:
                #print("ENDSTORE", values['time_stamp'])
                # create with existing classes
                #collection_label = re.split('[#/]', collection_type)[-1]
                dict_of_nodes = {the_observation_collection: collection_id_node}

                # and for observation
                endTime = flight_dict.get('flight_time_stamp_end', 'endTime')
                dict_of_nodes.update({endTime: values['time_stamp']})

                # create flight
                Store_shape_end = flight_dict.get('flight_store_shape_end', 'Store_shape_end')
                if not self.create_flight(dict_of_nodes, Store_shape_end, graph, -1):
                    return {"status": False, "Error": "Could not end store."}

                # ended if here
                ret.update({"status": True, "action": 'end store'})
                return ret

        ## create dictionary of nodes #########################################
        # get sensor data from stream
        sensors = values['sensors']

        dict_of_nodes = {}

        # loop over sensors, create sub graphs
        count = 0
        for k in sensors:
            #print("Sensor", sensors[k])

            # get sensor and add to dictionary
            sensors[k] = URIRef(sensors[k])
            new_label = sensor_label
            if count > 0:
                new_label = sensor_label + '-' + str(count)
            local_dict_of_nodes = {new_label: sensors[k]}

            # add reading from sensor, co2?
            sensor_quantity = flight_dict.get('flight_sensor_value', 'sensor_quantity')
            local_dict_of_nodes.update({sensor_quantity: values[k]})  # XSD.double

            # create sub-graph
            temp_dict_of_nodes = self.create_flight(local_dict_of_nodes, 'Sensor_store_shape', graph, count)
            if not temp_dict_of_nodes:
                return {"status": False, "Error": "Could not create sensor store."}
            else:
                dict_of_nodes.update(temp_dict_of_nodes)

            # pop quantity as done with it
            dict_of_nodes.pop(sensor_quantity)

            # update loop counter
            count += 1

        #print("DICTAFTERSENSE", dict_of_nodes)

        # add collection
        #collection_label = re.split('[#/]', collection_type)[-1]
        dict_of_nodes.update( {the_observation_collection: collection_id_node} )

        # fix
        sensor_quantity_geo_fix = flight_dict.get('flight_geo_fix', 'sensor_quantity_geo_fix')
        dict_of_nodes.update({sensor_quantity_geo_fix: values['geo_fix']})  # GEOSPARQL.wktLiteral

        # and for observation
        startTime = flight_dict.get('flight_time_stamp', 'startTime')
        dict_of_nodes.update({startTime: values['time_stamp']})

        # create flight
        store_shape = flight_dict.get('flight_store_shape', 'Store_shape')
        dict_of_nodes = self.create_flight(dict_of_nodes, store_shape, graph, -1)
        if not dict_of_nodes:
            return {"status": False, "Error": "Could not create store."}

        #print("DICT", dict_of_nodes)

        # return success
        ret.update({"status": True, 'observation_collection': collection_id_node})
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
    def populate_instance(self, label, flight_shape, dict_of_nodes, graph, id):
        '''
        Args:
            shape_target (URIRef):  target class to create
            flight_shape (dict.):   dictionary of shape dictionaries
            dict_of_nodes (dict.):  dictionary of nodes related to/part of flight
            graph (rdflib graph):   graph to append to

        Returns:
           URIRef: the created node URIRef
        '''
        #print("LABEL", label)
        # allow for unique names for instances while using common shape set.
        # assumes name-n for numeric n
        id = 0
        name_id = label.rsplit('-',1)

        if len(name_id) == 0:
            return False
        
        shape_target = name_id[0]

        if len(name_id) > 1:
            id = int(name_id[1])

        # get shape for shape_target class
        shape = flight_shape[shape_target]

        # find target class
        target_class = shape['target_class']

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

            # multiple inheritance?
            if 'target_classes' in shape.keys():
                for tg in shape['target_classes']:
                    if tg != target_class:
                        graph.add((oc_node, RDF.type, tg))
                        #print("TG", str(tg))

            # add to dictionary of created nodes
            dict_of_nodes.update({label: oc_node})

        # loop over proberties defined in shape
        for property in shape['properties']:

            # deal with strings?
            if 'datatype' in property.keys():
                ##print(property['datatype'], property['path'], property['name'])
                # has value?
                if 'hasValue' in property.keys():
                    graph.add((oc_node, URIRef(property['path']), Literal(property['hasValue'])))
                    # skip rest
                    continue

                # check if maxcount or if under maxcount
                if 'maxCount' not in property.keys() or len(list(graph.objects(oc_node, URIRef(property['path'])))) < int(property['maxCount']):
                    # if OK update
                    if property['datatype'] == str(XSD.string):
                        graph.add((oc_node, URIRef(property['path']), Literal(
                            dict_of_nodes[property['name']])))
                    else:
                        dat_lit = Literal(dict_of_nodes[property['name']], datatype=URIRef(property['datatype']))
                        graph.add((oc_node, URIRef(property['path']), dat_lit))

            # deal with sh:nodeKind sh:IRI
            elif 'class' in property.keys():
                # has value?
                if 'hasValue' in property.keys():
                    graph.add((oc_node, URIRef(property['path']), URIRef(property['hasValue'])))
                    # skip rest
                    continue

                # get dict label
                prop_label = re.split('[#/]', str(property['class']))[-1]
                if 'name' in property.keys():
                    prop_label = property['name']

                if property['nodeKind'] == str(SH.IRI) or property['nodeKind'] == str(SH.BlankNode):
                    # Example, 'path': 'http://www.w3.org/ns/sosa/madeBySensor', 'class': 'http://www.w3.org/ns/sosa/Sensor',
                    # check for wildcards
                    prop_labels = [val for key, val in dict_of_nodes.items() \
                        if prop_label == key[:len(prop_label)] and \
                            (len(key) == len(prop_label) or key[len(prop_label)] == '-')]

                    # exist? Includes prop_label if that exists
                    if prop_labels:
                            # get each one
                            for pd in prop_labels:
                                graph.add((oc_node, URIRef(property['path']), pd))
                            continue
                    else:
                        #print("Not found", property['class'], property['path'])
                        # create missing class instance recursively
                        new_label = prop_label
                        if id > 0:
                            new_label = prop_label + '-' + str(id)
                        new_node = self.populate_instance(new_label, flight_shape, dict_of_nodes, graph, id)
                        if new_node:
                            # add to dictionary of created nodes
                            dict_of_nodes.update( {new_label: new_node} )

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
    def create_flight(self, dict_of_nodes, flight_shape, graph, id):
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

            # multiples in dictionary?
            # TODO, check for '-' after shape_target
            node_keys = [key for key, val in dict_of_nodes.items() \
                if shape_target == key[:len(shape_target)] and \
                    (len(key) == len(shape_target) or key[len(shape_target)] == '-')]

            if node_keys:
                for n in node_keys:
                    #print("KEY", n)
                    # update
                    oc_node = self.populate_instance(n, flight_shapes, dict_of_nodes, graph, id)

            # also run original call?
            new_label = shape_target
            if id > 0:
                new_label = shape_target + '-' + str(id)
            # populate
            oc_node = self.populate_instance(new_label, flight_shapes, dict_of_nodes, graph, id)

        #print("DICT", dict_of_nodes)

        # OK if here
        return dict_of_nodes

    ######################################################
    # Get unsatisfied requirements from flight shacl file
    ######################################################
    def flight_shacl_requirements(self, input_dict):
        # get shapes #############################################
        flight_shape = input_dict.get('input_shape', 'Flight_shape')

        flight_shapes = self.get_flight_shapes(flight_shape)

        # boundary label
        flight_graph_boundary = input_dict.get('graph_boundary', 'graph_boundary')

        # parse shapes for graph boundaries #
        boundarys = []

        # loop
        for shape_target in flight_shapes.keys():
            #print("shape target", shape_target)
            shape = flight_shapes[shape_target]

            # loop over proberties defined in shape
            for property in shape['properties']:

                # deal with strings? Now using graph boundary labeling
                if 'label' in property.keys() and property['label'] == flight_graph_boundary \
                        and 'name' in property.keys():
                    # grab property dictionary
                    prop_dict = property

                    # sort order for cases where it is None
                    if 'order' in prop_dict.keys():
                        if prop_dict['order'] == None:
                            prop_dict['order'] = 100

                    # substitutions from ini file?
                    if prop_dict['name'] in input_dict.keys():
                        mode = input_dict.get(
                            property['name'] + '_mode', 'None')

                        # substitute mode
                        if mode == 'SUBSTITUTE':
                            prop_dict.update(
                                {'defaultValue': input_dict[property['name']]})

                        # files mode
                        if mode == 'FILES':
                            files = self.get_files_list(
                                input_dict.get(property['name'], './'))
                            prop_dict.update({'in': files})

                    # add dictionary to list
                    if not [element for element in boundarys if element['name'] == prop_dict['name']]:
                        boundarys.append(prop_dict)

        # sort
        boundarys = sorted(boundarys, key=lambda i: int(i['order']))

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
    # process the input form request
    #####################################################################
    def process_input_form(self, request_dict, input_dict):
        '''
        Args:
            request_dict (dict): POST request with input data
            input_dict (dict):  ini file flight dict.

        Returns:
           dict.: uuid and status
        '''
        # create dictionary of nodes
        dict_of_nodes = {}

        # get name substitution
        name_substutute = input_dict.get('name_substutute', None)

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
                        if name in input_dict.keys():
                            # if geometry?
                            if input_dict[name + '_mode'] == 'GEOMETRY':
                                # get string
                                polygon_string = self.get_geometry(
                                    request_dict[input_dict[name]])

                                # add to dictionary
                                if polygon_string:
                                    dict_of_nodes.update({name: Literal(
                                        polygon_string, datatype=GEOSPARQL.asWKT)})
                                else:
                                    # if no polygon then bail
                                    return {"status": "Error: no coordinates in " + request_dict[input_dict[name]] + '.'}

            # get inputs that have a type
            if '_type' not in input_data and input_data + '_type' in request_dict.keys():
                #print("INPUT", input_data, request_dict[input_data], request_dict[input_data + '_type'])

                # if its a string handle differently
                # TODO the dictionary should have keys of names not types.
                if request_dict[input_data + '_type'] == 'http://www.w3.org/2001/XMLSchema#string':
                    req_str = request_dict[input_data]

                    # template substitute?
                    if name_substutute and name_substutute in req_str:
                        # create template
                        temp_obj = Template(req_str)
                        # lookup
                        d = {name_substutute: request_dict[name_substutute]}
                        # subst
                        req_str = temp_obj.substitute(**d)

                    dict_of_nodes.update({input_data: req_str})
                else:
                    # classes
                    dict_of_nodes.update(
                        {input_data: URIRef(request_dict[input_data])})

        #print("DICTNODES", dict_of_nodes)

        # do the class instances meet the constraint reqirement of the shape file?
        # e.g. if we have ObservableProperty it must be isPropertyOf of FeatureOfInterest
        # get flight constraint shapes
        constraint_shape = input_dict.get('constraint_shape', None)

        # are there constraints?
        if constraint_shape:
            # get constraints
            constraint_shapes = self.get_flight_shapes(constraint_shape)
            # check each constraint
            for constraint_w in constraint_shapes:
                # does the constarint exist in the boundary list?
                # wildcard
                constraints = [key for key, val in dict_of_nodes.items() \
                    if constraint_w == key[:len(constraint_w)] and \
                        (len(key) == len(constraint_w) or key[len(constraint_w)] == '-')]

                # TODO if not bail?
                for constraint in constraints:
                    #print(dict_of_nodes[constraint])
                    # if so then find properties to test
                    for property in constraint_shapes[constraint_w]['properties']:
                        # property pass/fail
                        prop_pass = False

                        # get the path and target class
                        c_path = property['path']
                        c_name = property['name']
                        # is the target class in the boundary list?
                        # wildcard
                        c_names = [key for key, val in dict_of_nodes.items() \
                            if c_name == key[:len(c_name)] and \
                                (len(key) == len(c_name) or key[len(c_name)] == '-')]

                        # loop
                        for cname in c_names:
                            # if so does it have the correct relationship with our constarint class?
                            # get candidates
                            subjects = self.g1.objects(dict_of_nodes[constraint], URIRef(c_path))
                            # is ours in generator?
                            if dict_of_nodes[cname] in subjects:
                                #print("OK", cname)
                                prop_pass = True

                        # did we get a postive hit?
                        if not prop_pass:
                            print("MATCH ERROR.")
                            return {"status": "Error: \n" + str(dict_of_nodes[constraint]) + '\nNOT\n' + str(c_path) + '\nOF\n' + str(dict_of_nodes[c_name])}

        # dictionary OK?
        if not dict_of_nodes:
            return {"status": "Error: could not load all input instances."}

        # create sub-graph
        input_shape = input_dict.get('input_shape', None)

        if not input_shape:
            return {"status": "Error: no input shape."}

        combined_dict_of_nodes = self.create_flight(dict_of_nodes, input_shape, self.g1, -1)
        if not combined_dict_of_nodes:
            return {"status": "Error: could not create graph."}

        # return data
        combined_dict_of_nodes.update({"status": "OK"})

        return combined_dict_of_nodes

    ####################################################################
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
        # get the flight name
        the_flight_name = flight_dict.get('flight_name', 'flight')
        
        # valid name?
        flight_name = request_dict[the_flight_name]
        if len(flight_name) == 0:
            return {"status": "Error: no flight name."}

        # check flight does not exist
        if (None, None, Literal(flight_name)) in self.g1:
            return {"status": "Error: Flight Name '" + flight_name + "' exists."}

        # # valid description? (guarenteed by input form)
        # description = request_dict['description']
        # if len(description) == 0:
        #     return {"status": "Error: no flight description."}

        # parse input data
        combined_dict_of_nodes = self.process_input_form(request_dict, flight_dict)

        # ether our dictionary or an error
        if combined_dict_of_nodes['status'] != 'OK':
            return combined_dict_of_nodes

        # get our named obs col
        the_observation_collection = flight_dict.get('flight_collection', 'the_observation_collection')
        obs_col =  combined_dict_of_nodes.get(the_observation_collection, None)

        # test?
        if not obs_col:
            return {"status": "Error: could not find flight collection."}

        # strip uri part for display
        pos = obs_col.rfind('/')
        if pos > 0:
            oc_id = obs_col[pos + 1:len(obs_col)]

        # get the graph/dataset
        the_dataset = flight_dict.get('flight_dataset', 'the_dataset')
        dataset = combined_dict_of_nodes.get('the_dataset', None)

        # and the sensors
        # sensor Shacl label
        sensor = flight_dict.get('flight_sensor', 'sensor')

        # get wildcard from dict
        sensors = [{key:str(val)} for key, val in combined_dict_of_nodes.items() \
                    if sensor == key[:len(sensor)] and \
                        (len(key) == len(sensor) or key[len(sensor)] == '-')]

        # return data
        return {"status": "OK", "oc_id": oc_id, "observation_collection": obs_col, "dataset": dataset, 
                "flight": flight_name, "sensors": sensors}

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
