import os
import csv
import time
import signal
import sys
import threading
import queue
import collections
import numpy as np
import logging
from breathingBeltHandlerHacked import GoDirectDevices
from BeltBreathRate import BreathRate

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

DIRECTORY_PATH = r"./data/belt" + time.strftime(u"%Y%m%d") + "/"

TERMINATE = False
threads = []
devices = None
rateQ = None

def graceful_exit(signum, frame):
    # 信号处理函数，用于接收到信号后优雅退出
    global TERMINATE
    logging.info("Received termination signal, will attempt graceful shutdown...")
    TERMINATE = True

def sensor_thread(device, rateQ):
    global TERMINATE
    name = device.name
    logging.info(f"Starting sensor_thread for device: {name}")

    device_dir = os.path.join(DIRECTORY_PATH, name)
    os.makedirs(device_dir, exist_ok=True)

    sensor_data_csv_path = os.path.join(device_dir, 'sensor_data_' + time.strftime(u"%Y%m%d%H%M%S") + '.csv')
    breathing_rate_csv_path = os.path.join(device_dir, 'breathing_rate_' + time.strftime(u"%Y%m%d%H%M%S") + '.csv')

    logging.info(f"Sensor CSV will be saved at: {os.path.abspath(sensor_data_csv_path)}")
    logging.info(f"Breathing Rate CSV will be saved at: {os.path.abspath(breathing_rate_csv_path)}")

    bbeltDataDeck = collections.deque(maxlen=15 * 10)
    dataLock = threading.Lock()
    startTime = time.time()
    stopEvent = threading.Event()

    with open(sensor_data_csv_path, 'a', newline='') as sensor_file, open(breathing_rate_csv_path, 'a', newline='') as rate_file:
        sensor_writer = csv.writer(sensor_file)
        rate_writer = csv.writer(rate_file)

        # 写入表头
        sensor_writer.writerow(["Timestamp_s", "Force", "Respiration Rate", "Step Rate", "Steps"])
        rate_writer.writerow(["Timestamp_s", "Breathing Rate"])
        sensor_file.flush()
        os.fsync(sensor_file.fileno())
        rate_file.flush()
        os.fsync(rate_file.fileno())

        t = threading.current_thread()
        try:
            if not TERMINATE:
                device.start(period=100)

            while getattr(t, "do_run", True) and not TERMINATE:
                currentTime = time.time()
                if TERMINATE:
                    break

                try:
                    if TERMINATE:
                        break

                    if device.read():
                        sensor_values = {}
                        for sensor in device.get_enabled_sensors():
                            if TERMINATE:
                                break
                            try:
                                value = sensor.value
                                if not isinstance(value, (int, float)):
                                    raise ValueError(f"Invalid sensor value: {value}")
                                sensor_values[sensor.sensor_description] = value
                            except Exception as e:
                                logging.error(f"Error reading sensor {sensor.sensor_description}: {e}")
                                sensor_values[sensor.sensor_description] = float('nan')

                        if TERMINATE:
                            break

                        sensor_values["timestamp_ms"] = int((currentTime - startTime) * 1000)
                        sensor_values["timestamp_s"] = currentTime

                        if {'Force', 'Respiration Rate', 'Step Rate', 'Steps', 'timestamp_s'}.issubset(sensor_values.keys()):
                            bbeltDataDeck.append(sensor_values)
                        else:
                            logging.warning(f"Invalid data structure: {sensor_values}")

                        if len(bbeltDataDeck) == 15 * 10 and not TERMINATE:
                            try:
                                beltData = np.array(
                                    [[d['Force'], d['Respiration Rate'], d['Step Rate'], d['Steps']] for d in bbeltDataDeck],
                                    dtype=float
                                )
                                timestamps = [d['timestamp_s'] for d in bbeltDataDeck]

                                logging.debug("Processing breathing rate data now...")
                                breathing_rate = BreathRate(beltData[:, 0])

                                dataLock.acquire()
                                rateQ.put(breathing_rate)
                                dataLock.release()

                                for i, row in enumerate(beltData):
                                    logging.debug("Writing sensor data now...")
                                    sensor_writer.writerow([timestamps[i]] + list(row))

                                sensor_file.flush()
                                os.fsync(sensor_file.fileno())

                                logging.debug("Writing breathing rate data now...")
                                rate_writer.writerow([timestamps[-1], breathing_rate])
                                rate_file.flush()
                                os.fsync(rate_file.fileno())

                                bbeltDataDeck.clear()

                            except Exception as e:
                                logging.error(f"Error processing bbeltDataDeck for device {name}: {e}")
                    else:
                        logging.warning(f"No data read from device {name}")
                except Exception as e:
                    logging.error(f"Error collecting data from device {name}: {e}")

                time.sleep(0.1)
        except Exception as e:
            logging.error(f"Error in sensor_thread for device {name}: {e}")
        finally:
            stopEvent.set()
            # 在finally中确保设备正常停止和关闭
            # 此时TERMINATE已设置，不会再有额外操作对设备进行I/O
            try:
                device.stop()
                device.close()
            except:
                pass

            logging.info(f"Data collection stopped for device {name}.")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, graceful_exit)
    signal.signal(signal.SIGTERM, graceful_exit)

    devices = GoDirectDevices()
    rateQ = queue.Queue()

    for device in devices.device_list:
        logging.info(f"Found device: {device}")
        sensors = device.list_sensors()
        print(f"device: {device} has sensors: {sensors}")
        device.enable_sensors([1, 2, 4, 5])

    for device in devices.device_list:
        t = threading.Thread(target=sensor_thread, args=(device, rateQ))
        t.do_run = True
        t.start()
        threads.append(t)

    try:
        while not TERMINATE and any(t.is_alive() for t in threads):
            while not rateQ.empty():
                rate = rateQ.get()
                logging.info(f"Breathing rate: {rate}")
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt received in main thread, setting TERMINATE=True...")
        TERMINATE = True
    finally:
        # 通知线程停止
        for t in threads:
            t.do_run = False

        # 等待线程结束
        for t in threads:
            t.join()

        # 确保设备关闭
        if devices and devices.device_list:
            for device in devices.device_list:
                try:
                    device.stop()
                    device.close()
                except:
                    pass

        logging.info("All threads and devices have been terminated.")
        sys.exit(0)
