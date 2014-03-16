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
from AppLayer import AdjudicatorAgent
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
    d = os.path.join(g("Directories","escrow_base_dir"),"multisig_store")
    #p = g("Escrow","escrow_pubkey")
    #initialise multisig
    #multisig.initialise(p,d) #TODO remove this "initialize" thing
    multisig.msd=d
    #need a connection to an escrow to do anything
    Msg.instantiateConnection()
    adjudicator = AdjudicatorAgent(d,myEscrow,txStore=False)
    while True:
        print """Please choose an option:
        [1] Read message from queue
        [2] Choose transaction
        [3] Adjudicate transaction
        [4] Review adjudicator applications
        [5] Exit
        
        """
        choice = shared.get_validated_input("Enter an integer:",int)
        
        
        if choice==1:
            msg = adjudicator.getSingleMessage(prefix='ADJ')
            print msg
            
        elif choice==2:
            print "todo"
        elif choice==3:
            print "todo"
        
        elif choice==4:
            with open(g("Escrow","adjudicator_store")) as f:
                lines = f.readlines()
            applications = [x for x in lines if 'ADJUDICATOR_APPLICATION' in x]
            print '''
            ======================================================
            Choose from one of the following applications by index
            number, or enter 0 (zero) to abort
            ======================================================
            '''
            for i,app in enumerate(applications):
                print '['+str(i+1)+']: '+app
            c = shared.get_validated_input("Enter choice:",int)
            if c<0:
                shared.debug(0,["Invalid choice"])
            if c>0:
                c=shared.get_binary_user_input("Do you accept the application?",'y','y','n','n')
                accepted = True if c=='y' else False
                reason = shared.get_validated_input("Enter a comment or reason:",str)
                adjudicator.acceptAdjudicatorApplication(app,reason,accepted)
            
                
        elif choice == 5:
            exit(0)
            
        