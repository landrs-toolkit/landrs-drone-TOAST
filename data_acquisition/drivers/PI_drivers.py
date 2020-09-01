'''
Raspberry Pi drivers for py_drone_toast.

Chris Sweet 09/01/2020
University of Notre Dame, IN
LANDRS project https://www.landrs.org
'''
# Imports ######################################################################
import os
import glob
import time

##############################################
# Driver class for DS18B20 temperature sensor
##############################################
class DS18B20_driver():


    ##############################
    # initialize class
    ##############################
    def __init__(self):
        # check platform
        if os.uname()[4].startswith('arm'):
            self.arm = True
        
            # These two lines mount the device:
            os.system('modprobe w1-gpio')
            os.system('modprobe w1-therm')
        
            self.base_dir = '/sys/bus/w1/devices/'
            # Get all the filenames begin with 28 in the path base_dir.
            self.device_folder = glob.glob(self.base_dir + '28*')[0]
            self.device_file = self.device_folder + '/w1_slave'
        else:
            self.arm = False
            print("Not ARM device!")

    ##############################
    # Get sensor id
    ##############################
    def read_rom(self):
        '''
        Returns:
            str: sensor id
        '''
        if not self.arm:
            return -1
        name_file=self.device_folder+'/name'
        f = open(name_file,'r')
        return f.readline()
    
    ##############################
    # Read sensor raw data
    ##############################
    def read_temp_raw(self):
        '''
        Returns:
            str: sensor raw data
        '''
        if not self.arm:
            return -1
        f = open(self.device_file, 'r')
        lines = f.readlines()
        f.close()
        return lines
    
    ##############################
    # Get values
    ##############################
    def get_values(self):
        '''
        Returns:
            str: sensor calibrated value
        '''
        if not self.arm:
            return -1
        lines = self.read_temp_raw()
        # Analyze if the last 3 characters are 'YES'.
        while lines[0].strip()[-3:] != 'YES':
            time.sleep(0.2)
            lines = self.read_temp_raw()
        # Find the index of 't=' in a string.
        equals_pos = lines[1].find('t=')
        if equals_pos != -1:
            # Read the temperature .
            temp_string = lines[1][equals_pos+2:]
            temp_c = float(temp_string) / 1000.0
            return temp_c
 
# run if main ##################################################################
if __name__ == "__main__": 
    my_temp_class = DS18B20_driver()

    print(' rom: '+ my_temp_class.read_rom())
    while True:
        print(' C=%3.3f '% my_temp_class.get_values())
        time.sleep(1)

