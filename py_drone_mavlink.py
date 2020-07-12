'''
Mavlink interface for py_drone_toast.
From a gist by Ben Boughton https://gist.github.com/benboughton1/dba72b1ca01aec86775e0e6c54a6067e
Also quotes # https://gist.github.com/vo/9331349

Subsequent coding,
Chris Sweet 06/24/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org

'''
# Imports ######################################################################
from pymavlink import mavutil
import time
import requests
import datetime
import json

###########
#read loop
###########
def read_loop(m):
    message = {}

    while True:
        msg = m.recv_match(blocking=False)

        # break loop once most recent messages have updated dict
        if not msg:
            #print(message) #['GLOBAL_POSITION_INT']['lat'])
            if 'GLOBAL_POSITION_INT' in message.keys():
                return message['GLOBAL_POSITION_INT']
            else:
                return None

        message[msg.get_type()] = msg.to_dict()

        # if msg.get_type() == 'GLOBAL_POSITION_INT':
        #    print(message['GLOBAL_POSITION_INT'])

#loop to read messages
def mavlink(in_q, mavlink_dict, api_callback):
    #keep running
    store_data = True

    #get config
    #get obs. collection, sensor
    mav_obs_collection = mavlink_dict.get('observation_collection', '*')
    mav_sensor = mavlink_dict.get('sensor', 'MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==')

    #address
    address = mavlink_dict.get('address', 'tcp:127.0.0.1:5760')
    #rate
    try:
        rate = int(mavlink_dict.get('rate', '10'))
    except:
        rate = 10

    #setup connection
    master = mavutil.mavlink_connection(address, 115200, 255)

    master.wait_heartbeat()

    #setup data streams
    master.mav.request_data_stream_send(
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL,    # stream id
        rate,                                     # message rate hertz
        1                                       # 1 start, 0 stop
    )

    #loop until the end of time
    while True:
        #Queue
        if not in_q.empty():
            mess = in_q.get()
            print(mess)
            if mess == "stop":
                store_data = False
            if mess == "start":
                store_data = True

        #read returns the last gps value
        if store_data:
            #read link
            gps = read_loop(master)

            if gps != None:
                #scale mavlink
                gps['lat'] = str(float(gps['lat']) * 1e-7)
                gps['lon'] = str(float(gps['lon']) * 1e-7)
                gps['alt'] = str(float(gps['alt']) * 1e-3)

                #add type and time
                gps.update({ "type": "gps"})

                #create timestamp, may be in stream
                ts = datetime.datetime.now().isoformat()
                gps.update({ "time_stamp": str(ts)})

                #create parameters
                datas = {"data": json.dumps(gps)}

                print("GPS lat", gps['lat'],"long", gps['lon'], "alt", gps['alt'])

                #post
                r = requests.post(api_callback + mav_obs_collection + '/' + mav_sensor, params=datas)
                #print(r.content)

                #parse return
                ret = json.loads(r.text)
                #if we used * the we should get back a obs coll uuid
                if 'collection uuid' in ret.keys():
                    mav_obs_collection = ret['collection uuid']
            #out_q.put(gps)

        #sleep
        time.sleep(3)

#run if main
if __name__ == "__main__":
    q = Queue()
    mavlink(q, {"address": 'tcp:127.0.0.1:5760'}, 'http://localhost:5000/api/v1/store/')
