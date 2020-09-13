## Data Acquisition Module

### Basic idea
The Data acquisition model is based around a sensor class based on ideas and some code from Teus Hagen's MySense, https://github.com/teusH/MySense/tree/master/RPi. The sensor class, ```data_acquisition_sensor```, contains configuration data,
```
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
```
to allow us to acquire data via means specific to the sensor.

There also exists sub-class of the sensor, ```data_acquisition_mavlink``` that handles MavLink serial data streams.

### Data logging
The main data logging loop ```data_acquisition``` keeps a python list of sensors for which it calls the ```start```, ```stop```, ```loop``` and ```update``` functions for each sensor within the acquisition loop (DAL).

Each sensor instance requires specific configuration information to populate ```CONFIG```, for example for GPS fix,
```
[geo_fix]
# config data, includes comms port
class = MavLink
CONFIG = { "interface":
            # wdt:P31 wd:Q385390
            {"type": "serial", 
            "address": "tcp:127.0.0.1:5761"},
            "filter": "GLOBAL_POSITION_INT",
            # calibration factors, here order 1
            "calibrations": [["lat", 0, 1e-7],["lon", 0, 1e-7],["alt", 0, 1e-3]],
            "fields": ["lat", "lon", "alt"],
            "output_template": "POINT(_{lat} _{lon} _{alt})",
            "units": ["http://www.opengis.net/ont/geosparql#wktLiteral"] }
```

Here, calling the sensor ```loop``` grabs the leases messages filtered by ```GLOBAL_POSITION_INT```, generates a GPS POINT with units ```wktLiteral```. Calling ```update``` gets the latest data.

For a temperature sensor we use the concept of a driver for a Raspberry Pi companion device. Here,
```
[B6SZtaATTF2eRx4l_z51MQ]
class = Sensor
# config data
CONFIG = { 
            # DS18B20
            # schema:manufacturer?
            "type": "Maxim",
            # sosa:observes
            "fields": ["DEG_C"],
            # ssn-system:Sensitivity [ssn-system:MeasurementRange]
            "sensitivity": [[0, 1, 1]],
            # sosa:isHostedBy?
            "interface": {
                # wdt:P31 ?
                "type": "1-wire", 
                "address": "0x28"},
            # handler
            "fd": "DS18B20_driver" }
```
Calling ```update``` calls an instance of ```DS18B20_driver``` in ```drivers/PI_drivers.py``` that returns the temperature.
