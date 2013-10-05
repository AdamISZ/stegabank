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
    
    other = 'buyer' if role == 'seller' else 'seller'
    
    counterparty = UserAgent(g("Directories",other+"_base_dir"),\
        g(other.title(),"btc_address"),g(other.title(),"bank_information"),\
        g(other.title(),"base_currency"))
    
    buyer = myself if role=='buyer' else counterparty
    seller = counterparty if role=='buyer' else myself
    
    #the next stage - instantiate a transaction based on user input
    #when bitcoin code is ready, it will slot in here somewhere
    #use the command line to drive; ask the user what they want to do: buy/sell
    #and how much
    try:
        
        amount = shared.get_validated_input("Enter amount to trade: ",float)
        price = shared.get_validated_input("Enter worst acceptable price in "+\
                                        myself.baseCurrency+" per BTC: ",float)
    
    except:
        shared.debug(0,["Error in command line agent execution. Quitting!"])
        exit(1)
    
    #make a temporary transaction object with our data to cross check 
    #with escrow response
    tx = Transaction(buyer.uniqID(),seller.uniqID(),amount,price,buyer.baseCurrency)
    #having collected enough info, we're ready to request a transaction:
    myself.activeEscrow.requestTransaction(buyer=buyer,seller=seller, \
                    amount=amount,price=price,curr=myself.baseCurrency)
    #the next step (for both parties) is to wait for confirmation from the remote escrow
    #that the transaction has been accepted as valid
    if not myself.activeEscrow.getResponseToTxnRq(tx):
        shared.debug(0,["Received no intelligible response from escrow.Quitting."])
        exit(1)
    
    #at this stage the escrow and counterparty have confirmed that the
    #transaction represented by 'tx' is valid.
    
    shared.debug(1,["Transaction has been set to: ",tx.uniqID()])
    
    myself.doBankingSession(tx)
    

def do_dispute(myself,role,escrow):
    
    myself.printCurrentTransactions()
    tnum = shared.get_validated_input("Choose a transaction to dispute:",int)
    tx = myself.transactions[tnum]
        
    #a hack for testing
    rspns =shared.get_binary_user_input("Are you the disputer?",'y','y','n','n')
    
    if rspns=='y':
        shared.debug(0,["Sending dispute request"])
        escrow.sendInitiateL1DisputeRequest(tx)

    #wait for escrow to ask for the data
    escrow.waitForSSLDataRequest(tx)
    
    #send the ssl data - we use the 'on the fly' method of formatting the message
    #noting that the escrow accessor can reset the message key correctly
    #based on the transaction passed, and always sends to the escrow by default
    my_ssl_data = ','.join(myself.getHashList(tx))
    if role == 'buyer':
        #need to send the magic hashes telling the escrow which other hashes
        #to ignore in the comparison
        my_ssl_data += '^'+','.join(myself.getMagicHashList(tx))
    escrow.sendMessages(messages={'x':'SSL_DATA_SEND:'+my_ssl_data},transaction=tx)
    
    #wait for the escrow to respond with adjudication
    adjudication = escrow.getL1Adjudication(tx)

    shared.debug(0,["The result of adjudication was:\n The bitcoins were",\
    "awarded to:",adjudication[0],"for this reason:",adjudication[1]])
    time.sleep(4)
    exit(0)

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
    
    #Load all necessary configurations:
    helper_startup.loadconfig()
    
    #TODO: get rid of this, it's nonsense..
    role = shared.get_binary_user_input("Do you want to buy or sell? [B/S]",\
                                            'b','buyer','s','seller')
    
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
        [2] Start a new transaction
        [3] Dispute an existing transaction
        [4] Act on existing unresolved transactions
        [5] Exit
        """)
        choice = shared.get_validated_input("Enter an integer:",int)
        if choice==1:
            myself.printCurrentTransactions()
        elif choice == 2:
            do_transaction(myself,role,escrow)
        elif choice == 3:
            do_dispute(myself,role,escrow)
        elif choice == 4:
            do_actions_menu(myself,role,escrow,actionables)
        elif choice == 5:
            exit(0)
        else:
            print "invalid choice. Try again."


