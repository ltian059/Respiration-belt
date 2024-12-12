'''
Created on Dec 25, 2018
'''
import collections
import csv
import json
import logging
import msvcrt
import os
import queue
import signal
import sys
import threading
import time
import traceback

import numpy as np
from godirect import GoDirect

from BeltBreathRate import BreathRate

def setup_logging(logging_level_str):
    """Set up logging based on a given logging level string."""
    logging_levels = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL
    }
    logging_level = logging_levels.get(logging_level_str.lower(), logging.INFO)
    # Reconfigure logging to ensure proper log level and format
    for handler in logging.root.handlers[:]:  # Clear existing handlers
        logging.root.removeHandler(handler)
    # Logging to both console (stdout) and a file (application.log)
    logging.basicConfig(
        level=logging_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("application.log", mode='a', encoding='utf-8')
        ]
    )

def load_config(config_path='belt_config.json'):
    """Load configuration from the given JSON config file.
       If the file is missing or invalid, create or fallback to a default config."""
    # Temporary minimal logging setup to ensure critical messages are logged
    if not logging.getLogger().hasHandlers():  # Prevent duplicate handlers
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),  # Log to console
                logging.FileHandler("application.log", mode='a', encoding='utf-8')  # Log to file
            ]
        )
    default_config = {
        "use_ble": True,
        "directory_path": "./data/belt_",
        "sensor_data_file_name": "sensor_data",
        "breath_rate_file_name": "breath_data",
        "file_name_timestamp": True,
        "logging_level": "info",
        "file_name_include_device_name": True,
        "period": 100
    }
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        # If config file not found, create a default one.
        logging.error(f"configuration file {config_path} not found, generating default config.")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
            logging.info(f"Default config file has been created in {config_path}. Edit as needed.")
        except Exception as e:
            logging.error(f"Error generating default config file: {e}")
        return default_config
    except json.JSONDecodeError as e:
        # If the JSON is malformed, fallback to default and warn the user.
        logging.error(
            f"Error resolving config file: {e}. Using default config.\nDefault Config: USE_BLE=True; LOGGING_LEVEL=info; DIRECTORY_PATH=./data/belt_currentdate."
        )
        return default_config

class GoDirectDevices:
    def __init__(self, godirect, use_ble):
        self.device_list = []
        self.godirect = godirect
        try:
            all_devices = self.godirect.list_devices()
        except Exception as e:
            logging.error(f"Error: {e} when finding devices via {'BLE' if use_ble else 'USB'}")
            raise

        if use_ble and not all_devices:
            logging.error("No devices found via BLE.")
            raise RuntimeError("No devices found via BLE.")
        if not use_ble and not all_devices:
            logging.error("No devices found via USB.")
            raise RuntimeError("No devices found via USB.")

        # self.devices = godirect.list_devices()
        # self.devices = godirect.get_device(threshold=-100)
        self.device_list = []
        for device in all_devices:
            try:
                # Try to open the device
                device.open(auto_start=False)
                logging.info(f'Found and opened device: {device.name}')
                self.device_list.append(device)
            except Exception as e:
                # If we fail to open the device (e.g. because it's already connected elsewhere), skip it
                logging.warning(f"Failed to open device {device.name}: {e}")
                # device could be ignored at this point, not appended to self.device_list

    def __del__(self):
        # Attempt to close all devices on object deletion.
        # Note: __del__ may not always be called reliably at program exit.
        for device in self.device_list:
            try:
                device.stop()
                device.close()
                logging.info(f'Device {device.name} stopped and closed.')
            except Exception as e:
                logging.error(f'Error closing device {device.name}: {e}')
        # Quit the GoDirect instance
        self.godirect.quit()

def sensor_thread(device, rateQ, terminate_event, directory_path, period, sensor_data_file_name, breath_rate_file_name, file_name_timestamp, include_device_name):
    """Thread function to read sensor data from a device, write to CSV,
       compute breathing rate, and put results in a queue."""
    name = device.name
    logging.info(f"Starting sensor_thread for device: {name}")

    device_dir = os.path.join(directory_path, name)
    os.makedirs(device_dir, exist_ok=True)
    if include_device_name:
        sensor_data_csv_path = sensor_data_file_name + '_' + name
        breathing_rate_csv_path = breath_rate_file_name + '_' + name
    if file_name_timestamp:
        sensor_data_csv_path = sensor_data_file_name + '_' + time.strftime(u"%Y%m%d%H%M%S")
        breathing_rate_csv_path = breath_rate_file_name + '_' + time.strftime(u"%Y%m%d%H%M%S")


    sensor_data_csv_path = os.path.join(device_dir, sensor_data_csv_path + '.csv')
    breathing_rate_csv_path = os.path.join(device_dir, breathing_rate_csv_path + '.csv')


    logging.info(f"Sensor CSV will be saved at: {os.path.abspath(sensor_data_csv_path)}")
    logging.info(f"Breathing Rate CSV will be saved at: {os.path.abspath(breathing_rate_csv_path)}")

    bbeltDataDeck = collections.deque(maxlen=15 * 10)  # Store up to 150 samples (assuming 15Hz * 10s)
    dataLock = threading.Lock()
    startTime = time.time()

    try:
        with open(sensor_data_csv_path, 'a', newline='') as sensor_file, open(breathing_rate_csv_path, 'a', newline='') as rate_file:
            sensor_writer = csv.writer(sensor_file)
            rate_writer = csv.writer(rate_file)

            # Write CSV headers
            sensor_writer.writerow(["Timestamp_s", "Force", "Respiration Rate", "Step Rate", "Steps"])
            rate_writer.writerow(["Timestamp_s", "Breathing Rate"])
            sensor_file.flush()
            os.fsync(sensor_file.fileno())
            rate_file.flush()
            os.fsync(rate_file.fileno())

            # Start the device data acquisition
            device.start(period=period)

            while not terminate_event.is_set():
                currentTime = time.time()
                try:
                    if device.read():
                        # If we got data, extract sensor values
                        sensor_values = {}
                        for sensor in device.get_enabled_sensors():
                            try:
                                value = sensor.value
                                if not isinstance(value, (int, float)):
                                    raise ValueError(f"Invalid sensor value: {value}")
                                sensor_values[sensor.sensor_description] = value
                            except Exception as e:
                                # If reading a sensor fails, log error and set value to NaN
                                logging.error(f"Error reading sensor {sensor.sensor_description}: {e}")
                                sensor_values[sensor.sensor_description] = float('nan')

                        sensor_values["timestamp_ms"] = int((currentTime - startTime) * 1000)
                        sensor_values["timestamp_s"] = currentTime

                        required_keys = {'Force', 'Respiration Rate', 'Step Rate', 'Steps', 'timestamp_s'}
                        if required_keys.issubset(sensor_values.keys()):
                            bbeltDataDeck.append(sensor_values)
                        else:
                            logging.warning(f"Invalid data structure: {sensor_values}")

                        # If we have collected enough data (150 samples), process it
                        if len(bbeltDataDeck) == 15 * 10 and not terminate_event.is_set():
                            try:
                                beltData = np.array(
                                    [[d['Force'], d['Respiration Rate'], d['Step Rate'], d['Steps']] for d in bbeltDataDeck],
                                    dtype=float
                                )
                                timestamps = [d['timestamp_s'] for d in bbeltDataDeck]

                                logging.debug("Processing breathing rate data now...")
                                # Compute breathing rate from the first column (Force)
                                breathing_rate = BreathRate(beltData[:, 0])

                                with dataLock:
                                    rateQ.put(breathing_rate)

                                # Write sensor data rows
                                for i, row in enumerate(beltData):
                                    logging.debug("Writing sensor data now...")
                                    sensor_writer.writerow([timestamps[i]] + list(row))

                                sensor_file.flush()
                                os.fsync(sensor_file.fileno())

                                logging.debug("Writing breathing rate data now...")
                                rate_writer.writerow([timestamps[-1], breathing_rate])
                                rate_file.flush()
                                os.fsync(rate_file.fileno())

                                # Clear the deck after processing
                                bbeltDataDeck.clear()

                            except Exception as e:
                                logging.error(f"Error processing bbeltDataDeck for device {name}: {e}")
                    else:
                        # If device.read() returned False, no new data is available
                        logging.warning(f"No data read from device {name}")
                except Exception as e:
                    logging.error(f"Error collecting data from device {name}: {e}")
                    # Break out of the loop if a critical error occurs during data collection
                    break
                time.sleep(0.1)

    except Exception as e:
        # If there's an unexpected error setting up the files or starting the device
        logging.error(f"Unexpected error in sensor_thread for device {name}: {e}")
        traceback.print_exc()
    finally:
        # Ensure device is stopped and closed even if we had errors
        try:
            device.stop()
            device.close()
            logging.info(f"Device {name} stopped and closed.")
        except Exception as e:
            logging.error(f"Error stopping/closing device {name}: {e}")
        logging.debug(f"Data collection stopped for device {name}.")

def register_signal_handlers(terminate_event):
    """Register signal handlers for graceful shutdown."""
    def graceful_exit(signum, frame):
        logging.info("Received termination signal, attempting graceful shutdown...")
        terminate_event.set()
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

def run_main():
    config_path = r"belt_config.json"
    config = load_config(config_path)
    setup_logging(config.get("logging_level", "info"))

    USE_BLE = config.get("use_ble", True)
    DIRECTORY_PATH_BASE = config.get("directory_path", "./data/belt_")
    DIRECTORY_PATH = DIRECTORY_PATH_BASE + time.strftime("%Y%m%d") + "/"
    SENSOR_DATA_FILE_NAME = config.get("sensor_data_file_name", "sensor_data_")
    BREATH_RATE_FILE_NAME = config.get("breath_rate_file_name", "breath_rate_")
    INCLUDE_DEVICE_NAME = config.get("file_name_include_device_name", True)
    FILE_NAME_TIMESTAMP = config.get("file_name_timestamp", True)
    PERIOD = config.get("period", 100)

    os.makedirs(DIRECTORY_PATH, exist_ok=True)

    terminate_event = threading.Event()
    threads = []
    rateQ = queue.Queue()

    try:
        register_signal_handlers(terminate_event)
        devices = GoDirectDevices(godirect=GoDirect(use_ble=USE_BLE, use_usb=not USE_BLE), use_ble=USE_BLE)
        for device in devices.device_list:
            logging.info(f"Found device: {device}")
            sensors = device.list_sensors()
            print(f"device: {device} has sensors: {sensors}")
            device.enable_sensors([1, 2, 4, 5])

        for device in devices.device_list:
            t = threading.Thread(target=sensor_thread, args=(device, rateQ, terminate_event, DIRECTORY_PATH,
                                                             PERIOD,SENSOR_DATA_FILE_NAME,BREATH_RATE_FILE_NAME, FILE_NAME_TIMESTAMP,INCLUDE_DEVICE_NAME))
            t.do_run = True
            t.start()
            threads.append(t)

        while not terminate_event.is_set() and any(t.is_alive() for t in threads):
            while not rateQ.empty():
                rate = rateQ.get()
                logging.info(f"Breathing rate: {rate}")
            time.sleep(1)
    except Exception as e:
        logging.error(f"An error occurred in main execution: {e}")
        traceback.print_exc()
    finally:
        terminate_event.set()
        logging.info("Terminating all threads...")
        for t in threads:
            t.do_run = False

        for t in threads:
            t.join()
        if 'devices' in locals() and devices.device_list:
            for device in devices.device_list:
                try:
                    device.stop()
                    device.close()
                except Exception as e:
                    logging.error(f"Error stopping/closing device {device.name}: {e}")

        logging.info("All threads and devices have been terminated.\n\n\n")

if __name__ == "__main__":
    try:
        run_main()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        traceback.print_exc()
    finally:
        # Wait for user to press any key before exiting completely
        input("\nPress any key to exit...")
        print("\n\n")
        sys.exit(1)
