# -*- coding: utf-8 -*-
"""
Created on Wed May 25 11:48:01 2022

@author: owenh
"""

try:
    while True:
        print("Program is running")
except KeyboardInterrupt:
    print("Oh! you pressed CTRL + C.")
    print("Program interrupted.")
finally:
    print("This was an important code, ran at the end.")