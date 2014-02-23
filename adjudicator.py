#=====LIBRARY IMPORTS===============
import sys
import random
import pickle
import subprocess
import shutil
import os
import time
import re
import shared
import threading
import json
import Queue
import BaseHTTPServer
import SimpleHTTPServer
from multisig_lspnr import multisig

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
from AppLayer import Contract
import Messaging.MessageWrapper as Msg
from NetworkAudit import sharkutils
import Messaging
#=====END LIBRARY IMPORTS==========

if __name__ == "__main__":
    #first connect to CNE
    #code for reading order books and choosing escrow here?
    myBtcAddress=None
    myself = None
    receiverThread=None
    #Load all necessary configurations:
    helper_startup.loadconfig(sys.argv[1])    
    global txRE
    myEscrow = g("Escrow","escrow_id")
    myself = g("Escrow","super_id")
    d = os.path.join(g("Directories","escrow_base_dir"),"multisig_store")
    #p = g("Escrow","escrow_pubkey")
    #initialise multisig
    #multisig.initialise(p,d)
    #need a connection to an escrow to do anything
    Msg.instantiateConnection()
    adjudicator = Agent(d,myself)
    while True:
        print """Please choose an option:
        [1] Read message from queue
        [2] Choose transaction
        [3] Adjudicate transaction
        [4] Exit
        
        """
        choice = shared.get_validated_input("Enter an integer:",int)
        
        
        if choice==1:
            msg = adjudicator.getSingleMessage()
            print msg
            
        elif choice==2:
            print "todo"
        elif choice==3:
            print "todo"
            
        elif choice == 4:
            exit(0)
            
        