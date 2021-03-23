import serial
import time
import csv
import os
from pathlib import Path
import minimalmodbus as mm
import datetime as dt
import pandas as pd
import numpy as np
import RPi.GPIO as GPIO
import Adafruit_DHT

pd.set_option('display.max_columns', 10)


class Instrument:
    """
    Used to get and log data from Instruments rs485 CAN Hat
    
    Params:
    address_sensor = The sensor you want
    
    Example:
    >>> sensor_1 = Instrument(address_sensor=1)
    >>> sensor_1.read_temp()
    98.6
    
    """
    
    def __init__(self, address_sensor=1, moist_lvl = 20,
                 debug=False, grow_date='1-1-2020'):
        
        self.instr = mm.Instrument('/dev/ttyS0', address_sensor, debug=debug)
        self.sensor = address_sensor
        self.instr.serial.baudrate=9600
        self.grow_date = grow_date
        self.water_time = 15
        self.oscillate = 2
        self.moisture_lvl_maintain = moist_lvl
        self.readings_map = {'pH' : 0x06,
                             'soil_moist' : 0x12,
                             'nitrogen' : 0x1e,
                             'potassium' : 0x20,
                             'phosphorus' : 0x1f,
                             'electrical_conductivity' : 0x15,
                             'temp' : 0x13}
        self.pins =  {'p_pump_1' : 5,
                      'p_pump_2' : 13,
                      'main_water_pump' : 20,
                      'trashcan' : 26,
                      'temp_humid_pin' : 24}
        
        self.DHT_SENSOR = Adafruit_DHT.DHT11
        self.DHT_PIN = self.pins['temp_humid_pin']
        
        
    def temp_humidity(self):
        
        humidity, temperature = Adafruit_DHT.read_retry(self.DHT_SENSOR, self.DHT_PIN)

        if humidity is not None and temperature is not None:
            # Leaf Temp typically 1-3 C cooler on average
            tmp = temperature - 2.5
            svp =  (610.78 * (2.71828 ** (tmp / (tmp + 238.3) * 17.2694))) / 1000
            vpd = round(svp * (1 - (humidity / 100)), 3)
            far = round(temperature * (9 / 5) + 32, 2)
            now = dt.datetime.strftime(dt.datetime.now(), '%m-%d-%Y %H:%M:%S')
            print(f"Datetime : {now}")
            print(f"Temp={far}*F / {temperature}*C  Humidity={humidity}%")
            print(f"VPD = {vpd} kPa\n")
            data = [now, far, temperature, humidity, vpd]
            self.temp_humid_frame = pd.DataFrame([data], columns=['Datetime','Fahrenheit','Celsius','RelHumidity','VPD'])
            
            return self.temp_humid_frame
        
    def water_control(self):

        # loop through pins and set mode and state to 'high'

        for k,v in self.pins.items():
            if k == 'trashcan':
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(v, GPIO.OUT)
                GPIO.output(v, GPIO.HIGH)

                try:
                  GPIO.output(v, GPIO.LOW)
                  print (f"Pin {v}")
                  time.sleep(self.water_time)

                # End program cleanly with keyboard
                except KeyboardInterrupt:
                  print ("  Quit")

                  # Reset GPIO settings
                  GPIO.cleanup()
              
        GPIO.cleanup()
        print ("Good bye!")
        
        
        
    def run_stats(self, file_obj):
        
        self.plantFrame = pd.read_csv(file_obj, parse_dates=['Datetime'], index_col='Datetime').loc[self.growdate:]
        self.dailyFrame = self.plantFrame.resample('D').mean()
        today = dt.datetime.now().date().strftime('%m-%d-%Y')
        
        print('####################\n')
        print(f'Week Averages: \n')
        print(self.dailyFrame.tail(7))
        print('####################\n')
                
        self.dailyFrame.tail(7).to_csv(f'sensor_data_{self.sensor}_WeekAvg.csv', mode='w', header=True)

        
        
    def log_data(self):
        
        x = 0
        self.water_count = 0
        path = os.getcwd() + f'/sensor_data_{self.sensor}.csv'
        is_log_file = os.path.isfile(path)
        
        while True:
            data = self.read_all()
            self.plantFrame = pd.read_csv(path, parse_dates=['Datetime'],
                                          index_col='Datetime').loc[self.grow_date:].fillna(method='ffill')
            df = pd.DataFrame(data, index=[0]).set_index('Datetime')
            self.temp_humid_frame.set_index('Datetime', inplace=True)
            
            finalFrame = pd.merge(df, self.temp_humid_frame,
                                   left_index=True,
                                   right_index=True,
                                   how='inner')

            if is_log_file:
                finalFrame.to_csv(f'sensor_data_{self.sensor}.csv', mode='a', header=False)
                self.water_count = self.plantFrame['WaterCount'].iloc[-1]
                
            else:
                finalFrame.to_csv(f'sensor_data_{self.sensor}.csv', mode='w', header=True)
                finalFrame['WaterCount'] = self.water_count
                
                
#             finalFrame['TimeDelta'] = finalFrame.index[-1] - self.plantFrame.index[-1]      
            ref_moisture_value = self.plantFrame['Moisture'].shift(self.oscillate).iloc[-1]
            
            if  ref_moisture_value < self.moisture_lvl_maintain:
                print(f'Reference Moisture : {ref_moisture_value}')
                self.water_control()
                self.water_count += 1
                finalFrame['WaterCount'] = self.water_count
                
            else:
                finalFrame['WaterCount'] = self.water_count
                
            print(f'Current Water count : {self.water_count}')
            x += 1
        
            print('####################\n')
            print('Current Readings: \n')
            print(finalFrame)
            
            if x % 200 == 0:
                with open(f'sensor_data_{self.sensor}.csv', 'r') as r:
                    #self.run_stats(r)
                    pass
                
            time.sleep(900)


    def read_pH(self) -> float:
        """
        Gets Soil pH Reading in pH
        """
        return self.instr.read_register(self.readings_map['pH'],2)
    
    def read_ec(self, ppm=True) -> float:
        """
        Gets Soil electrical conductivity Reading in ppm or us/cm
        Default ppm
        """
        if ppm:
            return round(self.instr.read_register(self.readings_map['electrical_conductivity']) / 1.58, 2)
        else:
            return self.instr.read_register(self.readings_map['electrical_conductivity'])

    def read_temp(self, fahren=True) -> float:
        """
        Gets Soil Temp Reading in degrees
        default Fahrenheit
        """
        if fahren:
            return round(self.instr.read_register(self.readings_map['temp'], 1) * 1.8 + 32, 2)
        else:
            return self.instr.read_register(self.readings_map['temp'], 1)
        
    def read_npk(self) -> dict:
        """
        Gets Soil NPK Reading in mg/kg
        """
        return { x : self.instr.read_register(self.readings_map[x]) for x in
                 ['nitrogen','phosphorus','potassium']}
    
    def read_moisture(self) -> float:
        """
        Gets Soil Moisture Reading in %
        """
        return self.instr.read_register(self.readings_map['soil_moist'], 1)
    
    def read_all(self) -> dict:
        """
        Returns all readings in a dict
        """
        npk = self.read_npk()
        self.temp_humidity()

        
        self.readings =  { 'Datetime' : dt.datetime.now().strftime('%m-%d-%Y %H:%M:%S'),
                      'Temp' : self.read_temp(),
                      'pH' : self.read_pH(),
                      'EC' : self.read_ec(),
                      'Moisture' : self.read_moisture(),
                      'Nitrogen' : npk['nitrogen'],
                      'Phosphorus' : npk['phosphorus'],
                      'Potassium' : npk['potassium']}
        
        return self.readings
                     
        
        
    
if __name__ == '__main__':
    import time

    npk = Instrument(grow_date = '3-21-2020')
    npk.log_data()
