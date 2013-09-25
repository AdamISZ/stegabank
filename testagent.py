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
from NetworkAudit import sharkutils
import Messaging
#=====END LIBRARY IMPORTS==========


#basic functional testing of application layer
#t = Transaction(Agent(),Agent(),'100','101')
#check functioning of __repr__ (will be used for messaging)
#print t

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
        role = shared.get_binary_user_input("Do you want to buy or sell? [B/S]",'b','buyer','s','seller')
        amount = shared.get_validated_input("Enter amount to trade: ",float)
        price = shared.get_validated_input("Enter worst acceptable price in "+myself.baseCurrency+" per BTC: ",float)
    
    except:
        shared.debug(0,["Error in command line agent execution. Quitting!"])
        exit(1)

    buyer = myself if role=='buyer' else counterparty
    seller = counterparty if role=='buyer' else myself
    #having collected enough info, we're ready to request a transaction:
    tx =myself.activeEscrow.requestTransaction(buyer=buyer,seller=seller, amount=amount,price=price)
    
    #the next step (for both parties) is to wait for confirmation from the remote escrow
    #that the transaction has been accepted as valid
    if not escrow.getResponseToTxnRq(tx):
        shared.debug(0,["Timed out waiting for a response from the escrow."])
        exit(1)
    
    #at this stage the escrow and counterparty have confirmed that the
    #transaction is valid.
    shared.debug(1,["Transaction has been set to: ",tx])
    
    rspns = shared.get_binary_user_input("Press Y/y to start banking session",\
                                        'y','y','n','n')
    if rspns != 'y':
        shared.debug(0,["You chose not to do the banking session. Please note"\
        ,"that your transaction is still held on the escrow in an",\
        "\'initialised\', i.e. pending, state. You can continue at another",\
        "time. The application will now quit."])
        exit(0)
        
    myself.startBankingSession(tx)
    if role=='buyer':
        print "Waiting for you to finish and quit Firefox..."
        #something to account for the case where the proxy didn't work?
        shared.wait_for_process_death('firefox')
        #put some code to get the confirmation of storage from escrow
        #(and counterparty?) so as to be sure everything was done right
    else:
        dummy = raw_input("Waiting for signal of end of banking session.")
    















