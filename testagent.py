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

if __name__ == "__main__":
    #Load all necessary configurations:
    #========================
    helper_startup.loadconfig()
    
    parser = argparse.ArgumentParser(description='ssllog user agent script')
    parser.add_argument('role',help="role, either \'buyer\' or \'seller\'")
    args = parser.parse_args()
    role = args.role.lower()
    if role not in ['buyer','seller']:
        shared.debug(0,["invalid role string provided, quitting."])
        exit(1)
        
    #In the next section we instantiate the agents which are going to take
    #part in the test.
    
    other = 'seller' if role == 'buyer' else 'buyer'
    #instantiate a blocking connection to the message queue
    Msg.instantiateConnection(un=g(role.title(),role+"_rabbitmq_user"),\
                              pw=g(role.title(),role+"_rabbitmq_pass"))
    
    #instantiate two instances of UserAgent
    myself = UserAgent(g("Directories",role+"_base_dir"),\
        g(role.title(),"btc_address"),g(role.title(),"bank_information"),\
        g(role.title(),"base_currency"))
 
    counterparty = UserAgent(g("Directories",other+"_base_dir"),\
        g(other.title(),"btc_address"),g(other.title(),"bank_information"),\
        g(other.title(),"base_currency"))
    
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
        role = shared.get_binary_user_input("Do you want to buy or sell? [B/S]",\
                                            'b','buyer','s','seller')
        amount = shared.get_validated_input("Enter amount to trade: ",float)
        price = shared.get_validated_input("Enter worst acceptable price in "+\
                                        myself.baseCurrency+" per BTC: ",float)
    
    except:
        shared.debug(0,["Error in command line agent execution. Quitting!"])
        exit(1)

    buyer = myself if role=='buyer' else counterparty
    seller = counterparty if role=='buyer' else myself
    
    #having collected enough info, we're ready to request a transaction:
    myself.activeEscrow.requestTransaction(buyer=buyer,seller=seller, \
                    amount=amount,price=price,curr=myself.baseCurrency)
    
    #make a temporary transaction object with our data to cross check 
    #with escrow response
    tx = Transaction(buyer.uniqID(),seller.uniqID(),amount,price,buyer.baseCurrency)
    
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
            exit(0)
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
            exit(0)
    
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
        
        #TODOput some code to get the confirmation of storage from escrow
        #(and counterparty?) so as to be sure everything was done right
    else:
        shared.debug(0,["Waiting for signal of end of banking session."])
        
        #wait for escrow message telling us the buyer's finished
        if not myself.activeEscrow.waitForBankingSessionEnd(tx): exit(1)
        shared.debug(0,["The banking session is finished. Exiting."])
        exit(0)















