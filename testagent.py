#the purpose of this testing script will be to function something like
#a prototype.
#we will incorporate testing data (test ports, hosts, addresses) into
#the application layer model.
#Run some initial functional testing.
#Test the network setup and shut down.
#Test a banking session.
#Test an audit.
#
#THIS script will be run with a command prompt so user can request
#buy/sell. Two instances will run simultaneously.
#The other script, testescrow.py, will be responsible for instantiating a
#transaction and propagating it here and to the other agent.
#Then this script will instantiate a banking session and the other instance 
# will request an audit.
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
import Messaging
#=====END LIBRARY IMPORTS==========

def do_transaction(myself, role, escrow):
    
    #Instantiate a transaction based on user input
    try:
        role = shared.get_binary_user_input("Do you want to buy(B) or sell(S)?: "\
                                            ,'b','buyer','s','seller')
        ctrprty = shared.get_validated_input("Enter the bitcoin address of "+\
                                             "your counterparty: ",str)
        amount = shared.get_validated_input("Enter amount to trade: ",float)
        price = shared.get_validated_input("Enter worst acceptable price in "+\
                                        myself.baseCurrency+" per BTC: ",float)
    
    except:
        shared.debug(0,["Error in command line agent execution. Quitting!"])
        exit(1)
        
    #TODO: don't need to enter bank info,base dir or currency info here
    counterparty = UserAgent(g("Directories","agent_base_dir"),\
        ctrprty,g("Agent","bank_information"),\
        g("Agent","base_currency"))
    buyer = myself if role=='buyer' else counterparty
    seller = myself if role=='seller' else counterparty
    
    #make a temporary transaction object with our data to cross check 
    #with escrow response
    tx = Transaction(buyer.uniqID(),seller.uniqID(),amount,price,buyer.baseCurrency)
    #having collected enough info, we're ready to request a transaction:
    myself.activeEscrow.requestTransaction(buyer=buyer,seller=seller, \
                    amount=amount,price=price,curr=myself.baseCurrency)
    #it is not NECESSARY for the counterparties to synchronize at this point;
    #their request has been stored and the match of two requests can occur
    #later. However, the intended approach is for buyer and seller to 
    #do this part at the same time. So we wait for escrow response, understanding
    #that the user may simply quit out at any time.
    if not myself.activeEscrow.getResponseToTxnRq(tx):
        shared.debug(0,["Attempt failed.Quitting."])
        exit(1)
    
    #at this stage the escrow and counterparty have confirmed that the
    #transaction represented by 'tx' is valid. It has been updated by reference.
    shared.debug(1,["Transaction has been set to: ",tx.uniqID()])
    
    myself.doBankingSession(tx)
    

def do_dispute(myself,role,escrow):
    myself.printCurrentTransactions()
    tnum = shared.get_validated_input("Choose a transaction to dispute:",int)
    tx = myself.transactions[tnum]
        
    escrow.sendInitiateL1DisputeRequest(tx)

    #wait for escrow to ask for the data
    escrow.waitForSSLDataRequest(tx)
    
    my_ssl_data = ','.join(myself.getHashList(tx))
    if role == 'buyer':
        #need to send the magic hashes telling the escrow which other hashes
        #to ignore in the comparison
        my_ssl_data += '^'+','.join(myself.getMagicHashList(tx))
    
    #'x' is a dummy, we use default sending signature (TODO clean that up)    
    escrow.sendMessages(messages={'x':'SSL_DATA_SEND:'+my_ssl_data},\
                        transaction=tx,rs=703)
        
def do_actions_menu(myself,role,escrow,actionables):
    while True:
        print "Current actions to be taken:"
        for i,action in enumerate(actionables.items()):
            print "["+str(i+1)+"] - Transaction: "+action[0][0:4]+"..."+"  "+action[1]
            
        choice = shared.get_validated_input("Enter an integer, or 0 to \
                                            go back to main menu:",int)
        if choice ==0:
            return
        #Here we don't decide on the actual action to perform, rather just
        #let the UserAgent object figure out which action it needs to perform
        #based on the transaction that was chosen to address.
        myself.takeAppropriateActions(actionables.items()[choice-1][0])
            
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
    #TODO ssl connections with credentials (or similar)
    try:
        Msg.instantiateConnection(un=g(role.title(),role+"_rabbitmq_user"),\
                              pw=g(role.title(),role+"_rabbitmq_pass"))
    except:
        shared.debug(0,["Failed to instantiate a connection to rabbitmq server",\
                        "- maybe the escrow machine is down? Try pinging it.",\
                        "Quitting."])
        exit(1)
    
    #need to access escrow immediately to get an up to date list of transactions
    escrow = EscrowAccessor(host=g("Escrow","escrow_host"),agent=myself,\
    username=g(role.title(),"escrow_ssh_user"),\
    password=g(role.title(),"escrow_ssh_pass"),\
        port=g(role.title(),"escrow_input_port"),escrowID='123') 
    
    #activate the locally instantiated EscrowAccessor object
    myself.addEscrow(escrow).setActiveEscrow(escrow)
    
    #collect messages with issues to be resolved
    actionables = myself.processExistingTransactions()
    #start with a menu
    
    while True:
        print ("""Please choose an option:
        [1] List current transactions
        [2] Start a new transaction and do internet banking
        [3] Dispute an existing transaction and send your ssl records
        [4] List existing unresolved transactions
        [5] Exit
        """)
        choice = shared.get_validated_input("Enter an integer:",int)
        if choice==1:
            myself.activeEscrow.synchronizeTransactions()
        elif choice == 2:
            do_transaction(myself,role,escrow)
        elif choice == 3:
            do_dispute(myself,role,escrow)
        elif choice == 4:
            #collect issues to be actioned for each transaction
            actionables = myself.processExistingTransactions()
            do_actions_menu(myself,role,escrow,actionables)
        elif choice == 5:
            exit(0)
        else:
            print "invalid choice. Try again."


