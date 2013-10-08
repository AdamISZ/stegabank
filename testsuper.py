#rudimentary super escrow access to read html
#=====LIBRARY IMPORTS===============
import sys
import subprocess
import shutil
import os
import time
import re
import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import helper_startup
import argparse
import itertools
import AppLayer
from AppLayer import Transaction
from AppLayer import Agent
from AppLayer import UserAgent
from AppLayer import EscrowAccessor
import Messaging.MessageWrapper as Msg
from NetworkAudit import sharkutils



if __name__ == "__main__":
    
    if len(sys.argv)>1:
        config_file = sys.argv[1]
    else:
        config_file = 'ssllog.ini'
        
    #Load all necessary configurations:
    helper_startup.loadconfig(config_file)
    
    role='agent'
    #instantiate my instance of UserAgent
    myself = UserAgent(g("Directories",role+"_base_dir"),\
        g(role.title(),"btc_address"),g(role.title(),"bank_information"),\
        g(role.title(),"base_currency"))
    
    #instantiate a blocking connection to the message queue
    try:
        Msg.instantiateConnection(un=g(role.title(),role+"_rabbitmq_user"),\
                              pw=g(role.title(),role+"_rabbitmq_pass"))
    except:
        shared.debug(0,["Failed to instantiate a connection to rabbitmq server",\
                        "- maybe the escrow machine is down? Try pinging it.",\
                        "Quitting."])
        exit(1)
    
    start=True
    with open('super.html','wb') as f:
        while True:
            msg = Msg.getSingleMessage(recipientID='adam111')
            if not msg:
                break
            shared.debug(0,["Super escrow retrieved message:",msg])
            html = msg.values()[0].replace('\n','\r\n')
            
            if start:
                f.write('**Super-escrow evidence file**, for transaction:'+\
                    msg.keys()[0].split('.')[0]+'\r\n\r\n')
                start = False
            
            if 'END_PAGE' in msg.values()[0].split(':')[0]:
                f.write('\r\n\r\n**END OF PAGE**\r\n\r\n')
            else:
                f.write(':'.join(html.split(':')[1:]).encode('utf-8'))
    time.sleep(2)
    f.close
            
    