from hydra_python_core import doc_maker
from hydra_python_core.doc_writer import HydraDoc
from typing import Any, Dict, List, Set, Optional
from py_drone_doc import doc

from flask import Flask
from flask_cors import CORS
from flask_restful import Api
import json

from flask import Response, jsonify, request, abort
from flask_restful import Resource
from flask import g

print(doc['@context']['ApiDocumentation'])

def get_classes(apidoc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Get all the classes in the APIDocumentation."""
    classes = list()
    for class_ in apidoc["supportedClass"]:
        if class_["@id"] not in ["http://www.w3.org/ns/hydra/core#Collection",
                                 "http://www.w3.org/ns/hydra/core#Resource", "vocab:EntryPoint"]:
            classes.append(class_)
    # print(classes)
    return classes
#
#
def get_all_properties(classes: List[Dict[str, Any]]) -> Set[str]:
    """Get all the properties in the APIDocumentation."""
    # properties = list()
    prop_names = set()  # type: Set[str]
    for class_ in classes:
        for prop in class_["supportedProperty"]:
            if prop["title"] not in prop_names:
                prop_names.add(prop["title"])
                # properties.append(prop)
    return set(prop_names)

def get_doc() -> HydraDoc:
    global apidoc
    """
    Get the server API Documentation.
    Returns and sets doc_writer_sample.api_doc if not found.
    :return apidoc : Hydra Documentation object
            <hydra_python_core.doc_writer.HydraDoc>
    """
    try:
        apid = getattr(g, 'doc')
    except AttributeError:
        g.doc = apidoc
    return g.doc

def set_response_headers(resp: Response,
                         ct: str = "application/ld+json",
                         headers: List[Dict[str, Any]]=[],
                         status_code: int = 200) -> Response:
    """
    Set the response headers.
    :param resp: Response.
    :param ct: Content-type default "application/ld+json".
    :param headers: List of objects.
    :param status_code: status code default 200.
    :return: Response with headers.
    """
    resp.status_code = status_code
    for header in headers:
        resp.headers[list(header.keys())[0]] = header[list(header.keys())[0]]
    resp.headers['Content-type'] = ct
    link = "http://www.w3.org/ns/hydra/core#apiDocumentation"
    resp.headers['Link'] = f'<http://localhost:6000/api/v2/vocab>; rel="{link}"'
    return resp

class Index(Resource):
    """Class for the EntryPoint."""

    def get(self) -> Response:

        """Return main entrypoint for the api."""
        return set_response_headers(jsonify(get_doc().entrypoint.get()))


class Vocab(Resource):
    """Vocabulary for Hydra."""

    def get(self) -> Response:
        """Return the main hydra vocab."""
        return set_response_headers(jsonify(get_doc().generate()))

def app_factory(api_name: str = "api/v2") -> Flask:
    """
    Create an app object
    :param api_name : Name of the api
    :return : API with all routes directed at /[api_name].
    """

    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'secret key'
    CORS(app)
    app.url_map.strict_slashes = False
    api = Api(app)

    api.add_resource(Index, f"/{api_name}/", endpoint="api")
    api.add_resource(Vocab, f"/{api_name}/vocab", endpoint="vocab")

    return app

#
# Load ApiDoc with doc_maker
#
apidoc = doc_maker.create_doc(doc, "api/v2", "http://localhost:6000/")
'''
{'@id': 'vocab:Drone', '@type': 'hydra:Class', 'description': 'Class for a drone', 'supportedOperation': [{'@type': 'http://schema.org/UpdateAction', 'expects': 'vocab:Drone', 'expectsHeader': [{'description': 'Drone updated', 'statusCode': 200}], 'method': 'POST', 'possibleStatus': [], 'returns': 'null', 'returnsHeader': [], 'title': 'SubmitDrone'}, {'@type': 'http://schema.org/AddAction', 'expects': 'vocab:Drone', 'expectsHeader': [{'description': 'Drone added', 'statusCode': 200}], 'method': 'PUT', 'possibleStatus': [], 'returns': 'null', 'returnsHeader': [], 'title': 'CreateDrone'}, {'@type': 'http://schema.org/FindAction', 'expects': 'null', 'expectsHeader': [{'description': 'Drone not found', 'statusCode': 404}, {'description': 'Drone Returned', 'statusCode': 200}], 'method': 'GET', 'possibleStatus': [], 'returns': 'vocab:Drone', 'returnsHeader': [], 'title': 'GetDrone'}], 'supportedProperty': [{'@type': 'SupportedProperty', 'property': 'vocab:State', 'readable': 'false', 'required': 'true', 'title': 'DroneState', 'writeable': 'false'}, {'@type': 'SupportedProperty', 'property': 'http://schema.org/name', 'readable': 'false', 'required': 'true', 'title': 'name', 'writeable': 'false'}, {'@type': 'SupportedProperty', 'property': 'http://schema.org/model', 'readable': 'false', 'required': 'true', 'title': 'model', 'writeable': 'false'}, {'@type': 'SupportedProperty', 'property': 'http://auto.schema.org/speed', 'readable': 'false', 'required': 'true', 'title': 'MaxSpeed', 'writeable': 'false'}, {'@type': 'SupportedProperty', 'property': 'http://schema.org/device', 'readable': 'false', 'required': 'true', 'title': 'Sensor', 'writeable': 'false'}], 'title': 'Drone'}
'''
classes = get_classes(doc)
for dclass in classes:
    print(dclass)

'''
SensorStatus
DroneState
Data
MessageString
DroneID
BottomRight
Battery
TopLeft
Send
model
State
Speed
Sensor
name
Get
Direction
Command
Update
MaxSpeed
Position
Temperature
members
'''
# Get all the properties from the classes
properties = get_all_properties(classes)
for prpty in properties:
    print(prpty)

app = app_factory("api/v2")

app.run(host='0.0.0.0', port=6000)
