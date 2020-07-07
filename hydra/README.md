# Hydra compliant API on py_drone

This code is based on the awesome work of the ```HTTP-APIs``` team, Github https://github.com/HTTP-APIs website http://www.hydraecosystem.org.

py_drone_doc_gen.py generates the json-ld file py_drone_doc.py, using library https://github.com/HTTP-APIs/hydra-python-core, which is used to generate the api. You need to run this after changes to py_drone_doc_gen.py, our top level api definition, ```python3 py_drone_doc_gen.py```.

The api is served by a dissasembled and re-constituted version of hydrus https://github.com/HTTP-APIs/hydrus, think hydrus_lite. Most of the routines are lifted from that repository.

Api appears at ```/api/v2```

Excellent documentation to understand all this is at https://www.hydraecosystem.org/hydra-agent-redis-graph.

The ```HTTP-APIs``` team also provide an self configuring agent https://github.com/HTTP-APIs/hydra-python-agent and a GUI https://github.com/HTTP-APIs/hydra-python-agent-gui that shows a graph representation of the api an auto-configured console to interact with it.
