'''
Created on Dec 25, 2018

'''
import asyncio
import time
import collections
import subprocess
import os
import csv
import math
import logging
import datetime

import multiprocessing
# from processBR import processBR
import threading
import queue
import numpy as np
from breathingBeltHandlerHacked import CollectionThreadGDXRBDummy, GoDirectDevices
from BeltBreathRate import BreathRate
from multiprocessing.connection import Listener
# 设置日志记录
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

DIRECTORY_PATH = r"./data/belt" + time.strftime(u"%Y%m%d") + "/"
def sensor_thread_0(device, rateQ):
    name = device.name
    print(f"sensor_thread: name: {name}")
    if not os.path.exists(DIRECTORY_PATH + name + '/'):
        os.makedirs(DIRECTORY_PATH + name + '/')

    # CSV file paths
    sensor_data_csv_path = os.path.join(DIRECTORY_PATH + name + '/', 'sensor_data_' + time.strftime(u"%Y%m%d%H%M%S") + '.csv')
    breathing_rate_csv_path = os.path.join(DIRECTORY_PATH + name + '/', 'breathing_rate_' + time.strftime(u"%Y%m%d%H%M%S") + '.csv')

    bbeltDataLock = threading.Lock()
    stopEvent = threading.Event()
    bbeltDataQ = queue.Queue()

    try:
        # Initialize the collection thread
        logging.info("Initializing CollectionThreadGDXRBDummy...")
        bbeltThread = CollectionThreadGDXRBDummy(
            threadID=1, name=name, device=device,
            dataQueue=bbeltDataQ, dataLock=bbeltDataLock,
            stopEvent=stopEvent
        )
        logging.info("CollectionThreadGDXRBDummy initialized.")
        bbeltThread.start()
        logging.info("Thread started.")

        bbeltDataDeck = collections.deque(maxlen=15 * 10)
        t = threading.current_thread()

        # Open CSV files for writing
        with open(sensor_data_csv_path, 'w', newline='') as sensor_file, open(breathing_rate_csv_path, 'w', newline='') as rate_file:
            sensor_writer = csv.writer(sensor_file)
            rate_writer = csv.writer(rate_file)

            # Write headers
            sensor_writer.writerow(["Timestamp_s", "Force", "Respiration Rate", "Step Rate", "Steps"])
            rate_writer.writerow(["Timestamp_s", "Breathing Rate"])

            try:
                while getattr(t, "do_run", True):
                    if not bbeltDataQ.empty():
                        while not bbeltDataQ.empty():
                            data = bbeltDataQ.get()
                            if isinstance(data, dict) and {'Force', 'Respiration Rate', 'Step Rate', 'Steps', 'timestamp_s'}.issubset(data.keys()):
                                bbeltDataDeck.append(data)
                            else:
                                logging.warning(f"Invalid data structure: {data}")

                        if len(bbeltDataDeck) == 15 * 10:
                            # Process data
                            try:
                                beltData = np.array(
                                    [[d['Force'], d['Respiration Rate'], d['Step Rate'], d['Steps']] for d in bbeltDataDeck],
                                    dtype=float
                                )
                                timestamps = [d['timestamp_s'] for d in bbeltDataDeck]

                                # Calculate breathing rate
                                breathing_rate = BreathRate(beltData[:, 0])

                                # Lock and queue breathing rate
                                bbeltDataLock.acquire()
                                rateQ.put(breathing_rate)
                                bbeltDataLock.release()

                                # Write sensor data to CSV
                                for i, row in enumerate(beltData):
                                    sensor_writer.writerow([timestamps[i]] + list(row))

                                # Write breathing rate to CSV
                                rate_writer.writerow([timestamps[-1], breathing_rate])

                                bbeltDataDeck.clear()

                            except Exception as e:
                                logging.error(f"Error processing bbeltDataDeck: {e}")

                    time.sleep(0.1)  # Small delay to prevent high CPU usage
            except Exception as e:
                logging.error(f"Error in sensor_thread: {e}")
            finally:
                stopEvent.set()
                bbeltThread.join()
    except Exception as e:
        logging.error(f"Error initializing sensor_thread: {e}")
def sensor_thread(device, rateQ):
    name = device.name
    logging.info(f"Starting sensor_thread for device: {name}")

    # Create directory for device data
    device_dir = os.path.join(DIRECTORY_PATH, name)
    os.makedirs(device_dir, exist_ok=True)

    # CSV file paths
    sensor_data_csv_path = os.path.join(device_dir, 'sensor_data_' + time.strftime(u"%Y%m%d%H%M%S") + '.csv')
    breathing_rate_csv_path = os.path.join(device_dir, 'breathing_rate_' + time.strftime(u"%Y%m%d%H%M%S") + '.csv')

    # Initialize data structures
    bbeltDataDeck = collections.deque(maxlen=15 * 10)
    dataLock = threading.Lock()
    stopEvent = threading.Event()

    logging.info(f"Data collection started for device: {name}")
    startTime = time.time()

    # Open CSV files for writing
    with open(sensor_data_csv_path, 'w', newline='') as sensor_file, open(breathing_rate_csv_path, 'w', newline='') as rate_file:
        sensor_writer = csv.writer(sensor_file)
        rate_writer = csv.writer(rate_file)

        # Write headers
        sensor_writer.writerow(["Timestamp_s", "Force", "Respiration Rate", "Step Rate", "Steps"])
        rate_writer.writerow(["Timestamp_s", "Breathing Rate"])

        t = threading.current_thread()
        try:
            device.start(period=100)
            while getattr(t, "do_run", True):
                currentTime = time.time()
                try:
                    if device.read():
                        sensor_values = {}
                        for sensor in device.get_enabled_sensors():
                            try:
                                value = sensor.value
                                if not isinstance(value, (int, float)):
                                    raise ValueError(f"Invalid sensor value: {value}")
                                sensor_values[sensor.sensor_description] = value
                            except Exception as e:
                                logging.error(f"Error reading sensor {sensor.sensor_description}: {e}")
                                sensor_values[sensor.sensor_description] = float('nan')

                        # Add timestamps
                        sensor_values["timestamp_ms"] = int((currentTime - startTime) * 1000)
                        sensor_values["timestamp_s"] = currentTime

                        # Add data to deck
                        if {'Force', 'Respiration Rate', 'Step Rate', 'Steps', 'timestamp_s'}.issubset(sensor_values.keys()):
                            bbeltDataDeck.append(sensor_values)
                        else:
                            logging.warning(f"Invalid data structure: {sensor_values}")

                        if len(bbeltDataDeck) == 15 * 10:
                            # Process data
                            try:
                                beltData = np.array(
                                    [[d['Force'], d['Respiration Rate'], d['Step Rate'], d['Steps']] for d in bbeltDataDeck],
                                    dtype=float
                                )
                                timestamps = [d['timestamp_s'] for d in bbeltDataDeck]

                                # Calculate breathing rate using the first column (Force)
                                breathing_rate = BreathRate(beltData[:, 0])

                                # Lock and queue breathing rate
                                dataLock.acquire()
                                rateQ.put(breathing_rate)
                                dataLock.release()

                                # Write sensor data to CSV
                                for i, row in enumerate(beltData):
                                    sensor_writer.writerow([timestamps[i]] + list(row))

                                # Write breathing rate to CSV
                                rate_writer.writerow([timestamps[-1], breathing_rate])

                                bbeltDataDeck.clear()

                            except Exception as e:
                                logging.error(f"Error processing bbeltDataDeck for device {name}: {e}")
                    else:
                        logging.warning(f"No data read from device {name}")
                except Exception as e:
                    logging.error(f"Error collecting data from device {name}: {e}")

                time.sleep(0.1)  # Small delay to prevent high CPU usage
        except Exception as e:
            logging.error(f"Error in sensor_thread for device {name}: {e}")
        finally:
            stopEvent.set()
            device.stop()
            device.close()
            logging.info(f"Data collection stopped for device {name}.")

if __name__ == "__main__":
    devices = GoDirectDevices()
    threads = []

    rateQ = queue.Queue()

    # Initialize devices and enable sensors in the main thread
    for device in devices.device_list:
        logging.info(f"Found device: {device}")
        sensors = device.list_sensors()
        print(f"device: {device} has sensors: {sensors}")
        device.enable_sensors([1, 2, 4, 5])
        # t = threading.Thread(target=sensor_thread, args=(device, rateQ))
        # t.do_run = True
        # t.start()
        # threads.append(t)

    # Start data collection threads
    for device in devices.device_list:
        # device.open(auto_start=True)
        t = threading.Thread(target=sensor_thread, args=(device, rateQ))
        t.do_run = True
        t.start()
        threads.append(t)

    try:
        while any(t.is_alive() for t in threads):
            while not rateQ.empty():
                rate = rateQ.get()
                logging.info(f"Breathing rate: {rate}")
            time.sleep(1)  # Small delay to prevent high CPU usage
    except KeyboardInterrupt:
        logging.info("Terminating program.")
    finally:
        for t in threads:
            t.do_run = False
            t.join()

        # Ensure all devices are properly stopped and closed
        for device in devices.device_list:
            device.stop()
            device.close()

        logging.info("All threads and devices have been terminated.")
