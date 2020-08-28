# Install TOAST
#
# Chris's third Dockerfile
# See http://www.mathworks.com/products/compiler/mcr/ for more info.

FROM ubuntu:latest

# install git
RUN apt-get update && apt-get install -y git && apt-get install -y python3-pip

# Now grab TOAST and MARMALADE
#ttl files
RUN git clone https://github.com/landrs-toolkit/landrsOntTest.git landrsOntTest
WORKDIR landrsOntTest

#get working version
RUN git checkout config

WORKDIR /
RUN git clone https://github.com/ArduPilot/ardupilot.git

#now the testbed
RUN git clone https://github.com/landrs-toolkit/landrs-drone-TOAST.git toast
WORKDIR toast

#RUN pip3 install -r requirements.txt
RUN pip3 install pymavlink
RUN pip3 install Flask_Cors
RUN pip3 install requests
RUN pip3 install Flask
RUN pip3 install rdflib
RUN pip3 install SPARQLWrapper
RUN pip3 install SQLAlchemy
RUN pip3 install rdflib-sqlalchemy
RUN pip3 install pyshacl

#assume we run on port 8000
RUN sed -i 's/:5000/:8000/g' py_drone.ini
RUN sed -i 's/tcp:127.0.0.1:5761/tcp:host.docker.internal:5761/g' data_acquisition/py_drone_sensors.ini

#port
EXPOSE 5000
EXPOSE 5761

# Finally the command
# hostname -I | awk '{print $1;}' | xargs -I '{}' sed -i 's/127.0.0.1:5000/{}:8000/g' py_drone.ini
CMD [ "python3", "py_drone_toast.py" ]
