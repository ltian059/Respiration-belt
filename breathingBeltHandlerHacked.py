'''
Created on Dec 25, 2018

@author: rajitha
'''
import logging

# !pip install vernierpygatt
from godirect import GoDirect
USE_BLE = True
import time
godirect = GoDirect(use_ble=USE_BLE, use_usb=not USE_BLE)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

import time
import threading
import queue
import csv
import sys
import threading
import queue

from io import open
class GoDirectDevices():
    def __init__(self):
        self.devices = godirect.list_devices()
        # self.devices = godirect.get_device(threshold=-100)
        self.device_list = []
        for device in self.devices:
            device.open(auto_start=False)
            logging.info(f'Found and opened device: {device.name}')
            self.device_list.append(device)
        # print('found devices: {0}'.format(godirect.list_devices()))

    def __del__(self):
        for device in self.devices:
            try:
                device.stop()
                device.close()
                logging.info(f'Device {device.name} stopped and closed.')
            except Exception as e:
                logging.error(f'Error closing device {device.name}: {e}')
        godirect.quit()


class CollectionThreadGDXRBDummy(threading.Thread):
    def __init__(self, threadID, name, device, dataQueue=None, dataLock=None, stopEvent =  None):
        threading.Thread.__init__(self)
        self.name = name
        self.threadID = threadID
        self.stopEvent = stopEvent
        self.dataQueue = dataQueue
        self.dataLock = dataLock
        self.device = device
        print ('Before device opened')
        self.device.open(auto_start=True)
        print ('After device opened')
        self.sensors = self.device.get_enabled_sensors()
        logging.info(f'Beathing Belt {self.device.name} collection thread initialized.')

    def run(self):
            startTime = time.time()
            print ('Starting Beathing Belt {0} data collection'.format(self.name))
            while not self.stopEvent.is_set():
                currentTime = time.time()
                if self.device.read():
                    sensor_values = {}
                    for sensor in self.sensors:
                        try:
                            value = sensor.value
                            if not isinstance(value, (int, float)):
                                raise ValueError(f"Invalid sensor value:{value}")
                            sensor_values[sensor.sensor_description] = value
                        except Exception as e:
                            print(f"Error reading sensor {sensor.sensor_description}: {e}")
                            sensor_values[sensor.sensor_description] = float('nan')  # 默认设置为 NaN

                    # 获取所有传感器数据后，添加时间戳
                    sensor_values["timestamp_ms"] = int((currentTime - startTime) * 1000)
                    sensor_values["timestamp_s"] = currentTime
                    # 写入队列（线程安全）
                    # 确保数据仅写入一次
                    if sensor_values not in self.dataQueue.queue:
                        self.dataLock.acquire()
                        try:
                            self.dataQueue.put(sensor_values)
                        finally:
                            self.dataLock.release()
                    time.sleep(0.1)  # 减少对 CPU 的占用

            self.device.stop()
            self.device.close()
            logging.info(f'Beathing Belt {self.name} data collection stopped.')


