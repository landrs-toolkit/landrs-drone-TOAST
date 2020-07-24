'''
Mavlink interface for py_drone_toast.
From a gist by Ben Boughton https://gist.github.com/benboughton1/dba72b1ca01aec86775e0e6c54a6067e
Also quotes # https://gist.github.com/vo/9331349

Subsequent coding,
Chris Sweet 07/10/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

Runs on a thread created from the Flask API
Note:   Setting .ini '[MAVLINK] run_at_start = True' will run the thread at the start.
        In this instance 'http://localhost:5000/api/v1/mavlink?action=start/stop'
        will have no effect as task started before Flask fork.
        RECOMMENDATION: set run_at_start = False and start with
        'http://localhost:5000/api/v1/mavlink?action=start'.
'''
# Imports ######################################################################
from pymavlink import mavutil
import time
import requests
import datetime
import json
import logging
from queue import Queue

# setup logging ################################################################
logger = logging.getLogger(__name__)

############################################################
# read loop, waits until messages end to return last message
############################################################


def read_loop(m):
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


def gps_extract(message):
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

            # create timestamp, may be in stream
            ts = datetime.datetime.now().isoformat()
            gps.update({"time_stamp": str(ts)})

            # create parameters
            datas = {"data": json.dumps(gps)}

            print("GPS lat", gps['lat'], "long", gps['lon'], "alt", gps['alt'])

            # return dataset
            return datas
        except:
            #print("Error in GPS data!")
            logger.error("Error in GPS data.")
            return None
    else:
        #print("No GPS data!")
        logger.error("No GPS data.")
        return None

###############################################
# MavLink setup and main loop to read messages
###############################################


def mavlink(in_q, mavlink_dict, api_callback):
    '''
    Args:
        in_q (Queue):           quue for API to turn logging on/off
        mavlink_dict (dict):    dictionary of MavLink settings
        api_callback (url):     API callback url

    Returns:
       never
    '''
    # setup ####################################################################
    # store data flag, used so the API can start/stop
    # with http://localhost:5000/api/v1/mavlink?action=stop
    store_data = True

    # get config
    # get obs. collection, sensor
    mav_obs_collection = mavlink_dict.get('observation_collection', '*')
    mav_sensor = mavlink_dict.get(
        'sensor', 'MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==')

    # address
    address = mavlink_dict.get('address', 'tcp:127.0.0.1:5760')
    # rate
    try:
        rate = int(mavlink_dict.get('rate', '10'))
    except:
        rate = 10

    # sleep for 10s to allow Flask to instantiate
    time.sleep(10)

    # setup connection
    master = None
    try:
        master = mavutil.mavlink_connection(address, 115200, 255)

        # wait for a <3 response
        master.wait_heartbeat()

        # setup data streams
        master.mav.request_data_stream_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,    # stream id
            1,                                   # message rate Hz
            1                                       # 1 start, 0 stop
        )
    except Exception as ex:
        print("No MavLink connection " + str(ex))

    storage_counter = 0
    # loop until the end of time :-o ###########################################
    while True:
        # Queue, do we have a message?
        if not in_q.empty():
            mess = in_q.get()

            # valid message?
            if mess:
                # parse commands
                # action? stop/start?
                if 'action' in mess.keys():
                    print(mess['action'])
                    # stop or start?
                    if mess['action'] == 'stop':
                        store_data = False
                    if mess['action'] == 'start':
                        store_data = True

        # read returns the last gps value
        # check we connected
        if master and store_data:
            # updare counter
            storage_counter = storage_counter + 1

            # read link
            message = read_loop(master)

            # store?
            if storage_counter > rate:
                storage_counter = 0

                # look for GPS data
                datas = gps_extract(message)

                # check for data
                if datas:
                    # post to the local flask server
                    r = requests.post(
                        api_callback + mav_obs_collection + '/' + mav_sensor, params=datas)
                    logger.info("POST return: %s.", r.text)

                    # parse return
                    ret = json.loads(r.text)

                    # if we used * for observation collection then we should get back a obs coll uuid
                    # use so all obs. get added to the same obs. coll.
                    if 'collection uuid' in ret.keys():
                        mav_obs_collection = ret['collection uuid']
            # out_q.put(gps)

        # sleep
        time.sleep(.1)


# run if main ##################################################################
if __name__ == "__main__":
    q = Queue()
    mavlink(q, {"address": 'tcp:127.0.0.1:5760'},
            'http://localhost:5000/api/v1/store/')
