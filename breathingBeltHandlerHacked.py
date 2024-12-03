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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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
        self.device_list = []
        for device in self.devices:
            self.device_list.append(device)
            device.open(auto_start=False)
            print('found device: {0}'.format(device.name))
        # print('found devices: {0}'.format(godirect.list_devices()))

    def __del__(self):
        for device in self.devices:
        	device.stop()
        	device.close()
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
        print ('Beathing Belt {0} collection thread initialized'.format(self.device.name))

    def run(self):
            startTime = time.time()
            print ('Starting Beathing Belt {0} data collection'.format(self.name))
            while not self.stopEvent.is_set():
                currentTime = time.time()
                if self.device.read():
                    sensor_values = {}
                    for sensor in self.sensors:
                        value = sensor.value

                self.dataLock.acquire()
                self.dataQueue.put([int((currentTime - startTime) * 1000)] + [value])
                self.dataQueue.put([currentTime] + [value])

                self.dataLock.release()
            self.device.stop()
            self.device.close()

def open_device(device):
    print(f"Opening device: {device.name}")
    device.open(auto_start=True)
    print(f"Device {device.name} opened successfully.")