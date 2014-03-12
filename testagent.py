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
import math
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


#the intention of this module is to provide an 
#*interface* from the client app in the browser
#to the underlying application layer

myself=None

#if on RE, we focus on one transaction at a time
txRE = None    

#a thread which returns a value. This is achieved by passing self as the first argument to a called function
#the calling function can then set self.retval
class ThreadWithRetval(threading.Thread):
    def __init__(self, target):
        super(ThreadWithRetval, self).__init__(target=target, args = (self,))
    retval = ''
    
def sendCtrprtyAliveRequest(myself,ctrprty,prefix='CNE'):
    msg = 'QUERY_STATUS:'+ctrprty    
    myself.sendMessage(msg,recipientID=prefix)
    
    #TODO: this code doesn't work asynchronously, and needs work anyway!
    rspns = myself.getSingleMessage(timeout=5)
    if rspns:
        for k,m in rspns.iteritems():
            if 'QUERY_STATUS_RESPONSE:ONLINE' in m:
                return True
    return False

def sendChatToCtrprty(myself,ctrprty,msgToSend,txID=None):
    #tx will be set after contracts signed
    myself.sendMessage('CNE_CHAT:'+msgToSend,recipientID=ctrprty,txID=txID)     

def getEscrowList():
    return [e.split('|') for e in g("Escrow","escrow_list").split(',')]

def changeEscrow(specific=None):
    shared.debug(0,["Current escrow:",g("Escrow","escrow_id")])
    if specific:
        c = specific
    else:
        for i,e in enumerate(getEscrowList()):
            print "["+str(i+1)+"] "+e[0]    
        c = shared.get_validated_input("Choose an escrow",int)
        
    if c not in range(1,len(escrowList)+1):
        shared.debug(0,["Invalid choice from escrow list"])
    else:
        #rewrite the settings file and reset the escrow
        #TODO: persist changes to config file
        shared.config.set("Escrow","escrow_id",value=escrowList[c-1][0])
        shared.config.set("Escrow","escrow_pubkey",value=escrowList[c-1][2])
        shared.config.set("Escrow","escrow_host",value=escrowList[c-1][1])
        shared.debug(2,["Set the escrow to host:",g("Escrow","escrow_host"),"id:",g("Escrow","escrow_id"),"pubkey:",g("Escrow","escrow_pubkey")])
        
    Msg.closeConnection()
    time.sleep(1)
    Msg.instantiateConnection(un='client1',pw='client1',chanIndex=0)
    
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
    d = os.path.join(g("Directories","agent_base_dir"),"multisig_store")
    p = g("Escrow","escrow_pubkey")
    #initialise multisig
    multisig.initialise(p,d)
    #need a connection to an escrow to do anything
    Msg.instantiateConnection(un='guest', pw='guest')
    
    
    #read in contract details (for early testing only)
    contractDetails = {}
    with open("AppLayer/boilerplate.txt") as fi:
        lines = fi.readlines()
        for line in lines:
            if line.startswith('***'):
                k,v = line[3:].strip().split(':: ')
                contractDetails[k]=v
    
    boilerplateContract = Contract.Contract(contractDetails)
    
    #flag to control which menu to use for contacting which type of escrow
    #TODO: actual connection switching; could still use EscrowAccessor concept?
    RE = False
    
    while True:
        '''
        if (myself):
            print "****WORKING ON IDENTITY: "+myself.uniqID()
            c,u = multisig.get_balance_lspnr(myself.uniqID())
            print "Current balance in this identity: confirmed: "+str(c)+", unconfirmed: "+str(u)
            print "******************************************************"
            try:
                #primitive implementation of display to user
                shared.debug(0,["Earlier, received this from MQ:",myself.qFrontEnd.get_nowait()])
            except:
                #necessary because empty queue raises Exception
                pass
        '''
        try:
            #primitive implementation of display to user
            shared.debug(0,["Earlier, received this from MQ:",myself.qFrontEnd.get_nowait()])
        except:
            #necessary because empty queue raises Exception
            pass        
        if RE:
            print """You are on RE. Please choose an option:
            [1] Show current transactions and choose one 
            [2] Pay mBTC to be transferred into multisig (seller)
            [3] Request banking session (buyer)
            [4] Dispute receipt of funds (seller)
            [5] Confirm receipt of funds (buyer)
            [6] Show transaction details
            [7] Specify ssl keys as proof of transfer (buyer)
            [8] Exit
            """
            
            choice = shared.get_validated_input("Enter an integer:",int)
            
            if choice in [2,3,4,5,6] and txRE is None:
                print "You need to specify a transaction first"
                continue 
            
            if choice==1:
                if not myself.synchronizeTransactions():
                    shared.debug(0,["Error synchronizing transactions"])                              
                tnum = shared.get_validated_input("Choose a transaction:",int)
                print "got ",str(tnum)
                if tnum not in range(0,len(myself.transactions)):
                    shared.debug(0,["Invalid choice"])
                    continue
                txRE = tnum
                print "set txre to",str(txRE)
                
            elif choice == 2:
                if not myself.transactions[txRE].seller == myself.uniqID():
                    shared.debug(0,["Error: this action is to be performed by the seller,"\
                                    ,myself.transactions[txRE].seller])
                    continue
                
                if not myself.transactions[txRE].sellerFundingTransactionHash:
                    amt = int(myself.transactions[txRE].contract.text['mBTC Amount'])\
                        +shared.defaultBtcTxFee
                    payee = myself.transactions[txRE].msigAddr
                    sellerDepositHash = multisig.spendUtxos(myself.uniqID(),myself.uniqID(),\
                                                            payee,None,amt=amt)
                
                    if not sellerDepositHash:
                        shared.debug(0,["Error; insufficient funds in",\
                                        myself.uniqID(),"for the deposit of",\
                                        str(amt),"satoshis."])
                        continue
                    else:
                        shared.debug(0,["Deposit successfully made into transaction:",\
                                        sellerDepositHash])
                        myself.transactions[txRE].sellerFundingTransactionHash=\
                            sellerDepositHash
                
                else:
                    sellerDepositHash = myself.transactions[txRE].sellerFundingTransactionHash
                    
                #message the RE to inform of payment
                myself.sendMessage("RE_SELLER_DEPOSIT:"+sellerDepositHash,recipientID='RE',\
                                   txID=myself.transactions[txRE].uniqID())
                
            elif choice==3:
                if not myself.getTxByIndex(txRE).getRole(myself.uniqID())=='buyer':
                    shared.debug(0,["Error, only the buyer can start banking"])
                    continue
                
                if not myself.synchronizeTransactions():
                                    shared.debug(0,["Error synchronizing transactions"])                
                
                myself.sendMessage("RE_BANK_SESSION_START_REQUEST:",recipientID='RE',\
                                   txID=myself.transactions[txRE].uniqID())
                #wait for bank session start accceptance message, 
                #handled by processInboundMessages, and block 
                while True:
                    #wait for response; we don't expect a long wait as it's a low
                    #intensity workload for escrow
                    msg=None
                    try:
                        msg = myself.qFrontEnd.get_nowait()
                    except:
                        pass #in case queue is empty
                    
                    shared.debug(4,["Got",msg])
                    if not msg:
                        #we stay here since we insist on getting a response.
                        time.sleep(1)
                        shared.debug(4,["Waiting for escrow response.."])
                        #TODO need some failure mode here
                        continue                
                    
                    hdr,data = msg.values()[0].split(':')[0],':'.join(msg.values()[0].split(':')[1:])
                    shared.debug(4,["Got this message:",hdr,data])
                    
                    if hdr == 'RE_BANK_SESSION_START_REJECTED':
                        shared.debug(0,["Seller is not available, cannot proceed"])
                        break
                    elif hdr != 'RE_BANK_SESSION_START_ACCEPTED':
                        shared.debug(0,["The message server sent a wrong message in the"\
                                                    "stream of transaction data."])
                        break
                    else:
                        rspns = myself.startBankingSession(myself.getTxByIndex(txRE))
                        myself.endBankingSession(myself.getTxByIndex(txRE), rspns)
                        break
                        
            elif choice==4:
                shared.debug(0,["You have chosen to dispute the sending of fiat money."])
                if myself.getTxByIndex(txRE).getRole(myself.uniqID()) not in ['seller','buyer']:
                    shared.debug(0,["Error, you cannot dispute fiat sending unless you are the seller or buyer!"])
                
                else:
                    reasonForDispute=shared.get_validated_input(\
                        "Please enter a brief description of the reason for the dispute:",str)                    
                    sig = myself.makeRedemptionSignature(myself.getTxByIndex(txRE),\
                                                         toCounterparty=False)
                    if sig:
                        myself.sendMessage("RE_DISPUTE_REQUEST:"+reasonForDispute+'|'+sig,\
                                           recipientID='RE',txID=myself.getTxByIndex(txRE).uniqID())
                    else:
                        shared.debug(0,["Sorry, there was an error in the construction\
                        of the redeeming payment signature, cannot proceed. You may \
                        have to wait longer for the initial deposit into the multisig\
                        to confirm."])
                continue
                
            elif choice==5:
                if myself.getTxByIndex(txRE).getRole(myself.uniqID()) != 'seller':
                    shared.debug(0,["Error, you cannot acknowledge receipt of fiat unless you are the seller!"])
                else:
                    #construct the signature to redeem the bitcoin escrow
                    #to the buyer
                    sig = myself.makeRedemptionSignature(myself.getTxByIndex(txRE))
                    if sig:
                        myself.sendMessage("RE_FIAT_RECEIPT_ACKNOWLEDGE:"+sig,\
                                   recipientID='RE',txID=myself.getTxByIndex(txRE).uniqID())
                    else:
                        shared.debug(0,["Sorry, cannot make the payment, probably\
                         because the initial deposit is not yet confirmed. Please\
                          try again later."])
                continue
            
            elif choice==6:
                print myself.getTxByIndex(txRE).contract.getContractDetails()
                print "signature completed on:"
                print myself.getTxByIndex(txRE).signatureCompletionTime
            
            elif choice==7:
                myself.chooseSSLKeys(myself.getTxByIndex(txRE))
                
            elif choice==8:
                exit()
                
        else:    
            print """Please choose an option:
            [1] Send signed contract to counterparty
            [2] Send chat message
            [3] Exit
            [4] Check if counterparty is online
            [5] Pay deposit and fee
            [6] View/set active escrow
            [7] Show available pending contracts
            [8] Create or choose id
            [9] Modify and set the working contract
            [10] Purge old messages
            [11] Switch escrow
            [12] Application for escrow status
            """
            choice = shared.get_validated_input("Enter an integer:",int)
            if choice in [1,2,4,5,6,7,9,10,11] and not myself:
                print "You need to set an identity first."
                continue
            
            if choice==1:
                if not myself.signContractCNE():
                    print "something went wrong signing"
                if not myself.sendSignedContractToCtrprtyCNE():
                    print "you attempted to send an unsigned contract"
            elif choice == 2:
                text = shared.get_validated_input("Enter chat message:",str)
                #default is counterparty in current contract
                c = shared.get_validated_input("Enter counterparty (BTC Address), or 0 for \
                default counterparty i.e. specified in contract",str)
                if c=='0':
                    ctrprty1 =myself.workingContract.text['Buyer BTC Address']
                    ctrprty2 = myself.workingContract.text['Seller BTC Address']
                    ctrprty = ctrprty1 if ctrprty2==myBtcAddress else ctrprty2
                else:
                    ctrprty = c
                sendChatToCtrprty(myself,ctrprty,text)
                
            elif choice == 3:
                exit(0)
                
            elif choice == 4:
                #default is counterparty in current contract
                c = shared.get_validated_input("Enter counterparty (BTC Address), or 0 for \
                default counterparty i.e. specified in contract",str)
                if c=='0':
                    ctrprty1 = myself.workingContract.text['Buyer BTC Address']
                    ctrprty2 = myself.workingContract.text['Seller BTC Address']
                    ctrprty = ctrprty1 if ctrprty2==myBtcAddress else ctrprty2
                else:
                    ctrprty = c
                answer = sendCtrprtyAliveRequest(myself,ctrprty)
                shared.debug(0,["Escrow reports that",ctrprty,"-s online status is:",answer])
                
            
            elif choice == 5:
                c = shared.get_binary_user_input('You have chosen to pay fees from '\
                                +myself.uniqID()+' : are you sure?','y','y','n','n')
                if c == 'y':
                    txhash = myself.payInitialFees()
                    if not txhash:
                        shared.debug(0,\
                    ["Error, failed to pay the fees. The account probably isn't funded."])
                    else:
                        shared.debug(0,["Successfully paid into tx: ",txhash])
                continue
                    
            elif choice==6:
                print "Current contract hash:\n",myself.workingContract.textHash
                print "Current contract details:\n",myself.workingContract.getContractText()
                print "Current contract signatures:\n",myself.workingContract.signatures
                
            elif choice==7:
                if not myself.pendingContracts:
                    print "No contracts are currently proposed."
                    continue
                else:
                    myself.printPendingContracts()
                    
                    
            elif choice==8:
                
                #TODO not needed now; will need a rework when really switching
                #if receiverThread:
                #    myself.inboundMessagingExit=True
                
                listIds = [f for f in os.listdir(multisig.msd) if os.path.isfile(os.path.join(multisig.msd,f)) and f.endswith('.private')]
                dictIds = {}
                for i,fname in enumerate(listIds):
                    #if not fname.endswith('.private'):
                        #continue
                    print "["+str(i+1)+"] "+fname[:-8]
                    dictIds[i+1]=fname[:-8]
                c = shared.get_validated_input("Choose an identity or 0 for a new one",int)
                if c==0:
                    addr,pub,priv = multisig.create_tmp_address_and_store_keypair()
                    myBtcAddress=addr                
                elif c in dictIds.keys():
                    myBtcAddress=dictIds[c]
                else:
                    print "invalid choice"
                
                #create or override the master "useragent object"
                myself = UserAgent(basedir=g("Directories","agent_base_dir"),\
                                   btcaddress=myBtcAddress,\
                                   bankinfo="stuff",currency=g("Agent","base_currency"))                    
                myself.workingContract = Contract.Contract(contractDetails)
                
                #for responding to messages from the escrow MQ server
                receiverThread = ThreadWithRetval(target= myself.processInboundMessages)
                receiverThread.daemon = True
                receiverThread.start()                  
                
            elif choice==9:
                #for manually upgrading the working contract
                myself.editWorkingContract()
                
            elif choice==10:
                Msg.purgeMQ(myself.uniqID())
            
            elif choice==11:
                #TODO: code to deal with connection switch
                myself.sendMessage('SELF_SHUTDOWN:', recipientID=myBtcAddress)
                time.sleep(5)
                changeEscrow()
                time.sleep(5)
                c = shared.get_binary_user_input("Do you want to use this as RE?",'y','y','n','n')
                RE = True if c == 'y' else False
                
                #for responding to messages from the escrow MQ server
                receiverThread = ThreadWithRetval(target= myself.processInboundMessages)
                receiverThread.daemon = True
                receiverThread.start()
                
                continue
            
            elif choice==12:
                #request to be adjudicator requires identity info
                identityInfo = shared.get_validated_input("Enter identity info",str)
                #construct list of pubkeys
                escrowList = getEscrowList()
                pubkeyList=[x[2] for x in escrowList]
                mypub,mypriv = multisig.getKeysFromUniqueID(myself.uniqID())
                pubkeyList.append(mypub)
                
                #majority M of N total:
                N = len(pubkeyList)
                if N>17:
                    shared.debug(0,["Critical error: the total number of keys in this multisig address exceeds the maximum of 17 - aborting"])
                    break
                
                M = math.floor(N/2)+1
                msigaddr,mscript = multisig.createMultisigRaw(M, N, pubkeyList)
                
                shared.debug(0,["You have created this multisig address:",msigaddr])
                shared.debug(0,["Please wait while your request is sent out to the pool."])
                #broadcast
                #TODO this is slow but ..?
                for i,e in enumerate(escrowList):
                    
                    shared.config.set("Escrow","escrow_id",value=escrowList[i][0])
                    shared.config.set("Escrow","escrow_pubkey",value=escrowList[i][2])
                    shared.config.set("Escrow","escrow_host",value=escrowList[i][1])
                    shared.debug(2,["Set the escrow to host:",g("Escrow","escrow_host"),"id:",g("Escrow","escrow_id"),"pubkey:",g("Escrow","escrow_pubkey")])                    
                    
                    Msg.closeConnection()
                    time.sleep(1)
                    
                    Msg.instantiateConnection()
                    
                    myself.sendMessage('ADJUDICATOR_APPLICATION:'+','.join(msigaddr,mypub))
                shared.debug(0,["Your application has been sent to all pool members. Please wait for their response."])
                
                    
            else:
                print "invalid choice. Try again."
