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
from queue import Queue

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
def mavlink_loop(out_q, mavlink_dict):
    #get config
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
        #read returns the last gps value
        gps = read_loop(master)

        if gps != None:
            #scale mavlink
            gps['lat'] = str(float(gps['lat']) * 1e-7)
            gps['lon'] = str(float(gps['lon']) * 1e-7)
            gps['alt'] = str(float(gps['alt']) * 1e-3)

            print("GPS lat", gps['lat'],"long", gps['lon'], "alt", gps['alt'])
            out_q.put(gps)

        #sleep
        time.sleep(3)

#run if main
if __name__ == "__main__":
    q = Queue()
    mavlink_loop(q, {"address": 'tcp:127.0.0.1:5760'})
