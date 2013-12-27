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

#set of contracts proposed by *possible* counterparties
pendingContracts = {}

#the contract we're currently working on
workingContract = None

#control thread access to the the contract list
contractLock = threading.Lock()

#temporary storage queue for messages
#passed from back-end to front-end
qFrontEnd = Queue.Queue()
myBtcAddress = None

ddir = None

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
def initiateChatWithCtrprty(ctrprty):
    msg = {'0.'+myBtcAddress:'QUERY_STATUS:'+ctrprty}    
    Msg.sendMessages(msg,escrow)
    rspns = Msg.getSingleMessage(myBtcAddress,timeout=5)
    for k,v in rspns.iteritems():
        if 'ONLINE' in m:
            return True
    return False

def sendChatToCtrprty(ctrprty,msgToSend,tx=None):
    #tx will be set after contracts signed
    if not tx:
        tx='0'
    msg = {tx+'.'+myBtcAddress:'CNE_CHAT:'+msgToSend}
    Msg.sendMessages(msg,ctrprty)

def sendCtrprtyAliveRequest(ctrprty,escrow):
    msg = {'0.'+myBtcAddress:'QUERY_STATUS:'+ctrprty}
    Msg.sendMessages(msg,escrow)

#'contractDetails' will be a dict
#passed in from the client interface
#a False return indicates you tried to sign a contract
#which didn't match the one sent by your counterparty
def signContractCNE():
    
    global workingContract
    
    if not workingContract:
        shared.debug(0,["Error: contract not defined."])  
        return False
    if not myBtcAddress:
        shared.debug(0,["Error: identity not defined."])
        
    dummy,sig = multisig.signText(myBtcAddress,workingContract.getContractTextOrdered())
    print "\n Here is the signature we made: \n",sig,"\n"
    contractLock.acquire()
    try:
        workingContract.sign(myBtcAddress,sig)
    finally:
        contractLock.release()
    
    return True

#When receiving a contract, first check it's signed and
#throw it out if not. Otherwise, store it in the list of contracts 
#that have been proposed by possible counterparties
#We can choose to accept at anytime, within the process/session.
#However we will not persist contract 'suggestions' across sessions.
def receiveContractCNE(msg):
    global myBtcAddress,workingContract,pendingContracts
    
    if not myBtcAddress:
        #shouldn't get here; if we haven't set an identity
        #then we won't report as "ONLINE".        
        shared.debug(0,["Ignored received contract since we haven't got an identity"])
        return 'Cannot receive contract without identity'
    
    allContractDetails = ':'.join(msg.split(':')[1:]).split('|')
    contractDetails = allContractDetails[0]
    #the contract is in json; need to change it to a Contract object
    contractDetailsDict = json.loads(contractDetails)
    tmpContract = Contract.Contract(contractDetailsDict)
    
    ca = getCounterparty(tmpContract)
    if not ca:
        return 'Contract invalid: does not contain this identity'
    
    for s in allContractDetails[1:]:
        ad = multisig.pubtoaddr(multisig.ecdsa_recover(tmpContract.getContractTextOrdered(),s))
        shared.debug(2,["\n recovery produced this address: ",ad,"\n"])
        tmpContract.signatures[ad]=s
    
    #now the temporary contract object is fully populated; 
    #we can check the signatures match the IDs in the contract
    for k,v in tmpContract.signatures.iteritems():
        if k not in [tmpContract.text['Buyer BTC Address'],tmpContract.text['Seller BTC Address']]:
            shared.debug(1,['Error: signature',v,'from',k,'was invalid'])
            return 'Invalid contract signature'
    
    contractLock.acquire()
    try:
        #note that this represents an override for
        #repeated sending of contracts; one cp can only
        #be suggesting one contract at a time
        pendingContracts[ca] = tmpContract
    finally:
        contractLock.release()
    #if the contract is already signed by me AND ctrprty, send it to escrow
    if len(tmpContract.signatures.keys())>1:
        contractLock.acquire()
        try:
            workingContract = tmpContract
            #wipe the pending contract list; we are only
            #interested in the live contract now
            pendingContracts = {}
        finally:
            contractLock.release()
        
    return 'Signed contract successfully received from counterparty: '+ca

def getCounterparty(contract):
    buyer,seller = [contract.text['Buyer BTC Address'],contract.text['Seller BTC Address']]
    if myBtcAddress not in [buyer,seller]:
        shared.debug(1,["Error, this contract does not contain us"])
        return None
    ca = buyer if seller==myBtcAddress else seller 
    return ca

#send a json dump of the contract contents
#also send to the chosen escrow if both parties signed
def sendSignedContractToCtrprtyCNE():
    #don't even try if we don't have a working identity
    if not myBtcAddress:
        return False
    #should already be initialised and signed
    if not workingContract.isSigned:
        return False
    #identify the counterparty
    msg_details = [workingContract.getContractText()]
    msg_details.extend([v for k,v in workingContract.signatures.iteritems()])
    msg = {workingContract.textHash+'.'+myBtcAddress:'CNE_SIGNED_CONTRACT:'+\
           '|'.join(msg_details)}
    shared.debug(0,["sending message:",msg])
    if len(workingContract.signatures.keys())>1:
        shared.debug(0,["\n **Sending a complete contract to the escrow**\n"])
        persistContract(workingContract)
        Msg.sendMessages(msg,g("Escrow","escrow_id")) 
    Msg.sendMessages(msg,getCounterparty(workingContract))
    return True

def persistContract(contract):
    shared.makedir([g("Directories","agent_base_dir"),"contracts"])
    with open(os.path.join(g("Directories","agent_base_dir"),\
                           "contracts",contract.textHash+'.contract'),'w') as fi:
        fi.write(contract.getContractTextOrdered())
        for k,v in contract.signatures.iteritems():
            fi.write(shared.PINL)
            fi.write("Signer: "+k)
            fi.write(shared.PINL)
            fi.write("Signature: "+v)
        
    
#messages coming from the "back end"
#(escrow MQ server) will either be processed
#directly by Python or sent to the front end
#for display
#MQ syntax will be isolated here
def processInboundMessages(parentThread):
    #infinite loop for getting messages
    while True:
        time.sleep(1)
        if not myBtcAddress:
            continue
        msg = Msg.getSingleMessage(myBtcAddress)
        if not msg:
            continue
        for t,m in msg.iteritems():
            if 'CNE_SIGNED_CONTRACT' in m:
                response = receiveContractCNE(m)
                #let the front end know we got it etc.
                qFrontEnd.put('CONTRACT RECEIVED:'+response)
                
            elif 'CNE_CHAT' in m:
                qFrontEnd.put('CHAT RECEIVED:'+t.split('.')[1]+':'+':'.join(m.split(':')[1:]))
            
            elif 'QUERY_STATUS_RESPONSE' in m:
                #status is online or offline (counterparty was specified in request)
                qFrontEnd.put('QUERY_STATUS_RESPONSE:'+m.split(':')[1])
                
                
                
if __name__ == "__main__":
    #first connect to CNE
    #code for reading order books and choosing escrow here?
    
    #Load all necessary configurations:
    helper_startup.loadconfig(sys.argv[1])    
    global myBtcAddress
    myEscrow = g("Escrow","escrow_id")
    d = os.path.join(g("Directories","agent_base_dir"),"multisig_store")
    p = g("Escrow","escrow_pubkey")
    #initialise multisig
    multisig.initialise(p,d)
    #need a connection to an escrow to do anything
    Msg.instantiateConnection()
    
    #for responding to messages from the escrow MQ server
    receiverThread = ThreadWithRetval(target= processInboundMessages)
    receiverThread.daemon = True
    receiverThread.start()  
    
    FF_to_backend_port = random.randint(1025,65535)
    FF_proxy_port = random.randint(1025,65535)
    thread = ThreadWithRetval(target= start_minihttp_thread)
    thread.daemon = True
    thread.start()  
    
    #read in contract details (for early testing only)
    contractDetails = {}
    with open("AppLayer/boilerplate.txt") as fi:
        lines = fi.readlines()
        for line in lines:
            if line.startswith('***'):
                k,v = line[3:].strip().split(':: ')
                contractDetails[k]=v
    
    workingContract = Contract.Contract(contractDetails)
    
    while True:
        if (myBtcAddress):
            print "****WORKING ON IDENTITY: "+myBtcAddress
            c,u = multisig.get_balance_lspnr(myBtcAddress)
            print "Current balance in this identity: confirmed: "+str(c)+", unconfirmed: "+str(u)
            print "******************************************************"
        try:
            shared.debug(0,["Earlier, received this from MQ:",qFrontEnd.get_nowait()])
        except:
            #necessary because empty queue raises Exception
            pass
        
        print """Please choose an option:
        [1] Send signed contract to counterparty
        [2] Send chat message
        [3] Exit
        [4] Check if counterparty is online
        [5] Space available
        [6] Space available
        [7] Show available pending contracts
        [8] Create or choose id
        [9] Modify and set the working contract
        [10] Purge old messages
        """
        choice = shared.get_validated_input("Enter an integer:",int)
        if choice==1:
            if not signContractCNE():
                print "something went wrong signing"
            if not sendSignedContractToCtrprtyCNE():
                print "you attempted to send an unsigned contract"
        elif choice == 2:
            text = shared.get_validated_input("Enter chat message:",str)
            sendChatToCtrprty(ctrprty,text)
            
        elif choice == 3:
            exit(0)
            
        elif choice == 4:
            if not ctrprty:
                print "You have to set the counterparty first!\n"
                continue
            sendCtrprtyAliveRequest(ctrprty,myEscrow)
            
        
        elif choice == 5:
            c = shared.get_binary_user_input("B/S","b","b","s","s")
            if c == 'b':
                ctrprty = contractDetails['Seller BTC Address']
            else:
                ctrprty = contractDetails['Buyer BTC Address']
                
        elif choice==6:
            print "Current contract hash:",workingContract.textHash
            print "Current contract details:",workingContract.getContractText()
            print "Current contract signatures:",workingContract.signatures
            
        elif choice==7:
            if not pendingContracts:
                print "No contracts are currently proposed."
                continue
            else:
                print "Counterparty \t Amount"
                print "**********************"
                for k,v in pendingContracts.iteritems():
                    print "["+k[:5]+"..] \t"+v.text['mBTC Amount']
                cchoice = shared.get_validated_input("Choose a counterparty identified by 5 characters:",str)
                for x in pendingContracts.keys():
                    if x.startswith(cchoice):
                        contractLock.acquire()
                        try:
                            workingContract = pendingContracts[x]
                            print "Contract chosen: " + x
                        finally:
                            contractLock.release()
                        break
                
        elif choice==8:
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
        elif choice==9:
            #for manually upgrading the working contract
            while True:
                print "current working contract:\n"
                for k,v in workingContract.text.iteritems():
                    print k,v
                for addr,sig in workingContract.signatures.iteritems():
                    print "Signed by: ",addr[:5],"..."
                    print "Signature: ",sig
                kchoice = shared.get_validated_input("Choose a parameter",str)   
                if kchoice not in workingContract.text.keys():
                    break
                vchoice = shared.get_validated_input("Set the value:",str)
                contractLock.acquire()
                try:
                    workingContract.modify(kchoice,vchoice)
                finally:
                    contractLock.release()
            
        elif choice==10:
            if not myBtcAddress:
                print "you need to define the identity before deleting its queue!"
                continue
            Msg.purgeMQ(myBtcAddress)
            
        else:
            print "invalid choice. Try again."


