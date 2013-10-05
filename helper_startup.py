import shared
import ConfigParser
import sys
import os

tm = {}
#TODO: This loading function currently assumes that 
#the config file is called "ssllog.ini" and that it's
#stored in the same directory as the program code.
def loadconfig():
    # First try to load the config file  from the program
    # directory
    
    shared.config.read('ssllog.ini')
    
    #load the transaction map
    with open('AppLayer/TransactionStateMap.txt') as f:
        l = f.readlines()
        for x in l:
            name,num = x.split()
            tm[int(num)] = name