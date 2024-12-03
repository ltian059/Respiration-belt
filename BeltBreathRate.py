# -*- coding: utf-8 -*-
"""
Created on Thu Feb  6 22:50:50 2020

@author: Zixiong Han
"""
import numpy as np
from scipy import signal
from numpy import linspace
from scipy.interpolate import UnivariateSpline
from modwt import modwt, modwtmra

def Pre_process_sig(data):
    N=data.shape[0]
    data=data.reshape(N,)
    x_in=linspace(0,N-1,N)
    # First baseline removal
    spln = UnivariateSpline(x_in, data,k=4)
    nr_data=data-spln(x_in) # baseline removed
    #Second noise removal using wavelet
    wt=modwt(nr_data, 'sym4', 6)
    wtmra = modwtmra(wt, 'sym4')
    # Reconstruct the signal using band [2,3,4,5]
    rec_data=wtmra[2,:]+wtmra[3,:]+wtmra[4,:]+wtmra[5,:]
    rec_data=rec_data.reshape(rec_data.shape[0],1)

    return(rec_data) # The return signal type is NX1 numpy array , N ia the length of the signal

def welch_br_rate(data):
    fs = 10    #sampling rate
    data = data.reshape(150,1)
    data = np.transpose(data)
    # calculate psd with Blackman window
    f, Pxx_den = signal.welch(data, fs,'blackman',noverlap=100, nfft=2**16)
    # calculate the max and its index
    max_index=np.argmax(Pxx_den)
    # check the value at that point
    freq = f[max_index]
    #Breathing rate
    br_rate=freq*60
    return(br_rate)

def BreathRate(data):

    process_belt = Pre_process_sig(data)
    breath_rate = welch_br_rate(process_belt)

    return breath_rate
