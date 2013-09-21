softwareVersion = '0.0.1'
verbose = 1
import os
import errno
import inspect
import platform
import ConfigParser
import subprocess
import re
import helper_startup

config = ConfigParser.ConfigParser()
helper_startup.loadconfig()
OS = platform.system()
PINL = '\r\n' if OS == 'Windows' else '\n'
hexdigits = set('0123456789abcdefABCDEF')

#call a command on the remote escrow - intended to be platform independent,
#allow background or foreground execution, redirect to a file on remote server
def remote_escrow_command(command,redirect='',bg=False):
    ssh = config.get("Exepaths","sshpass_exepath")
    ssh_port = config.get("Escrow","escrow_ssh_port")
    login = get_login('buyer') #TODO: should change config structure so we use
                                #this agent's login, not specifically buyer/seller
    debug(1,["Attempting remote command:",command," on host:",login[1]])
    if redirect=='NULL':
        command = command + ' > /dev/null 2>&1'
    elif redirect:
        command = command + ' > ' + redirect
        
    if bg: 
        command = command+' &'
        #in case of foreground execution, we can use the output; if not
        #it doesn't matter
    return subprocess.check_output([ssh,login[0]+'@'+login[1],'-P',ssh_port,\
                                '-pw',login[2],command])
   
#copy all files from remote_dir on the remote (escrow) server to the local_dir
#directory on the local machine
def get_remote_files(remote_dir,local_dir):
    login = get_login('buyer') #todo: should be just agent, not one of buy/sell
    params = [config.get("Exepaths","scp_exepath"), '-P',\
    config.get("Escrow","escrow_ssh_port"),'-pw',login[2],'-unsafe',\
    login[0]+'@'+login[1]+':'+remote_dir+'/*',local_dir+'/.']
    
    print subprocess.check_output(params)

#note: local_command takes input argument command as a LIST
def local_command(command,bg=False,redirect=''):
    debug(1,["Attempting local command:",command])
    
    if redirect=='NULL':
        if OS=='Windows': 
            command.append(' > NUL 2>&1')
        elif OS=='Linux':
            command.append(' > /dev/null 2>&1')
        else:
            debug(0,["OS not recognised, quitting."])
    elif redirect:
        command.extend('>',redirect)
    
    if OS == 'Windows':
        if bg:
            #20 Sep 2013:
            #a hack is needed here. 
            #Additional note: finally fixed this incredibly pernicious bug!
            #for details, see my post at: http://www.reddit.com/r/Python/
            #comments/1mpxus/subprocess_modules_and_double_quotes/ccc4sqr
            subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        else:
            return subprocess.check_output(command)
    elif OS == 'Linux':
        if bg: 
            command = command.append('&')
        #in case of foreground execution, we can use the output; if not
        #it doesn't matter
        return subprocess.check_output(command)
    else:
        debug(0,["OS not recognised, quitting."])
        
#agent must be 'buyer' or 'seller'
#TODO: find a secure way to access logins
def get_login(agent):
    return [config.get(agent.title(),agent+"_ssh_user"),\
config.get("Escrow","escrow_host"),config.get(agent.title(),agent+"_ssh_pass")]
    
    
#platform independent strip and split text string output (e.g. from console)
def pisp(x):
    x=x.rstrip()
    return x.split(PINL)

def silentremove(filename):
    try:
        os.remove(filename)
    except OSError, e: # this would be "except OSError as e:" in python 3.x
        if e.errno != errno.ENOENT: # errno.ENOENT = no such file or directory
            raise # re-raise exception if a different error occured
        
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
#This is the purpose of the remove_in_advance flag.
def verify_file_creation(file,warning,overwrite=False,prompt=True,remove_in_advance=False):
    
    try:
        while True:
            if (os.path.isfile(file)):
                if overwrite:
                    if prompt:
                        answer = raw_input("Warning: " + warning +   \
                                        " Do you want to overwrite file? [Y/N]")
                        if (answer in ['y','Y']):
                            if remove_in_advance: os.remove(file)
                            return file
                        elif (answer not in ['n','N']):
                            print "Unrecognized input. Please enter Y/y/N/n (one character)"
                        else:
                            answer2 = raw_input("Please enter new name for \
                            output file. \n (give filename only, \
                            directory will be the same):")
                            file = os.path.join(os.path.dirname(file),answer2)
                    else: #no prompt: just overwrite
                        if remove_in_advance: os.remove(file)
                        return file
                    
                else: #not overwrite
                    print "You have chosen not to overwrite. Program will quit."
                    exit(1)
                    
            else: #file doesn't exist
                return file              
    except:
        debug(0,["Failed trying to create file: ",file,". Quitting!"])
        exit(1)