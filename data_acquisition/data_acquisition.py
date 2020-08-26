'''
Data Acquisition interface for py_drone_toast.

Chris Sweet 07/10/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

Main loop runs on a thread created at class instantiation
'''
# Imports ######################################################################
import time
import requests
import datetime
import json
import logging
import sys
import glob

# thread Imports
from threading import Thread
from queue import Queue

# LANDRS imports
from data_acquisition.data_acquisition_mavlink import MavLink
from data_acquisition.data_acquisition_sensor import Sensor

# setup logging ################################################################
logger = logging.getLogger(__name__)

##############################
# Periodic timer for storage
##############################
class periodic_event(object):
    '''a class for fixed frequency events'''

    def __init__(self, frequency):
        self.frequency = float(frequency)
        self.last_time = time.time()

    def restart(self):
        '''reset time'''
        self.last_time = time.time()

    def force(self):
        '''force immediate triggering'''
        self.last_time = 0

    def trigger(self):
        '''return True if we should trigger now'''
        tnow = time.time()

        if tnow < self.last_time:
            print("Warning, time moved backwards. Restarting timer.")
            self.last_time = tnow

        if self.last_time + (1.0/self.frequency) <= tnow:
            while self.last_time + (1.0/self.frequency) <= tnow:
                self.last_time += (1.0/self.frequency)
            # print(time.time())
            return True
        return False

##############################
# helper for open serial port
##############################
def get_serial_ports():
    ''' Lists serial port names

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of the serial ports available on the system
    '''
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in range(256)]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        if port.find("Bluetooth") != -1:  # Exclude built-in bluetooth ports on OSX
            continue
        result.append(port)
    # return ports
    return result

##############################
# Data acquistion class
##############################
class Data_acquisition(object):

    # list of sensors
    sensor_list = []

    #######################
    # class initialization, starts main loop thread
    #######################
    def __init__(self, dataacquisition_dict, api_callback):
        '''
        Args:
            dataacquisition_dict (dict):    dictionary of data acquisition settings
            api_callback (url):     API callback url

        Returns:
            None
        '''
        # create queue
        self.q_to_data_acqu = Queue()

        # create thread for mavlink link, send api callback
        self.loop_thread = Thread(target=self.main_loop, daemon=True,
                                  args=(self.q_to_data_acqu, dataacquisition_dict, api_callback))

        # address
        address = dataacquisition_dict.get('address', 'tcp:127.0.0.1:5760')

        MavLink_dict = {'interface': {'type': 'serial', 'address': address}}

        # create MavLink object, add to sensors
        mavlink = MavLink(MavLink_dict, 'MavLink')
        self.sensor_list.append(mavlink)

        # get list of sensors
        prop_label = 'sensor'
        self.sensors = {key: val for key, val in dataacquisition_dict.items(
        ) if prop_label == key[:len(prop_label)]}

        for sensor in self.sensors:
            print("SENSE", sensor, self.sensors[sensor])
            new_sensor = Sensor(None, sensor)
            self.sensor_list.append(new_sensor)

        # Start mavlink thread
        self.loop_thread.start()

    #######################
    # queue comms
    #######################
    '''
    Args:
        message (dict):    message to send to main loop via queue

    Returns:
        None
    '''
    def q_to_data_acqu_put(self, message):
        # send message to thread
        self.q_to_data_acqu.put(message)

    ###############################################
    # MavLink setup and main loop to read messages
    ###############################################
    def main_loop(self, in_q, dataacquisition_dict, api_callback):
        '''
        Args:
            in_q (Queue):           quue for API to turn logging on/off etc.
            dataacquisition_dict (dict):    dictionary of data acquisition settings
            api_callback (url):     API callback url

        Returns:
        never
        '''
        # setup ###################################################################
        # store data flag, used so the API can start/stop
        # with http://localhost:5000/api/v1/mavlink?action=stop
        store_data = False

        # first reading flag
        first_reading = True

        # get config
        # get obs. collection, sensor
        observation_collection = dataacquisition_dict.get(
            'observation_collection', '*')

        # get dataset
        dataset = dataacquisition_dict.get('dataset', None)

        # rate
        try:
            rate = int(dataacquisition_dict.get('rate', '10'))
        except:
            rate = 10

        # sleep for 2s to allow Flask to instantiate
        time.sleep(2)

        # Set up triggers for one second events
        store_trigger = periodic_event(1.0 / rate)  # Hz

        # loop until the end of time :-o ##########################################
        while True:
            # Queue, do we have a message?
            if not in_q.empty():
                mess = in_q.get()

                # valid message?
                if mess:
                    # parse commands ##############################################
                    # action? stop/start?
                    if 'action' in mess.keys():
                        print(mess['action'])
                        # stop ####################################################
                        if mess['action'] == 'stop':
                            # close ports etc.
                            for sensor in self.sensor_list:
                                sensor.stop()

                            store_data = False

                            # end logging
                            req_store_end = {"end_store": True, 'observation_collection': observation_collection,
                                             'dataset': dataset}
                            # create timestamp, may be in stream
                            ts = datetime.datetime.now().isoformat()
                            req_store_end.update({"time_stamp": str(ts)})

                            req_data = {"data": json.dumps(req_store_end)}
                            # post to the local flask server
                            r = requests.post(api_callback, params=req_data)

                            # log return
                            logger.info("POST return: %s.", r.text)

                        # start logging ###########################################
                        if mess['action'] == 'start':
                            # open ports etc.
                            for sensor in self.sensor_list:
                                sensor.start()

                            store_data = True

                            # first reading flag
                            first_reading = True

                            # restart times
                            store_trigger.restart()

                        # set comms port ##########################################
                        if mess['action'] == 'setport':
                            # sensor updates
                            for sensor in self.sensor_list:
                                sensor.update(mess)

                        # set observation collection ##############################
                        if mess['action'] == 'set_oc_sensor':
                            # are we logging?
                            if store_data:
                                store_data = False

                                # close ports etc
                                for sensor in self.sensor_list:
                                    sensor.stop()

                                # end logging
                                req_store_end = {"end_store": True, 'observation_collection': observation_collection,
                                                 'dataset': dataset}

                                # create timestamp, may be in stream
                                ts = datetime.datetime.now().isoformat()
                                req_store_end.update({"time_stamp": str(ts)})

                                req_data = {"data": json.dumps(req_store_end)}
                                # post to the local flask server
                                r = requests.post(
                                    api_callback, params=req_data)

                                # log return
                                logger.info("POST return: %s.", r.text)

                            # update store params #################################
                            observation_collection = mess['observation_collection']
                            dataset = mess['dataset']

                            # remove old sensors
                            for sensor in self.sensors:
                                if sensor in self.sensor_list:
                                    self.sensor_list.remove(sensor)

                            # get updated sensor list
                            self.sensors = {}
                            for sensed in mess['sensors']:
                                self.sensors.update(sensed)
                                new_sensor = Sensor(None, sensor)
                                self.sensor_list.append(new_sensor)

                            #print("SENSE", sensors)

            # read returns the last gps value #####################################
            # check we connected
            if store_data:

                # sensor housekeeping
                for sensor in self.sensor_list:
                    sensor.loop()

                # store?
                if store_trigger.trigger():
                    # preset data
                    sensor_data = {}

                    # look for data, like GPS coords
                    for sensor in self.sensor_list:
                        sense_dat = sensor.get_values()
                        if sense_dat:
                            sensor_data.update(sense_dat)
                        else:
                            print("ERROR", sensor.Name, store_data)
                            sensor_data = None
                            break

                    # check for data
                    if sensor_data:
                        print(time.time())

                        # create timestamp, may be in stream
                        ts = datetime.datetime.now().isoformat()
                        sensor_data.update({"time_stamp": str(ts)})

                        # last reading?
                        sensor_data.update({"end_store": False})

                        # send sensors
                        sensor_data.update({'sensors': self.sensors})

                        # add obs col/dataset
                        sensor_data.update({'observation_collection': observation_collection,
                                            'dataset': dataset, 'first_reading': first_reading})

                        # reset first reading?
                        first_reading = False

                        # create parameters
                        datas = {"data": json.dumps(sensor_data)}

                        # post to the local flask server
                        r = requests.post(
                            api_callback, params=datas)
                        logger.info("POST return: %s.", r.text)

                        # parse return
                        ret = json.loads(r.text)

                        # if we used * for observation collection then we should get back a obs coll uuid
                        # use so all obs. get added to the same obs. coll.
                        if 'observation_collection' in ret.keys():
                            observation_collection = ret['observation_collection']
            # out_q.put(sensor_data)

            # sleep
            time.sleep(.1)

###########################################
# end of Data acquistion class
###########################################

# run if main ##################################################################
if __name__ == "__main__":
    data_acquire = Data_acquisition({"address": 'tcp:127.0.0.1:5760'},
                                    'http://localhost:5000/api/v1/store/')
