'''
Created on Dec 25, 2018

@author: rajitha
'''
import logging
import threading
# !pip install vernierpygatt
import time


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


