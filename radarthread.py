import sys
import time
import os
import collections
import multiprocessing as mp
import numpy as np
import csv

from pymoduleconnector import ModuleConnector
from datetime import datetime

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
        self.radarObject = self.mc.get_xep() #file:///D:/Work/Xethru_Radar/Module%20Connector/doc/html/class_xe_thru_1_1_module_connector.xhtml#afbd85cf71a364a04fa2344b619cbe180
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
        # self.mc.close()
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

class Main:
    def __init__(self):
        general_path = r'C:\Users\chafi\Desktop\Radar_Project\Charlie_Code\data'
        self.radar_data_dir = general_path + '\\' + time.strftime(u"%Y%m%d")
        if not os.path.exists(self.radar_data_dir):
            os.makedirs(self.radar_data_dir)

        self.port = 'COM12'
        self.radar_fs = 17
        self.createRadarSettingsDict()
        self.dataQ = mp.Queue()
        self.dataDeque = collections.deque()
        self.stopEvent = mp.Event()
        self.radarThread = CollectionThreadX4MP(stopEvent=self.stopEvent, radarSettings=self.radarSettings,
                                                baseband=True, fs=self.radar_fs, dataQueue=self.dataQ,
                                                radarPort=self.port)
        self.csv_file = None
        self.csv_writer = None

    def createRadarSettingsDict(self):
        self.radarSettings = {}
        self.radarSettings['Iterations'] = 16
        self.radarSettings['DACMin'] = 949
        self.radarSettings['DACMax'] = 1100
        self.radarSettings['PulsesPerStep'] = 26
        self.radarSettings['FrameStart'] = 0
        self.radarSettings['FrameStop'] = 9.75
        self.radarSettings['DACStep'] = 1
        self.radarSettings['RADAR_RESOLUTION'] = 51.8617 / 1000
        self.radarSettings['RadarType'] = 'X4'

    def main(self):
        self.radarThread.start()

        file_path = os.path.join(self.radar_data_dir, "radar_data.csv")
        self.csv_file = open(file_path, "a", newline='')
        self.csv_writer = csv.writer(self.csv_file)

        try:
            while True:
                if not self.dataQ.empty():
                    buffer = self.dataQ.get()
                    if buffer != 'setup_error':
                        self.dataDeque.append(buffer)
                    else:
                        print('Buffer setup error')
                        self.safeExit()
                    rawData = self.dataDeque.copy()
                    frames = self.framesToNp(rawData)
                    self.writeData(frames)
                    self.dataDeque.clear()

        except KeyboardInterrupt:
            self.safeExit()
        finally:
            self.csv_file.close()

    def safeExit(self):
        self.radarThread.shutdown()
        self.radarThread.join()
        return

    def radarToNp(self, frame):
        frame = np.array(frame)
        n = len(frame)
        frame = frame[:n // 2] + 1j * frame[n // 2:]
        rdDataRowstr = [str(f).replace('(', '').replace(')', '') for f in frame]
        return rdDataRowstr

    def framesToNp(self, radar_list):
        times = [row[0] for row in radar_list]
        frames = [self.radarToNp(row[1]) for row in radar_list]
        times = np.asarray(times)
        frames = np.column_stack((times, frames))
        return frames

    def writeData(self, frames):
        for rdDataRow in frames:
            self.csv_writer.writerow(rdDataRow)

if __name__ == '__main__':
    mc = Main()
    mc.main()
