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
            #print(time.time())
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
# MavLink class
##############################
class MavLink(object):

    # standard sensor interface ###############################################
    # name
    name = None

    # other
    # comms port
    master = None

    # cache last gps reading
    last_gps = None

    #######################
    # class initialization
    #######################
    def __init__(self, address, name):
        # remember address
        self.address = address

        # and sensor name
        self.name = name

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
    def gps_extract(self, message, sensors):
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

                # loop over sensors, add random readings for each
                for k in sensors:
                    co2 = str(float(random.randint(3000, 4500)) / 10)
                    gps.update({k: co2})

                # create timestamp, may be in stream
                ts = datetime.datetime.now().isoformat()
                gps.update({"time_stamp": str(ts)})

                # last reading?
                gps.update({"end_store": False})

                # send sensors
                gps.update({'sensors': sensors})

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
    def read(self, sensors):
        # look for GPS data
        if self.last_gps:
            gps = self.gps_extract(self.last_gps, sensors)
            return gps
        else:
            return None

    ##############################
    # Messaging loop for sensor updat
    # could set comms port
    ##############################
    def update(self, message):
        if 'comms_ports' in message.keys():
            self.address = message['comms_ports']
            print('port set to', self.address)

##############################
# Data acquistion class
##############################
class Data_acquisition(object):

    # list of sensors
    sensor_list = []

    #######################
    # class initialization
    #######################
    def __init__(self, mavlink_dict, api_callback):
        # create queue
        self.q_to_mavlink = Queue()

        # create thread for mavlink link, send api callback
        t1 = Thread(target=self.mavlink, daemon=True,
            args=(self.q_to_mavlink, mavlink_dict, api_callback))

        # address
        address = mavlink_dict.get('address', 'tcp:127.0.0.1:5760')

        # create MavLink object, add to sensors
        self.mavlink = MavLink(address, 'mav_link')
        self.sensor_list.append(self.mavlink)

        # Start mavlink thread
        t1.start()


    #######################
    # queue comms
    #######################
    def q_to_mavlink_put(self, message):
        # send message to thread
        self.q_to_mavlink.put(message)


    ###############################################
    # MavLink setup and main loop to read messages
    ###############################################


    def mavlink(self, in_q, mavlink_dict, api_callback):
        '''
        Args:
            in_q (Queue):           quue for API to turn logging on/off
            mavlink_dict (dict):    dictionary of MavLink settings
            api_callback (url):     API callback url

        Returns:
        never
        '''
        # setup ###################################################################
        # store data flag, used so the API can start/stop
        # with http://localhost:5000/api/v1/mavlink?action=stop
        store_data = True

        # first reading flag
        first_reading = True

        # get config
        # get obs. collection, sensor
        observation_collection = mavlink_dict.get('observation_collection', '*')

        # get dataset
        dataset = mavlink_dict.get('dataset', None)

        # get list of sensors
        prop_label = 'sensor'
        sensors = {key:val for key, val in mavlink_dict.items() if prop_label == key[:len(prop_label)]}
        #print("SENSE", sensors)

        # rate
        try:
            rate = int(mavlink_dict.get('rate', '10'))
        except:
            rate = 10

        # sleep for 2s to allow Flask to instantiate
        time.sleep(2)

        #Set up triggers for one second events
        store_trigger = periodic_event(1.0 / rate) # Hz

        # setup connection object
        master = None

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
                                r = requests.post(api_callback, params=req_data)

                                # log return
                                logger.info("POST return: %s.", r.text)
                                
                            # update store params #################################
                            observation_collection = mess['observation_collection']
                            dataset = mess['dataset']

                            # get updated sensor list
                            sensors = {}
                            for sensed in mess['sensors']:
                                sensors.update(sensed)

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
                    gps = {}

                    # look for data, like GPS coords
                    for sensor in self.sensor_list:
                        sense_dat = sensor.read(sensors)
                        if sense_dat:
                            gps.update(sense_dat)

                    # check for data
                    if gps:
                        print(time.time())

                        # add obs col/dataset
                        gps.update({'observation_collection': observation_collection, 
                                    'dataset': dataset, 'first_reading': first_reading})

                        # reset first reading?
                        first_reading = False

                        # create parameters
                        datas = {"data": json.dumps(gps)}

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
            # out_q.put(gps)

            # sleep
            time.sleep(.1)

# run if main ##################################################################
if __name__ == "__main__":
    q = Queue()
    mavlink(q, {"address": 'tcp:127.0.0.1:5760'},
            'http://localhost:5000/api/v1/store/')
