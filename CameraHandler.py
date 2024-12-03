#import pyrealsense2 as rs
import numpy as np
import cv2
import threading
import time
import multiprocessing as mp
import os
import psutil


class CameraHandlerIMG(threading.Thread):
    def __init__(self, cameraBufferImg, camFs, compression = '.jpg'):
        threading.Thread.__init__(self)
        
        # Configure depth and color streams
        self.camNum = 0 
        self.capture = cv2.VideoCapture(self.camNum)  # 0 for webcam (RGB camera), 1 for thermal sensor (connecting thermal only)
        
        self.FPS = float(self.capture.get(5))     # Get the camera default FPS    
        self.camFs = float(camFs)       # Set the frame rate according to the value in config_TR.ini 
        
        self.Flag = self.capture.open(self.camNum)
        if self.Flag:
            print("Camera open successfully")
        else:
            print("Cannot open the video capture device")
        self.exit = threading.Event()
        self.cameraBufferImg = cameraBufferImg
        self.video_start = time.time()
        self.num_frames = 0
        self.compression = compression

    def shutdown(self):
        # cv2.destroyAllWindows()
        self.capture.release()
        self.exit.set()

    def run(self):
        
        print("Run!")
        # Initialization
        index = 1
        
        # loop
        while not self.exit.is_set():
            ret,frame = self.capture.read()
            # self.compression = '.jpg'
            # cvEncodeImage returns single-row matrix of type CV_8UC1 that contains encoded image as array of bytes.
            # https://stackoverflow.com/questions/44328645/interpreting-cv2-imencode-result
            img = cv2.imencode(self.compression,frame)[1].tostring()
            index = index + 1
            # For decimal int() is equivalent to floor()
            if index == int(self.FPS / self.camFs):
                index = 1
                self.cameraBufferImg.put(img)



