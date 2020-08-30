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
import logging
from string import Template

# thread Imports
from threading import Thread
from queue import Queue

# LANDRS imports
from data_acquisition.data_acquisition_sensor import Sensor

# setup logging ################################################################
logger = logging.getLogger(__name__)

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

    # last reading dictionary
    last_reading = {}

    # current class timestamp
    current_time_stamp = 0

    # address for comms
    address = None

    # Itialized in superclass with
    # CONFIG = {'interface': {'type': 'serial', 'address': address}}
    # So CONFIG['interface']['address'] is address
    #######################
    # class initialization
    #######################
    '''
    Args:
        sensor_dict (dict): dictionary of sensor settings
        name (str):         sensor name

    Returns:
        None
    '''
    def __init__(self, sensor_dict, name):
        # call the super class py_drone_graph_core
        super().__init__(sensor_dict, name)

        # remember address
        MavLink.address = self.CONFIG['interface']['address']
        print("Mavlink Address:", MavLink.address)

        # add filter to packet list
        if self.CONFIG['filter'] not in MavLink.last_reading.keys():
            MavLink.last_reading.update({self.CONFIG['filter']: None})

    ############################################################
    # read loop, waits until messages end to return last message
    # Class method called from loop
    ############################################################
    @classmethod
    def read_loop(cls, m):
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
        if 'mavpackettype' in message.keys() and message['mavpackettype'] == self.CONFIG['filter']:
            # get gps if so
            gps = message

            try:
                # scale mavlink gps
                for cal in self.CONFIG['calibrations']:
                    gps[cal[0]] = str((float(gps[cal[0]]) - cal[1])  * cal[2])

                # add fix?
                if self.CONFIG['output_template']:
                    # create template
                    temp_obj = Template(self.CONFIG['output_template'].replace('_', '$'))
                    # lookup
                    d = {}
                    for fld in self.CONFIG['fields']:
                        d.update( {fld: gps[fld]} )

                    # subst
                    op_field = temp_obj.safe_substitute(**d)

                    print("GPS", op_field)

                    # add to dictionary
                    gps = {self.Name: op_field}

                else:
                    # then just add fields
                    fields = self.CONFIG['fields']

                    # single result?
                    if len(fields) == 1:
                        gps = {self.Name: gps[fields[0]]}
                    else:
                        # array
                        dict_res = {}
                        for fld in fields:
                            dict_res.update({fld: gps[fld]})
                        # store
                        gps = {self.Name: dict_res}

                # units?
                if self.CONFIG['units']:
                    gps.update({self.Name + '_units': self.CONFIG['units'][0]})
                    
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
    @classmethod
    def mav_open(cls):
        '''
        Args:
            None
        Returns:
            comms object or false
        '''
        try:
            master = mavutil.mavlink_connection(cls.address, 115200, 255)

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
            return master

        except Exception as ex:
            print("No MavLink connection " + str(ex))

            # return None if failed
            return None

    # close mavlink port
    @classmethod
    def mav_close(cls):
        if cls.master:
            cls.master.close()
            cls.master = None

    # standard sensor interface ###############################################
    ##############################
    # Stop the sensor. Comms off/power down
    ##############################
    def stop(self):
        MavLink.mav_close()

    ##############################
    # Start the sensor. Comms on/power up
    ##############################
    def start(self):
        if not MavLink.master:
            MavLink.master = MavLink.mav_open()

    ##############################
    # periodic sensor loop, can use for async comms
    # Class method
    ##############################
    @classmethod
    def loop(cls, timestamp):
        # link initialized?
        if cls.master:
            # only once per timestamp
            if cls.current_time_stamp < timestamp:

                # save timestamp
                cls.current_time_stamp = timestamp

                # read link
                message = cls.read_loop(cls.master)

                # buffer GPS/other sensor
                for p_type in cls.last_reading.keys():
                    if p_type in message.keys():
                        # last GPS/other sensor
                        cls.last_reading.update({p_type: message[p_type]})
                        #print("MES", {self.CONFIG['filter']: message[self.CONFIG['filter']]})

    ##############################
    # get dictionary of sensor readings
    ##############################
    def get_values(self):
        '''
        Args:
            None
        Returns:
            gps (dict.):  gps results
        '''
        # look for GPS data
        if self.CONFIG['filter'] in MavLink.last_reading.keys() and MavLink.last_reading[self.CONFIG['filter']]:
            gps = self.gps_extract(MavLink.last_reading[self.CONFIG['filter']])
            return gps
        else:
            return None

    ##############################
    # Messaging loop for sensor update
    # could set comms port
    ##############################
    def update(self, message):
        '''
        Args:
            message (dict.): update information dict.
        Returns:
            None
        '''
        if 'comms_ports' in message.keys():
            self.CONFIG['interface']['address'] = message['comms_ports']
            MavLink.address = message['comms_ports']
            print('port set to', MavLink.address)

###########################################
# end of MavLink class
###########################################
