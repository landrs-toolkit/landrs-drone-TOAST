'''
Configure functions for simple drone emulator that,
1) searches the graph for shacl classes
2) creates a self configured input form using teh shacl parameters
3) uses the POSTed result to add an instance of the target class to the graph

Original code at https://github.com/CSIRO-enviro-informatics/shacl-form

Laura Guillory
Lead Developer
Griffith University Industrial Placement Student at CSIRO Land & Water
laura.guillory@griffithuni.edu.au

Nicholas Car
Product Owner
Senior Experimental Scientist
CSIRO Land & Water
nicholas.car@csiro.au

Modifications and re-factoring for LANDRS

Chris Sweet 07/02/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

This code now inherited by Graph Class for simple drone emulator that,
1) takes an id
2) queries ld.landers.org to find its configuration OR
2) Loads a set of ttl files and runs sparql queries locally
3) generates an API for access to sensor data
4) provides other functionality in support of Landrs development.

Chris Sweet 07/02/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

This code is inherited by py_drone_graph, the class for acessing and manipulating
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
from rdflib.graph import Graph, ConjunctiveGraph
from rdflib.collection import Collection

#other
from SPARQLWrapper import SPARQLWrapper, JSON
from warnings import warn
import re

# my imports
from graph.py_drone_graph_core import py_drone_graph_core, LANDRS, LDLBASE
from graph.py_drone_graph_core import SOSA, QUDT_UNIT, QUDT, GEO, RDFG, \
        ontology_landrs, ontology_myID

# namespaces from rdflib
from rdflib.namespace import CSVW, DC, DCAT, DCTERMS, DOAP, FOAF, ODRL2, ORG, OWL, \
    PROF, PROV, RDF, RDFS, SDO, SH, SKOS, SSN, TIME, \
    VOID, XMLNS, XSD

SHACL = 'http://www.w3.org/ns/shacl#'

# setup logging ################################################################
logger = logging.getLogger(__name__)

################################################################################
# Class to house rdf graph shacl functions for drone
################################################################################


class config_graph_shacl():
    '''
    sample instantiation,
    d_graph = ldg.py_drone_graph(ontology_myID, load_graph_file)
    where,
    1. ontology_myID, uuid for this drone
      e.g. "MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg=="
    2. load_graph_file, turtle file or (folder) for db initialization
      e.g. base.ttl

    has the following sections,
    1. shacl support functions
    '''

    # shacl support functions ###########################################
    """
    Reads information from a SHACL Shapes file.
    For each shape, can determine:
        Shape URI
        Target class
        Properties associated with the shape
    """

    def get_shape(self, root_uri):
        # Will hold the target class, groups, and ungrouped properties
        shape = dict()

        """
        First, get the root shape. The only shapes we are interested in are Node Shapes. They define all the properties
        and constraints relating to a node that we want to create a form for. Property shapes are useful for defining
        constraints, but are not relevant here

        Shapes which match this criteria are subjects of a triple with a predicate of rdf:type and an object of
        sh:NodeShape

        Shapes and properties can reference other shapes using the sh:node predicate. Therefore, the root shape is the
        only shape that is not the object of a triple with a predicate of sh:node.
        """

        """
        Add any nodes which may be attached to this root shape.
        Does this by grabbing everything in that node and adding it to the root shape.
        Nodes inside properties are handled in get_property
        """
        nodes = self.g.objects(root_uri, URIRef(SHACL + 'node'))
        for n in nodes:
            for (p, o) in self.g.predicate_objects(n):
                self.add_node(root_uri, p, o)

        """
        Get the target class
        Node Shapes have 0-1 target classes. The target class is useful for naming the form.
        Looks for implicit class targets - a shape of type sh:NodeShape and rdfs:Class is a target class of itself.
        """
        if (root_uri, URIRef(RDF.uri + 'type'), URIRef(RDFS.uri + 'Class')) in self.g:
            shape['target_class'] = root_uri
        else:
            shape['target_class'] = self.g.value(
                root_uri, URIRef(SHACL + 'targetClass'), None)
        if not shape['target_class']:
            raise Exception(
                'A target class must be specified for shape: ' + root_uri)

        """
        Get the closed status
        Shapes which are open allow the presence of properties not explicitly defined in the shape
        Shapes which are closed will only allow explicitly defined properties
        """
        is_closed = self.g.value(root_uri, URIRef(SHACL + 'closed'), None)
        if is_closed is None:
            shape['closed'] = False
        else:
            shape['closed'] = is_closed.toPython()

        """
        If the shape is closed, get the ignored properties. These properties will be allowed despite the shape
        being closed and not being defined in their own property shape.
        """
        if 'closed' in shape and shape['closed'] is True:
            ignored_properties = self.g.value(
                root_uri, URIRef(SHACL + 'ignoredProperties'))
            if ignored_properties:
                shape['ignoredProperties'] = [str(l) for l in list(
                    Collection(self.g, ignored_properties))]

        """
        Get the groups
        Some properties belong to groups which determine how they are presented in the form.
        """
        shape['groups'] = list()
        group_uris = self.g.subjects(
            URIRef(RDF.uri + 'type'), URIRef(SHACL + 'PropertyGroup'))
        for g_uri in group_uris:
            group = dict()
            group['uri'] = g_uri
            group['label'] = self.g.value(
                g_uri, URIRef(RDFS.uri + 'label'), None)
            group['order'] = self.g.value(g_uri, URIRef(SHACL + 'order'), None)
            group['properties'] = list()
            shape['groups'].append(group)

        """
        Get all the properties associated with the Shape. They may be URIs or blank nodes. Additional shapes may be
        linked as a node.
        If it belongs to a group, place it in the list of properties associated with the group
        Otherwise, place it in the list of ungrouped properties
        """
        shape['properties'] = list()
        property_uris = list(self.g.objects(
            root_uri, URIRef(SHACL + 'property')))
        for p_uri in property_uris:
            prop = self.get_property(p_uri)
            # Place the property in the correct place
            group_uri = self.g.value(p_uri, URIRef(SHACL + 'group'), None)
            # Belongs to group
            if group_uri:
                # Check if the group referenced actually exists
                existing_group = None
                for g in shape['groups']:
                    if g['uri'] == group_uri:
                        existing_group = g
                if existing_group:
                    existing_group['properties'].append(prop)
                else:
                    raise Exception('Property ' + p_uri + ' references PropertyGroup ' + group_uri
                                    + ' which does not exist.')
            # Does not belong to a group
            else:
                shape['properties'].append(prop)

        # Add instances for fdrop down
        for prop in shape['properties']:
            if 'class' in prop.keys():
                instances = self.get_instances(prop['class'])
                prop.update({'in': instances})

        # return
        return shape

    # support function for get_shape
    def get_property(self, uri, path_required=True):
        prop = dict()
        c_uris = list(self.g.predicate_objects(uri))

        # Link nodes
        for c_uri in tuple(c_uris):
            if re.split('[#/]', c_uri[0])[-1] == 'node':
                c_uris.extend(self.g.predicate_objects(c_uri[1]))

        # Go through each constraint and convert/validate them as necessary
        for c_uri in c_uris:
            name = re.split('[#/]', c_uri[0])[-1]
            value = c_uri[1]

            # Get list of values from constraints that supply a list
            if name in ['in', 'languageIn']:
                value = [str(l) for l in list(Collection(self.g, value))]
            # Convert constraints which must be given as an int
            elif name in ['minCount', 'maxCount']:
                try:
                    value = int(value)
                except ValueError:
                    raise Exception(
                        name + ' value must be an integer: "{value}"'.format(value=value))
            # Convert constraints which must be converted from an rdf literal
            elif name in ['hasValue', 'defaultValue']:
                value = value.toPython()
            # Some properties are made up of other properties
            # Handle this with recursion
            elif name == 'property':
                if 'property' in prop:
                    properties = prop['property']
                    properties.append(self.get_property(value))
                    value = properties
                else:
                    value = [self.get_property(value)]
            # Consolidate constraints which may be supplied in different ways
            # minInclusive and minExclusive can be simplified down to one attribute
            elif name in ['minInclusive', 'minExclusive', 'maxInclusive', 'maxExclusive']:
                if name == 'minInclusive':
                    name = 'min'
                    value = float(value)
                elif name == 'minExclusive':
                    name = 'min'
                    value = float(value) + 1
                if name == 'maxInclusive':
                    name = 'max'
                    value = float(value)
                elif name == 'maxExclusive':
                    name = 'max'
                    value = float(value) - 1
            # All other constraints should be converted to strings
            else:
                value = str(value)

            prop[name] = value

        # Validate property as a whole
        # Property must have one and only one path
        if 'path' not in prop and path_required:
            raise Exception(
                'Every property must have a path associated with it: ' + uri)

        # Must have a name
        # If the property doesn't have a name label, fall back to the URI of the path.
        if 'name' not in prop and 'path' in prop:
            prop['name'] = re.split('[#/]', prop['path'])[-1]

        # There must be an entry for order even if it is unordered
        if 'order' not in prop:
            prop['order'] = None

        # If sh:nodeKind is not present, an appropriate option will be guessed
        # If nested properties are present -> sh:BlankNodeOrIRI
        # Otherwise -> sh:IRIOrLiteral
        warning = None
        if 'nodeKind' not in prop:
            if 'hasValue' in prop:
                prop['nodeKind'] = SHACL + 'Literal'
            else:
                prop['nodeKind'] = SHACL + \
                    'BlankNodeOrIRI' if 'property' in prop else SHACL + 'IRIOrLiteral'
        elif prop['nodeKind'] not in [SHACL + 'BlankNode', SHACL + 'IRI', SHACL + 'Literal',
                                      SHACL + 'BlankNodeOrIRI', SHACL + 'BlankNodeOrLiteral',
                                      SHACL + 'IRIOrLiteral']:
            if 'hasValue' in prop:
                default_value = SHACL + 'Literal'
            else:
                default_value = SHACL + 'BlankNodeOrIRI' if 'property' in prop else SHACL + 'IRIOrLiteral'
            warning = 'Property "' + prop['name'] + '" has constraint "sh:nodeKind" with invalid value "' + \
                      prop['nodeKind'] + '". Replacing with "' + \
                default_value + '".'
            prop['nodeKind'] = default_value
        # Make sure there is enough information provided to accommodate the selected option
        else:
            # If sh:hasValue is present, the user won't be able to choose between nodeKinds, therefore sh:nodeKind can't
            # be BlankNodeOrIRI, IRIOrLiteral, or BlankNodeOrLiteral
            if 'hasValue' in prop and prop['nodeKind'] in [SHACL + 'BlankNodeOrIRI', SHACL + 'IRIOrLiteral',
                                                           SHACL + 'BlankNodeOrLiteral']:
                if prop['nodeKind'] == SHACL + 'BlankNodeOrIRI':
                    new_node_kind = SHACL + 'IRI'
                elif prop['nodeKind'] == SHACL + 'IRIOrLiteral':
                    new_node_kind = SHACL + 'Literal'
                elif prop['nodeKind'] == SHACL + 'BlankNodeOrLiteral':
                    new_node_kind = SHACL + 'Literal'
                warning = 'Property "' + prop['name'] + '" has constraint "sh:nodeKind" with value "' + \
                          prop['nodeKind'] + '" which is incompatible with constraint sh:hasValue. Replacing ' \
                                             'with "' + new_node_kind + '".'
                prop['nodeKind'] = new_node_kind
            # If sh:BlankNode is selected, nested properties should be provided.
            if prop['nodeKind'] == SHACL + 'BlankNode' and 'property' not in prop:
                warning = 'Property "' + prop['name'] + '" has constraint "sh:nodeKind" with value "sh:BlankNode" but' \
                          ' no property shapes are provided. This property will have no input fields.'
            # If sh:BlankNodeOrIRI or sh:BlankNodeOrLiteral are selected, nested properties should be provided for the
            # blank node option
            elif prop['nodeKind'] in [SHACL + 'BlankNodeOrIRI', SHACL + 'BlankNodeOrLiteral'] \
                    and 'property' not in prop:
                warning = 'Property "' + prop['name'] + '" has constraint "sh:nodeKind" with value "' + \
                          prop['nodeKind'] + '" but no property shapes are provided. If the user selects the ' \
                          '"blank node" option, this property will have no input fields.'
            # If sh:IRI, sh:Literal, or sh:IRIOrLiteral are selected, nested properties will be ignored.
            elif prop['nodeKind'] in [SHACL + 'Literal', SHACL + 'IRI', SHACL + 'IRIOrLiteral'] and 'property' in prop:
                warning = 'Property "' + prop['name'] + '" has constraint "sh:nodeKind" with value "' + \
                          prop['nodeKind'] + \
                    '". The property shapes provided in this property will be ignored.'
        if warning:
            warn(warning)
        return prop

    # support function for get_shape
    def add_node(self, root_uri, predicate, obj):
        # Adds the contents of the node to the root shape
        # If the node contains a link to another node, use recursion to add nodes at all depths
        if str(predicate) == SHACL + 'node':
            for (p, o) in self.g.predicate_objects(obj):
                self.add_node(root_uri, p, o)
        self.g.add((root_uri, predicate, obj))

    # support function for get_shape
    def create_rdf_map(self, shape): #, destination):
        g = Graph()
        g.namespace_manager = self.g.namespace_manager
        g.bind('sh', SHACL)
        # Create the node associated with all the data entered
        g.add((Literal('placeholder node_uri'),
               RDF.type, shape['target_class']))
        # Go through each property and add it
        for group in shape['groups']:
            for prop in group['properties']:
                self.add_property_to_map(
                    g, prop, Literal('placeholder node_uri'))
        for prop in shape['properties']:
            self.add_property_to_map(g, prop, Literal('placeholder node_uri'))
        #g.serialize(destination=destination, format='turtle')

        # return serialized map graph
        return g.serialize(format="turtle")

    # support function for get_shape
    def add_property_to_map(self, graph, prop, root):
        # Recursive
        arguments = 'nodeKind=' + re.split('[#/]', prop['nodeKind'])[-1]
        if 'datatype' in prop:
            arguments = arguments + ' datatype=' + prop['datatype']
        placeholder = 'placeholder ' + arguments + ' ' + str(prop['id'])
        graph.add((root, URIRef(prop['path']), Literal(placeholder)))
        if 'property' in prop:
            for p in prop['property']:
                self.add_property_to_map(graph, p, Literal(placeholder))

    # add a graph to the main graph
    def add_graph(self, gin):
        self.g1 += gin

    # get list of SHACL shapes
    def get_shapes(self):
        #create list
        shapes = []
        # exist?
        for s, p, o in self.g.triples((None, RDF.type, SH.NodeShape)):
            if self.g.value(s, URIRef(SHACL + 'targetClass'), None):
                shapes.append(s)
            #print("s",s)
        #return list
        return shapes

    # get list of SHACL support class entities
    def get_instances(self, type):
        #create list
        instances = []
        # exist?
        for s, p, o in self.g.triples((None, RDF.type, type)):
            instances.append(str(s))
            #print("s",s)
        #return list
        return instances

###########################################
# end of config_graph_shacl class
###########################################
