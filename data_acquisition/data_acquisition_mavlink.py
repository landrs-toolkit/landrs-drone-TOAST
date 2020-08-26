'''
Mavlink interface for py_drone_toast.
From a gist by Ben Boughton https://gist.github.com/benboughton1/dba72b1ca01aec86775e0e6c54a6067e
Also quotes # https://gist.github.com/vo/9331349

Subsequent coding,
Chris Sweet 07/10/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

Runs on a thread created from the Flask API
'''
# Imports ######################################################################
from pymavlink import mavutil
import time
import requests
import datetime
import json
import logging
from queue import Queue
import sys
import glob
import random

# thread Imports
from threading import Thread
from queue import Queue

# setup logging ################################################################
logger = logging.getLogger(__name__)

##############################
# Sensor class
##############################
class Sensor(object):

    CONFIG = {
        'input': False,      # no temp/humidity sensors installed
        'type': 'AlphaSense',# type of the chip eg BME280 Bosch
        'fields': ['nh3'],   # gas nh3, co, no2, o3, ...
        'units' : ['ppm'],   # PPM, mA, or mV
        'calibrations' : [[0,1]], # calibration factors, here order 1
        'sensitivity': [[4,20,100]], # 4 - 20 mA -> 100 ppm
        'interface': {'type': 'i2c', 'address': '0x48'},     # I2C-bus addresses
        'interval': 30,      # read dht interval in secs (dflt)
        'bufsize': 20,       # size of the window of values readings max
        'sync': False,       # use thread or not to collect data
        'debug': False,      # be more versatile
        'raw': False,        # no raw measurements displayed
        'fd' : None          # input handler
    }

    # sensor handle
    Name = 'BASE_CLASS'

    # ref to sensor thread, thread may run in parallel
    MyThread = []

    #######################
    # class initialization
    #######################
    def __init__(self, sensor_dict, name):
        self.Name = name

        if sensor_dict:
            self.CONFIG.update( sensor_dict )

    ##############################
    # Get values
    ##############################
    '''
    Returns:
        dict.: current sensor values
    '''
    def get_values(self):
        return {self.Name: str(float(random.randint(3000, 4500)) / 10)}

        # standard sensor interface ###############################################
    ##############################
    # Stop the sensor. Comms off/power down
    ##############################
    def stop(self):
        return

    ##############################
    # Start the sensor. Comms on/power up
    ##############################
    def start(self):
        return

    ##############################
    # periodic sensor loop, can use for async comms
    ##############################
    def loop(self):
        return

    ##############################
    # Messaging loop for sensor updat
    # could set comms port
    ##############################
    def update(self, message):
        return

##############################
# MavLink class
##############################
class MavLink(Sensor):

    # standard sensor interface ###############################################
    # name
    #name = None

    # other
    # comms port
    master = None

    # cache last gps reading
    last_gps = None

    # Itialized in superclass with
    # CONFIG = {'interface': {'type': 'serial', 'address': address}}
    # So CONFIG['interface']['address'] is address
    #######################
    # class initialization
    #######################
    def __init__(self, sensor_dict, name):
        # call the super class py_drone_graph_core
        super().__init__(sensor_dict, name)

        # remember address
        self.address = self.CONFIG['interface']['address']
        print("Address", self.address)

        # # and sensor name
        # self.Name = name

    ############################################################
    # read loop, waits until messages end to return last message
    ############################################################
    def read_loop(self, m):
        '''
        Args:
            m (mavlink_connection): serial link connection

        Returns:
            dict.: last message as dict.
        '''
        message = {}

        # loop until no more messages
        while True:
            # get queued messages without blocking
            msg = m.recv_match(blocking=False)

            # break loop once most recent messages have updated dict
            if not msg:
                return message

            # convert to python dictionary for next loop possible return
            message[msg.get_type()] = msg.to_dict()

    #############################
    # extract and scale GPS data
    #############################
    def gps_extract(self, message):
        '''
        Args:
            message (dict):    message dictionary from drone

        Returns:
        dict.: gps data or None
        '''
        # do we have GPS data?
        if 'GLOBAL_POSITION_INT' in message.keys():
            # get gps if so
            gps = message['GLOBAL_POSITION_INT']

            try:
                # scale mavlink gps
                gps['lat'] = str(float(gps['lat']) * 1e-7)
                gps['lon'] = str(float(gps['lon']) * 1e-7)
                gps['alt'] = str(float(gps['alt']) * 1e-3)

                # add type and time
                gps.update({"type": "gps"})

                # add fix
                gps.update({"geo_fix": 'POINT(%s %s %s)' % (gps['lat'], gps['lon'], gps['alt'])})

                # # create timestamp, may be in stream
                # ts = datetime.datetime.now().isoformat()
                # gps.update({"time_stamp": str(ts)})

                # # last reading?
                # gps.update({"end_store": False})

                print("GPS lat", gps['lat'], "long", gps['lon'], "alt", gps['alt'])

                # return dataset
                return gps
            except:
                #print("Error in GPS data!")
                logger.error("Error in GPS data.")
                return None
        else:
            #print("No GPS data!")
            logger.error("No GPS data.")
            return None

    # open mavlink port
    def mav_open(self):
        try:
            master = mavutil.mavlink_connection(self.address, 115200, 255)

            # wait for a <3 response
            # http://docs.ros.org/kinetic/api/mavlink/html/mavutil_8py_source.html
            # blocking = True , timeout = None
            m = master.wait_heartbeat(timeout=3)
            # check we had a valid response
            if m == None:
                # go if error
                print("Connection error.")
                return None

            # setup data streams
            master.mav.request_data_stream_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,    # stream id
                1,                                   # message rate Hz
                1                                       # 1 start, 0 stop
            )

            # return comms object
            self.master = master
            return master

        except Exception as ex:
            print("No MavLink connection " + str(ex))
            # null
            self.master = None
            return None

    # close mavlink port
    def mav_close(self):
        if self.master:
            self.master.close()

    # standard sensor interface ###############################################
    ##############################
    # Stop the sensor. Comms off/power down
    ##############################
    def stop(self):
        self.mav_close()

    ##############################
    # Start the sensor. Comms on/power up
    ##############################
    def start(self):
        self.master = self.mav_open()

    ##############################
    # periodic sensor loop, can use for async comms
    ##############################
    def loop(self):
        if self.master:
            # read link
            self.message = self.read_loop(self.master)

            # buffer GPS
            if 'GLOBAL_POSITION_INT' in self.message.keys():
                # last GPS
                self.last_gps = self.message

    ##############################
    # get dictionary of sensor readings
    ##############################
    # TODO remove sensors!
    def get_values(self):
        # look for GPS data
        if self.last_gps:
            gps = self.gps_extract(self.last_gps)
            return gps
        else:
            return None

    ##############################
    # Messaging loop for sensor updat
    # could set comms port
    ##############################
    def update(self, message):
        if 'comms_ports' in message.keys():
            self.CONFIG['interface']['address'] = message['comms_ports']
            self.address = message['comms_ports']
            print('port set to', self.address)

