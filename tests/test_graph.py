'''
Graph Class tests.

Chris Sweet 07/19/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

This code test py_drone_graph, the class for acessing and manipulating
the rdf graph.

From module root call,
python3 -m unittest tests/test_graph.py
'''
import unittest
import os
import shutil

#get the graph class
from graph.py_drone_graph import py_drone_graph

#test class
class TestGraphMethods(unittest.TestCase):

    d_graph = None

    # def test_upper(self):
    #     self.assertEqual('foo'.upper(), 'FOO')

    # def test_isupper(self):
    #     print("hi")
    #     self.assertTrue('FOO'.isupper())
    #     self.assertFalse('Foo'.isupper())

    # def test_split(self):
    #     s = 'hello world'
    #     self.assertEqual(s.split(), ['hello', 'world'])
    #     # check that s.split fails when the separator is not a string
    #     with self.assertRaises(TypeError):
    #         s.split(2)

    #test storage
    def test_storage(self):
        #http://localhost:5000/api/v1/store/*/
        #MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==
        #?data={"type": "co2", "co2": "342", "time_stamp": "2020-07-11T15:25:10.106776"}
        print("STORAGE TEST") #, result)
        store_dict = {'collection_type': 'http://www.w3.org/ns/sosa/ObservationCollection', \
                        'startTime': 'http://www.w3.org/2001/XMLSchema#dateTime', \
                        'sensor_label': 'http://schema.landrs.org/schema/Sensor', \
                        'sensor_quantity': 'http://www.w3.org/2001/XMLSchema#double', \
                        'sensor_quantity_unit': 'http://qudt.org/2.1/vocab/unit#PPM', \
                        'sensor_quantity_geo_fix': 'http://www.opengis.net/ont/geosparql#wktLiteral' }
        result = self.d_graph.store_data_point('*', 'MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==', \
            {"type": "co2", "sensor_value_1": "342.6", "time_stamp": "2020-07-11T15:25:10.106776", "lat": "78.65", "lon": "-43,76", "alt": "486.1"}, store_dict)
        self.assertIn('collection uuid', result)

    #test db has data, RUN THIS BEFORE STORAGE
    def test_db(self):
        print("DB TEST")
        self.assertEqual(str(self.d_graph.find_node_from_uuid('MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==')), \
            "http://ld.landrs.org/id/MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==")

    #load base ttl file into a database
    def setUp(self):
        '''
            create a graph from a file
        '''
        if not self.d_graph: #os.path.exists('test/landrs_test_test.sqlite'): #self.d_graph: #
            print("GRAPH SETUP")
            gdict = {'name': 'landrs_test', 'db_location': 'test/landrs_test_test', \
                        'file_format': 'ttl', 'file': 'tests/test_data/base.ttl', 'file_reload': 'False'}
            #print(gdict.get('db_location', 'crs'))
            self.d_graph = py_drone_graph('MjlmNmVmZTAtNGU1OS00N2I4LWI3MzYtODZkMDQ0MTRiNzcxCg==', \
                gdict, \
                    'http://ld.landrs.org/id/', 'http://ld.landrs.org/')

            #test graph exists
            gdata = self.d_graph.list_graphs()
            #self.assertEqual(gdata, "@prefix rdfg: <http://www.w3.org/2004/03/trix/rdfg-1/> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix rdflib: <http://rdflib.net/projects#> .\n\n<http://ld.landrs.org/id/landrs_test> a rdfg:Graph;rdflib:storage [a rdflib:Store;rdfs:label 'SQLAlchemy'].\n")

    #remove test database file, if exists
    def tearDownClass():
        if os.path.exists('test/landrs_test_test.sqlite'):
             #print("exists")
             shutil.rmtree('test')

if __name__ == '__main__':
    unittest.main()
