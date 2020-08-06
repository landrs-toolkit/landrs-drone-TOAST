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

        # check it is a sensor, from ld.landres.org?
        sensor_id_node = self.find_node_from_uuid(sensor_id, LANDRS.Sensor)
        if not sensor_id_node:
            ret.update({"status": False, "error": "sensor not found."})
            return ret

        # check if collection exists
        # if collection_id is '*' then create a new one
        collection_id_node = LDLBASE.term(
            collection_id)  # from ld.landres.org?
        # create?
        if collection_id != '*':
            collection_id_node = self.find_node_from_uuid(
                collection_id, SOSA.ObservationCollection)
            if not collection_id_node:
                ret.update({"status": False, "error": "collection not found."})
                return ret

            # if we get here find or create graph to store
            graph = self.observation_collection_graph(collection_id)
        else:  # collection_id is '*'
            # find existing graph associated with obs. coll. or create
            # new uuid
            collection_id = self.generate_uuid()
            ret.update({"collection uuid": collection_id})

            # create new node in graph
            collection_id_node = self.BASE.term(collection_id)
            # TODO: do we nned to add to both graphs?
            self.g1.add((collection_id_node, RDF.type,
                         SOSA.ObservationCollection))
            self.g1.add((collection_id_node, RDFS.label,
                         Literal("Drone data collection")))
            # TODO: test to see if we need common value for collection
            #self.g.add((collection_id_node, SOSA.hasFeatureOfInterest, Literal("house/134/kitchen")))
            # create new graph and get context
            # self.g.get_context(self.create_new_graph(collection_id))
            graph = self.observation_collection_graph(collection_id)
            # now auto-adds obs_col to new graph
            # graph.add((collection_id_node, RDF.type,
            #            SOSA.ObservationCollection))
            # graph.add((collection_id_node, RDFS.label,
            #            Literal("Drone data collection")))

        # store data
        # new uuid
        id = self.generate_uuid()
        ret.update({"uuid": id})

        # create new node in graph
        the_node = self.BASE.term(id)
        graph.add((the_node, RDF.type, SOSA.Observation))

        # add data
        graph.add((the_node, SOSA.madeBySensor, sensor_id_node))
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
        graph.add((collection_id_node, SOSA.hasMember, the_node))

        # check for start time
        if (collection_id_node, PROV.startedAtTime, None) not in graph:
            graph.add((collection_id_node, PROV.startedAtTime, Literal(time_stamp, datatype = XSD.dateTime)))
        
        # add as end time, will keep getting updated
        graph.set((collection_id_node, PROV.endedAtTime, Literal(time_stamp, datatype = XSD.dateTime)))

        # return success
        ret.update({"status": True})
        return ret

    #################################################
    # store bounding box geometry for location
    #################################################
    def create_gometry(self, polygon_string, mission_file):
        '''
        Args:
            polygon_string (str): bounding box string

        Returns:
           str: uuid generated
        '''
        # create uuid for geometry
        poly_uuid = self.generate_uuid()

        # create new node in graph
        poly_id_node = self.BASE.term(poly_uuid)
        # add it
        self.g1.add((poly_id_node, RDF.type, GEOSPARQL.Geometry))

        # now add the polygon
        self.g1.add((poly_id_node, LOCN.geometry, Literal(polygon_string, datatype = GEOSPARQL.asWKT)))
        self.g1.add((poly_id_node, RDFS.label, Literal(mission_file)))   

        # send back the uuid
        return poly_id_node

    def get_observable_Properties(self):
        # create list
        instances = []
        # exist?
        for s in self.g1.subjects(RDF.type, SOSA.ObservableProperty):
            instances.append({ "uri": str(s), "label": str(self.g1.value(s, RDFS.label)) })
            #print("s",s, self.g1.value(s, RDFS.label))

        # return list
        return instances

    def get_sensor_for_obs_prop(self, obs_prop):
        # create list
        instances = []
        # exist?
        for s in self.g1.subjects(SOSA.observes, URIRef(obs_prop)):
            instances.append(str(s))
            #print("s",s, self.g1.value(s, RDFS.label))

        # return list
        return instances

    def get_pilots(self):
        # create list
        instances = []
        # exist?
        for s in self.g1.subjects(RDF.type, PROV.Agent):
            name = self.g1.value(s, FOAF.givenName)
            if name:
                instances.append( { "uri": str(s), "label": str(name) } )

        # return list
        return instances

    def create_flight(self, flight, description, mission_file, poly_id_node, obs_prop, sensor, pilot):
        dict_of_nodes = { SOSA.Sensor: URIRef(sensor), SOSA.ObservableProperty: URIRef(obs_prop) }
        # find feature of interest ##################################################
        #TODO we should probably select this
        feature_node = None
        fois = self.g1.subjects(RDF.type, SOSA.FeatureOfInterest)

        # check if obs_prop is hasProperty
        for foi in fois:
            if (foi, SSN.hasProperty, URIRef(obs_prop)) in self.g1:
                feature_node = foi
                dict_of_nodes.update({SOSA.FeatureOfInterest: feature_node})
                break
        
        # create Place ##############################################################
        # new uuid
        place_id = self.generate_uuid()

        # create new node in graph
        place_node = self.BASE.term(place_id)
        self.g1.add((place_node, RDF.type, LANDRS.Place))
        dict_of_nodes.update({LANDRS.Place: place_node})

        # add data
        # input data derived from form data
        self.g1.add((place_node, SCHEMA.name,  Literal(flight + '_location')))
        self.g1.add((place_node, SCHEMA.description, Literal("A place whose spatial coverage corresponds to " + description)))
        # created nodes
        self.g1.add((place_node, LANDRS.hasSpatialFootprint, URIRef(poly_id_node))) #geosparql:Geometry

        # create Procedure ###########################################################
        # new uuid
        proc_id = self.generate_uuid()

        # create new node in graph
        proc_node = self.BASE.term(proc_id)
        self.g1.add((proc_node, RDF.type, SOSA.Procedure ))
        dict_of_nodes.update({SOSA.Procedure: proc_node})
        # add data
        # input data derived from form data
        self.g1.add((proc_node, SSN.hasInput,  Literal(mission_file)))
        self.g1.add((proc_node, SSN.hasOutput, self.BASE.term(self.Id)))
        self.g1.add((proc_node, RDFS.comment,  Literal("GSC file (input) used to fly UAV (output)")))

        # create Flight ##############################################################
        # new uuid
        flt_id = self.generate_uuid()

        # create new node in graph
        flt_node = self.BASE.term(flt_id)
        self.g1.add((flt_node, RDF.type, LANDRS.Flight ))
        dict_of_nodes.update({LANDRS.Flight: flt_node})

        # add data
        # schema:name "A0001" ;
        # schema:description "First Flight" ;
        # input data derived from form data
        self.g1.add((flt_node, SCHEMA.name,  Literal(flight)))
        self.g1.add((flt_node, SCHEMA.description, Literal(description)))
        self.g1.add((flt_node, LANDRS.isUndertakenBy, self.BASE.term(self.Id)))
        # created nodes
        self.g1.add((flt_node, LANDRS.occursAtPlace, place_node))

        # we need to store the current flight
        self.current_flight_node = flt_node

        # create prov:Association ####################################################
        # new uuid
        assoc_id = self.generate_uuid()

        # create new node in graph
        assoc_node = self.BASE.term(assoc_id)
        self.g1.add((assoc_node, RDF.type, PROV.Association ))
        dict_of_nodes.update({PROV.Association: assoc_node})

        # add data
        # input data derived from form data
        self.g1.add((assoc_node, PROV.wasGeneratedBy, URIRef(pilot)))
        self.g1.add((assoc_node, PROV.hadRole, URIRef("https://www.wikidata.org/wiki/Q81060355"))) # UAV pilot
        # created nodes
        self.g1.add((assoc_node, PROV.hadPlan, proc_node))

        # create ObservationCollection ###############################################
        # get obs_coll shape
        shape = self.get_shape(LANDRS.Flight_ObservationCollectionShape)
        #print("OC SHAPE", shape)

        # find target class
        target_class = shape['target_class']
        print(shape['target_class'])

        # new uuid
        oc_id = self.generate_uuid()

        # create new node in graph
        oc_node = self.BASE.term(oc_id)
        self.g1.add((oc_node, RDF.type, target_class ))

        # loop over proberties defined in shape
        for property in shape['properties']:
            # deal with strings?
            if 'datatype' in property.keys():
                if property['datatype'] == str(XSD.string):
                    print(property['datatype'])
                    self.g1.add((oc_node, URIRef(property['path']), Literal(property['name']))) 
            # deal with sh:NodeKind sh:IRI
            if 'nodeKind' in property.keys():
                if property['nodeKind'] == str(SH.IRI):
                    print(property['nodeKind'])
                    # 'path': 'http://www.w3.org/ns/sosa/madeBySensor', 'class': 'http://www.w3.org/ns/sosa/Sensor',
                    if URIRef(property['class']) in dict_of_nodes.keys():
                        print("Class", property['class'])
                        self.g1.add((oc_node, URIRef(property['path']), dict_of_nodes[URIRef(property['class'])])) 
                    else:
                        print("Not found", property['class'], property['path'])

        # add data
        # dct:title "ObservationCollection 1"@en ;
        # dct:modified "2020-08-15T13:00:00-04:00"^^xsd:dateTime ;   
        # dcat:distribution <id/MkQ2MDlCMjAtMEE5MS00OUYzLUJCRjYtMUY5M0ExODAzREY1Cg==> ; # landrs:DroneDataDistribution
        # prov:wasUsedBy <id/Njk2QzJDNEUtMERBRS00NkIzLThCNEUtMjk3N0JFQzdERDYxCg==> ; # landrs:DataAquisition ;
        # ssn-ext:hasMember   <id/MjMxMjRFMzgtNkQzMi00MDM3LUEzM0YtMDY0Q0JGRDIyNUQ3Cg==> ,  # sosa:Observation
        # input data derived from form data
        ##self.g1.add((oc_node, RDFS.label, Literal(flight)))             # use flight name
        ##self.g1.add((oc_node, DCT.description, Literal(description)))   # use flight description
        # self.g1.add((oc_node, SOSA.madeBySensor, URIRef(sensor)))       # sosa:Sensor
        # self.g1.add((oc_node, PROV.wasAttributedTo, URIRef(sensor)))    # sosa:Sensor
        #self.g1.add((oc_node, SOSA.observedProperty, URIRef(obs_prop))) # co2?
        # created nodes
        #self.g1.add((oc_node, PROV.Agent, flt_node))                    # landrs:Flight
        ##self.g1.add((oc_node, PROV.wasInformedBy, flt_node))            # landrs:Flight point to flight
        ##self.g1.add((oc_node, PROV.qualifiedAssociation, assoc_node))   # PROV.Association
        #self.g1.add((oc_node, SOSA.usedProcedure, proc_node))           # SOSA.Procedure from above
        #if feature_node:
        #    self.g1.add((oc_node, SOSA.hasFeatureOfInterest, feature_node)) # SOSA.featureOfInterest

        # now setup MavLink for the correct obs_prop and sensor
        return oc_id, flt_id

###########################################
# end of py_drone_graph_store class
###########################################
