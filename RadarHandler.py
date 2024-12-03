# -*- coding: utf-8 -*-
"""
Created on Fri May 27 13:18:51 2022

@author: owenh
"""

import time
import csv
import os
import numpy as np
from io import open
import multiprocessing as mp
from datetime import datetime
from pymoduleconnector import ModuleConnector

class CollectionThreadX4MP(mp.Process):
    def __init__(self, stopEvent, radarSettings, baseband = True, fs = 17, radarPort='/dev/ttyACM0', dataQueue=None):
        mp.Process.__init__(self)
        self.exit = mp.Event()
        self.stopEvent = stopEvent
        self.radarDataQ = dataQueue
        self.radarPort = radarPort
        self.radarSettings = radarSettings
        self.fs = fs
        self.baseband = baseband
        print ('Collection thread initialized')

    def run(self):
        print ('Initializing radar')
        now = datetime.now()
        date_time = now.strftime("%H%M%S")

        self.reset(self.radarPort)
        self.mc = ModuleConnector(self.radarPort)
        self.radarObject = self.mc.get_xep()
        while self.radarObject.peek_message_data_float():
            self.radarObject.read_message_data_float()

        # Set DAC range
        time.sleep(3)
        self.radarObject.x4driver_set_dac_min(self.radarSettings['DACMin'])
        self.radarObject.x4driver_set_dac_max(self.radarSettings['DACMax'])

        # Set integration
        self.radarObject.x4driver_set_iterations(self.radarSettings['Iterations'])
        self.radarObject.x4driver_set_pulses_per_step(self.radarSettings['PulsesPerStep'])
        self.radarObject.x4driver_set_frame_area(self.radarSettings['FrameStart'],self.radarSettings['FrameStop'])
        if self.baseband:
            self.radarObject.x4driver_set_downconversion(1)
        self.radarObject.x4driver_set_fps(self.fs)

        self.clearBuffer()
        startTime = time.time()
        print((self.radarObject.get_system_info(0x07)))

        print ('Started radar data collection')
        while not self.exit.is_set():
            currentTime = time.time()
            radarFrame = self.radarObject.read_message_data_float().get_copy()
            data=[currentTime, radarFrame]
            # data=[radarFrame]
            self.radarDataQ.put(data)

        self.radarObject.x4driver_set_fps(0) # stop the radar
        print('radar stopped')

    def reset(self,device_name):
        mc = ModuleConnector(device_name)
        r = mc.get_xep()
        r.module_reset()
        mc.close()
        time.sleep(3)

    def readFrame(self):
        """Gets frame data from module"""
        d = self.radarObject.read_message_data_float()
        return d.get_copy()

    def clearBuffer(self):
        """Clears the frame buffer"""
        while self.radarObject.peek_message_data_float():
            _ = self.radarObject.read_message_data_float()

    def shutdown(self):
        self.exit.set()
        print ("Shutdown of radar process initiated")
