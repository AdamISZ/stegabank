softwareVersion = '0.0.1'
verbose = 1
import os
import inspect
import platform
import ConfigParser
import subprocess

#instantiate globals before populating
#them from config
#==========================================


#ssllog_installdir is the dir from which main.py is run

config = ConfigParser.ConfigParser()
OS = platform.system()

#platform independent strip and split text string output (e.g. from console)
def pisp(x):
    #clean out whitespace if necessary
    x=x.rstrip()
    if OS == 'Windows':
        return x.split('\r\n')
    elif OS == 'Linux':
        return x.split('\n')
    else:
        debug(0,["Error in split function: OS not recognized. Quitting."])
        exit()

#elementary debug calls with different levels:
def debug(level,message):
    if level <= int(config.get("Debug","level")):
        print 'function: ', inspect.stack()[1][3], \
        ': ',' '.join(str(x) for x in message)
        
#this function checks if a file already exists, and either confirms
#overwriting or changes the filename to be used as appropriate
#if creating a new file, it will be in the same directory
#This is the usual functionality.
#In some unusual cases (e.g. mergecap) it's essential to remove the
#previously existing file, otherwise processing cannot continue.
#This is the purpose of the force_overwrite flag.
def verify_file_creation(file,warning,force_overwrite=False):
    
    try:
        while (True):
            if (os.path.isfile(file)):
                answer = raw_input("Warning: " + warning +   \
                                " Do you want to overwrite file? [Y/N]")
                if (answer in ['y','Y']):
                    os.remove(file)
                    return file
                elif (answer not in ['n','N']):
                    print "Unrecognized input. Please enter Y/y/N/n (one character)"
                else:
                    if (force_overwrite):
                        print "You have chosen not to overwrite. Program will quit."
                        exit()
                    else:
                        answer2 = raw_input("Please enter new name for \
                        output file. \n (give filename only, \
                        directory will be the same):")
                        file = os.path.join(os.path.dirname(file),answer2)
                    
            else:
                return file              
    except:
        debug(0,["Failed trying to create file: ",file,". Quitting!"])
        exit()