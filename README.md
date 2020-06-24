# py_drone_sim

Python Drone simulator to use ld.landrs.org.

To run,
```
python3 py_drone_sim.py Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg==
```

this will parse ld.landrs.org for FlightControlerBoard Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg== and setup an api on port 5000.

To access root
```
http://localhost:5000/
```
returns
```
{"myUrl": "http://ld.landrs.org/id/Mjc2MzRlZWUtZGRiYS00ZjE5LThjMDMtZDBmNDFjNmQzMTY0Cg==", "apiroot": "/api/v1",
"sensors": ["MmUwNzU4ZDctOTcxZS00N2JhLWIwNGEtNWU4NzAyMzY1YWUwCg==",
"Y2U1YThiZTYtZTljMC00ZWY3LTlmMzItZGZhZDk4MTJkNDExCg==", "OTNkMDI1YTctZGE4Ny00Y2IyLWI3MzgtMTU2YzVmMDU1MDI4Cg==",
"OGIxYjVjOGEtOTgwZS00NDZhLTgzNTAtMzYyMzZlMzhjZDQ3Cg==", "ZmI3YzQ5NzMtMGFhMi00MTNhLWJjNzUtZjBmNmMxNTBkNjA3Cg=="]}
```
which lists the 4 sensors. To view a sensor,
```
http://localhost:5000/api/v1/Y2U1YThiZTYtZTljMC00ZWY3LTlmMzItZGZhZDk4MTJkNDExCg==
```
returns,
```
{"sensor_comment": "THe BMI055 is an ultra-small, 6-axis inertial sensor, consisting of: A digital, triaxial 12bit
acceleration sensor and a digital, triaxial 16bit, \u00b12000\u00b0/s gyroscope"}
```
