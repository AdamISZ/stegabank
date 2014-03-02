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

#TODO use ini file to set executable paths
'''
if shared.OS=='win':
    stcppipe_exepath = os.path.join(ddir,'stcppipe', 'stcppipe.exe')
    tshark_exepath = os.path.join(ddir,'wireshark', 'tshark.exe')
    mergecap_exepath = os.path.join(ddir,'wireshark', 'mergecap.exe')
    plink_exepath = os.path.join(ddir, 'plink.exe')    
if shared.OS=='linux':
    stcppipe_exepath = os.path.join(ddir,'stcppipe', 'stcppipe')
    tshark_exepath = 'tshark'
    mergecap_exepath = 'mergecap'
    
firefox_exepath = 'firefox'
ssh_exepath = 'ssh'
'''
#local port for ssh's port forwarding. Will be randomly chosen upon starting the tunnel
random_ssh_port = 0
#random TCP port on which firefox extension communicates with python backend
FF_to_backend_port = 0
#random port which FF uses as proxy port. Local stcppipe listens on this port and forwards traffic to random_ssh_port
FF_proxy_port = 0

#a thread which returns a value. This is achieved by passing self as the first argument to a called function
#the calling function can then set self.retval
class ThreadWithRetval(threading.Thread):
    def __init__(self, target):
        super(ThreadWithRetval, self).__init__(target=target, args = (self,))
    retval = ''

class StoppableHttpServer (BaseHTTPServer.HTTPServer):
    """http server that reacts to self.stop flag"""
    retval = ''
    def serve_forever (self):
        """Handle one request at a time until stopped. Optionally return a value"""
        self.stop = False
        while not self.stop:
                self.handle_request()
        return self.retval;

#Receive HTTP HEAD requests from FF extension. This is how the extension communicates with python backend.
class buyer_HandlerClass(SimpleHTTPServer.SimpleHTTPRequestHandler, object):
    protocol_version = "HTTP/1.1"      
    global qFrontEnd
        
    def do_HEAD(self):
        global ssh_proc
        global stcppipe_proc
        global is_ssh_session_active                    
                
        if self.path.startswith('/sign_tx'):
            print 'Received signing request'
            raddr,mbal,myid,cpid = urllib2.unquote(self.path.split('?')[1]).split()
            print 'Received a destination address: '+raddr
            print 'Received an owned balance: '+mbal
            print 'Received an owned id: '+myid
            print 'Received a ctrprty id: '+cpid
            sig = multisig.create_sig_for_redemption(myid,myid,cpid,mbal,0.0001,raddr)
            
            self.send_response(200)
            self.send_header("response","sign_tx")
            if (sig):
                self.send_header("result","success")
            else:
                self.send_header("result","failure")
            self.end_headers()
            return
            
        if self.path.startswith('/get_balance'):
            print 'Received a request to get the balance'
            addr = urllib2.unquote(self.path.split('?')[1])
            conf,unconf = multisig.check_balance_at_multisig('x','x',addr=addr)
            print 'got an unconf balance of: '+str(unconf)
            self.send_response(200)
            self.send_header("response","get_balance")
            self.send_header("confirmedbalance",str(conf))
            self.send_header("unconfirmedbalance",str(unconf))
            self.end_headers()
            return
            
        #chat message format going TO oracle: '<uniqueid_recipient> <type> [data..]'
        if self.path.startswith('/send_chat'):
            print 'Received a chat message send request'
            #need everything after the first question mark, including question marks
            chatdata = '?'.join(self.path.split('?')[1:])
            chatdata = urllib2.unquote(chatdata)
            params = chatdata.split()
            if len(params[0]) != 64:
                print 'Error: id of recipient wrong length'
            print 'recipient is: '+params[0]
            print 'type is: '+params[1]
            print 'message is: '+' '.join(params[2:])
            send_chat_to_oracle(params[0],params[1],' '.join(params[2:]))
            print 'Received a chat message and sent to oracle'
            self.send_response(200)
            self.send_header("response","send_chat")
            self.end_headers()
            return
        
        #chat message format coming FROM oracle: '<uniqueid_sender> <type> [data...]' 
        if self.path.startswith('/receive_chat'):
            m=''
            type=''
            value=''
            sender=''
            try:  
                m = q.get_nowait()
                if not m.strip().split():
                    sender = 'none'
                else:
                    sender = m.split()[0]
                    type = m.split()[1]
                    value = ' '.join(m.split()[2:])
            except Queue.Empty:
                pass
            if not m:
                sender='none'
            self.send_response(200)
            self.send_header("response","receive_chat")
            self.send_header("sender",sender)
            self.send_header("type",type)
            self.send_header("value",value)
            self.end_headers()
            return
        
        if self.path.startswith('/start_tunnel'):
            arg_str = self.path.split('?')[1]
            args = arg_str.split(";")
            if ALPHA_TESTING:
                key_name = "alphatest.txt"
            global assigned_port
            assigned_port = args[1]
            retval = start_tunnel(key_name, args[0])
            print 'Sending back: '+retval + assigned_port
            if retval == 'reconnect':
                self.send_response(200)
                self.send_header("response", "start_tunnel")
                #assigned_port now contains the new port which sshd wants us to reconnect to
                self.send_header("value", "reconnect;"+assigned_port)
                self.end_headers()                
            if retval != 'success':
                print 'Error while setting up a tunnel: '+retval
            self.send_response(200)
            self.send_header("response", "start_tunnel")
            self.send_header("value", retval)
            self.end_headers()
            return     
        
        if self.path.startswith('/terminate'):
            if is_ssh_session_active: 
                os.kill(stcppipe_proc.pid, signal.SIGTERM)
                ssh_proc.stdin.write("exit\n")
                ssh_proc.stdin.flush()
                is_ssh_session_active = False              
            self.send_response(200)
            self.send_header("response", "terminate")
            self.send_header("value", "success")
            self.end_headers()
            time.sleep(2)
            return      
            
        if self.path.startswith('/started'):
            global is_ff_started
            is_ff_started = True
            self.send_response(200)
            self.send_header("response", "started")
            self.send_header("value", "success")
            self.end_headers()
            return

#use miniHTTP server to receive commands from Firefox addon and respond to them
def start_minihttp_thread(parentthread):
    global FF_to_backend_port
    print 'Starting mini http server to communicate with Firefox plugin'
    try:
        httpd = StoppableHttpServer(('127.0.0.1', FF_to_backend_port), buyer_HandlerClass)
    except Exception, e:
        print 'Error starting mini http server', e
        exit(1)
    sa = httpd.socket.getsockname()
    print "Serving HTTP on", sa[0], "port", sa[1], "..."
    retval = httpd.serve_forever()
    
#this basically just consists of asking the
#escrow if the counterparty is currently online
def initiateChatWithCtrprty(myself,ctrprty):
    msg = 'QUERY_STATUS:'+ctrprty    
    myself.sendMessage(msg,recipientID='CNE')
    rspns = myself.getSingleMessage(timeout=5)
    for k,v in rspns.iteritems():
        if 'ONLINE' in m:
            return True
    return False

def sendChatToCtrprty(myself,ctrprty,msgToSend,txID=None):
    #tx will be set after contracts signed
    myself.sendMessage('CNE_CHAT:'+msgToSend,recipientID=ctrprty,txID=txID)     

def changeEscrow():
    shared.debug(0,["Current escrow:",g("Escrow","escrow_id")])
    
    #escrowList = zip(*(iter(g("Escrow","escrow_list").split('|')),)*3)
    escrowList = [e.split('|') for e in g("Escrow","escrow_list").split(',')]
    
    for i,e in enumerate(escrowList):
        print "["+str(i+1)+"] "+e[0]    
    c = shared.get_validated_input("Choose an escrow",int)
    if c not in range(1,len(escrowList)+1):
        print "Invalid choice"
    else:
        #rewrite the settings file and reset the escrow
        shared.config.set("Escrow","escrow_id",value=escrowList[c-1][0])
        shared.config.set("Escrow","escrow_pubkey",value=escrowList[c-1][2])
        shared.debug(2,["Set the escrow id to:",g("Escrow","escrow_id")])
        shared.debug(2,["Set the escrow pubkey to:",g("Escrow","escrow_pubkey")])
        
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
    Msg.instantiateConnection()
    
    #FF_to_backend_port = random.randint(1025,65535)
    #FF_proxy_port = random.randint(1025,65535)
    #thread = ThreadWithRetval(target= start_minihttp_thread)
    #thread.daemon = True
    #thread.start()  
    
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
                #TODO
                #sendChatToCtrprty(ctrprty,text)
                
            elif choice == 3:
                exit(0)
                
            elif choice == 4:
                if not ctrprty:
                    print "You have to set the counterparty first!\n"
                    continue
                #TODO
                #sendCtrprtyAliveRequest(ctrprty,myEscrow)
                
            
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
                changeEscrow()
                c = shared.get_binary_user_input("Do you want to use this as RE?",'y','y','n','n')
                RE = True if c == 'y' else False
                continue
                
            else:
                print "invalid choice. Try again."
