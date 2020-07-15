# Install TOAST
#
# Chris's third Dockerfile
# See http://www.mathworks.com/products/compiler/mcr/ for more info.

FROM ubuntu:latest

# install git
RUN apt-get update && apt-get install -y git && apt-get install -y python3-pip

# Now grab TOAST and MARMALADE
#ttl files
#RUN git clone https://github.com/landrs-toolkit/landrsOntTest.git marmalade
#WORKDIR marmalade

#get working version
#RUN git checkout 1f613fd2b06e2fa8b7cafdef15883db8b7aa3d8e

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

#port
EXPOSE 5000

# Finally the command
CMD [ "python3", "py_drone_toast.py" ]
