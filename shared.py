softwareVersion = '0.0.1'
verbose = 1
import os
import platform
import ConfigParser
import subprocess

#instantiate globals before populating
#them from config
#==========================================


#ssllog_installdir is the dir from which main.py is run

config = ConfigParser.ConfigParser()
OS = platform.system()

#platform independent split text string output (e.g. from console)
def pisp(x):
    if OS == 'Windows':
        return x.split('\r\n')
    elif OS == 'Linux':
        return x.split('\n')
    else:
        print "Error in split function: OS not recognized"
        exit()

#elementary debug calls with different levels:
def debug(level,message):
    if level <= int(config.get("Debug","level")):
        print ' '.join(str(x) for x in message)