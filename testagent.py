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

def do_transaction(myself, role):
    
    other = 'buyer' if role == 'seller' else 'seller'
    
    counterparty = UserAgent(g("Directories",other+"_base_dir"),\
        g(other.title(),"btc_address"),g(other.title(),"bank_information"),\
        g(other.title(),"base_currency"))
    
    buyer = myself if role=='buyer' else counterparty
    seller = counterparty if role=='buyer' else myself
    
    #initialize a fixed escrow -this is for testing; in prod
    #we need ability to dynamically use different escrows
    #the escrow ID is how we look up escrows 
    escrow = EscrowAccessor(host=g("Escrow","escrow_host"),agent=myself,\
    username=g(role.title(),"escrow_ssh_user"),\
    password=g(role.title(),"escrow_ssh_pass"),\
        port=g(role.title(),"escrow_input_port"),escrowID='123') 
        
    #activate the locally instantiated EscrowAccessor object
    myself.addEscrow(escrow).setActiveEscrow(escrow)
    
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
    
    if role=='buyer':
        myself.activeEscrow.requestBankSessionStart(tx)
    
    #wait for response - same for both parties at least in this script.
    if not myself.activeEscrow.getResponseToBankSessionStartRequest(tx):
        shared.debug(0,["Timed out waiting for banking session to be started."])
        exit(1)

    if role=='seller':
        rspns = shared.get_binary_user_input(\
    "Enter Y/y after you have started the proxy server (squid) on your local machine:",\
        'y','y','n','n')
        if rspns != 'y':
            shared.debug(0,["You have rejected the banking session. "+\
                            "Abort instruction will be sent."])
            myself.escrow.sendBankingSessionAbortInstruction(tx)
            rspns = shared.get_binary_user_input("Do you want to abort the "+\
"transaction entirely? If Y/y, the record of the transaction will be erased on"+\
"the remote escrow. If N/n, the transaction will remain in an initialised "+\
"state, waiting for you to conduct the banking session later.",'y','y','n','n')
            if rspns=='y':
                myself.escrow.sendTransactionAbortInstruction(tx)
            
    else:        
        rspns = shared.get_binary_user_input("Enter Y/y to start banking session",\
                                        'y','y','n','n')
        if rspns != 'y':
            myself.escrow.sendBankingSessionAbortInstruction(tx)
            rspns = shared.get_binary_user_input("Do you want to abort the "+\
"transaction entirely? If Y/y, the record of the transaction will be erased on"+\
"the remote escrow. If N/n, the transaction will remain in an initialised "+\
"state, waiting for you to conduct the banking session later.",'y','y','n','n')
            if rspns=='y':
                myself.escrow.sendTransactionAbortInstruction(tx)
            
    
    #if we reached here as seller it means we promise that squid is running.
    #if we reached here as buyer it means we promise to be ready to start banking.
    
    #here we set up the pipes for the internet traffic, as long as everything
    #is in order
    if not myself.startBankingSession(tx): 
            shared.debug(0,["Could not start banking session for transaction",\
                tx.uniqID(),"because this transaction does not belong to you."])
            exit(1)
    
    if role=='buyer':
            
        print "When firefox starts, please perform internet banking." +\
            "\n When you have finished, please close firefox."
        time.sleep(5)
        #start up firefox here TODO
        ffdir = os.path.dirname(g("Exepaths","firefox_exepath"))
        ffname = os.path.basename(g("Exepaths","firefox_exepath"))
        shared.local_command([g("Exepaths","firefox_exepath")],bg=True)
        
        #TODO: need to set things using a plugin
        #TODO: insert test session; escrow can check if it can 
        #receive valid SSL using a test case
        #something to account for the case where the proxy didn't work?
        #TODO: this will need some serious 'refactoring'!
        shared.wait_for_process_death(ffname)
        
        #we have finished our banking session. We need to tell the others.
        myself.activeEscrow.sendConfirmationBankingSessionEnded(tx)
        #if we shut down python immediately the connection is dropped 
        #and the message gets dropped! Ouch, what a bug!TODO
        time.sleep(10)
        #TODOput some code to get the confirmation of storage from escrow
        #(and counterparty?) so as to be sure everything was done right
    else:
        shared.debug(0,["Waiting for signal of end of banking session."])
        
        #wait for message telling us the buyer's finished
        if not myself.activeEscrow.waitForBankingSessionEnd(tx): exit(1)
        shared.debug(0,["The banking session is finished. Exiting."])
    
    #final cleanup - for now only storing the premaster keys
    myself.endBankingSession(tx)

def do_dispute(myself,role):
    
    escrow = EscrowAccessor(host=g("Escrow","escrow_host"),agent=myself,\
    username=g(role.title(),"escrow_ssh_user"),\
    password=g(role.title(),"escrow_ssh_pass"),\
        port=g(role.title(),"escrow_input_port"),escrowID='123') 
        
    #activate the locally instantiated EscrowAccessor object
    myself.addEscrow(escrow).setActiveEscrow(escrow)
    
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

if __name__ == "__main__":
    #Load all necessary configurations:
    #========================
    helper_startup.loadconfig()
    role = shared.get_binary_user_input("Do you want to buy or sell? [B/S]",\
                                            'b','buyer','s','seller')
    
    #instantiate two instances of UserAgent
    myself = UserAgent(g("Directories",role+"_base_dir"),\
        g(role.title(),"btc_address"),g(role.title(),"bank_information"),\
        g(role.title(),"base_currency"))
    
    #instantiate a blocking connection to the message queue
    try:
        Msg.instantiateConnection(un=g(role.title(),role+"_rabbitmq_user"),\
                              pw=g(role.title(),role+"_rabbitmq_pass"))
    except:
        shared.debug(0,["Failed to instantiate a connection to rabbitmq."\
                        "Quitting"])
        exit(1)
    
    #start with a menu
    while True:
        print ("""Please choose an option:
        [1] List current transactions
        [2] Start a new transaction
        [3] Dispute an existing transaction
        [4] Exit
        """)
        choice = shared.get_validated_input("Enter an integer:",int)
        if choice==1:
            myself.printCurrentTransactions()
        elif choice == 2:
            do_transaction(myself,role)
        elif choice == 3:
            do_dispute(myself,role)
        elif choice == 4:
            exit(0)
        else:
            print "invalid choice. Try again."


