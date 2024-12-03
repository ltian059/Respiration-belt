# -*- coding: utf-8 -*-
"""
Created on Fri Mar 11 16:26:13 2022

@author: owenh
"""

import cv2 as cv
import os
import time

def video_demo():
    # 0 is webcam (default), thermal sensor is 1
    capture = cv.VideoCapture(2)
    FPS = capture.get(5)    # Get the default camera frame rate
    print("default FPS: ", FPS)

    videoWidth = int(capture.get(cv.CAP_PROP_FRAME_WIDTH))
    videoHeight = int(capture.get(cv.CAP_PROP_FRAME_HEIGHT))

    print("width: ",videoWidth)
    print("height: ",videoHeight)

    # Image path
    image_path = r'C:\Users\chafi\Desktop\Radar_Project\Charlie_Code\data\Camera'
    # Image directory
    directory = r'C:\Users\chafi\Desktop\Radar_Project\Charlie_Code\data\Camera'

    i = 0
    prev = 0
    frame_rate = 1
    while (True):
        # Invoke the camera
        ref, frame = capture.read()
        # Show the image, "frame" indicates the window name
        cv.imshow('frame', frame)

        os.chdir(image_path)

        # save the image according to setting frame rate
        time_elapsed = time.time() - prev
        if time_elapsed > 1./frame_rate:
            prev = time.time()
            cv.imwrite('Frame'+str(i)+'.jpg', frame)
            i += 1

        # Destroy all windows if detecting keyboard input "q"
        c = cv.waitKey(10) & 0xff
        if c == ord('q'):
            cv.destroyAllWindows()
            break


if __name__ == '__main__':
    cv.waitKey()
    video_demo()
