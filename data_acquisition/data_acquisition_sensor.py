'''
Sensor class for py_drone_toast.
Ideas and some code from Teus Hagen's MySense, https://github.com/teusH/MySense/tree/master/RPi

Subsequent coding,
Chris Sweet 07/10/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

Can run a thread for data acquisition
'''
# Imports ######################################################################
import logging
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

    # sensor handle
    #Name = 'BASE_CLASS'

    # ref to sensor thread, thread may run in parallel
    MyThread = []

    #######################
    # class initialization
    #######################
    def __init__(self, sensor_dict, name):
        '''
        Args:
            sensor_dict (dict): dictionary of sensor settings
            name (str):         sensor name

        Returns:
            None
        '''
        self.CONFIG = {
            'id': "mySensor",      # sensor id
            'input': False,      # no temp/humidity sensors installed
            'type': 'AlphaSense',  # type of the chip eg BME280 Bosch
            'fields': ['nh3'],   # gas nh3, co, no2, o3, ...
            'units': ['ppm'],   # PPM, mA, or mV
            'calibrations': [['nh3', 0, 1]],  # calibration factors, here order 1
            'sensitivity': [[4, 20, 100]],  # 4 - 20 mA -> 100 ppm
            'filter': None,     # data stream filter
            # bus addresses
            'interface': {'type': 'i2c', 'address': '0x48'},
            'interval': 30,      # read dht interval in secs (dflt)
            'bufsize': 20,       # size of the window of values readings max
            'sync': False,       # use thread or not to collect data
            'debug': False,      # be more versatile
            'raw': False,        # no raw measurements displayed
            'fd': None,          # input handler
            'output_template': None,    # template to create combinrd output 
            'output_field': None        # output field name
        }

        self.Name = name

        if sensor_dict:
            self.CONFIG.update(sensor_dict)

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
    def loop(self, timestamp):
        return

    ##############################
    # Messaging loop for sensor updat
    # could set comms port
    ##############################
    def update(self, message):
        '''
        Args:
            message (dict.): update information dict.
        Returns:
            None
        '''
        return

###########################################
# end of Sensor class
###########################################
