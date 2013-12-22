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

workingContract = None
#working on a maximum of one contract at a time
contractLock = threading.Lock()

#temporary storage queue for messages
#passed from back-end to front-end
qFrontEnd = Queue.Queue()
workingCtrprtyPub = None
myBtcAddress = None
ddir = None

if OS=='win':
    stcppipe_exepath = os.path.join(ddir,'stcppipe', 'stcppipe.exe')
    tshark_exepath = os.path.join(ddir,'wireshark', 'tshark.exe')
    mergecap_exepath = os.path.join(ddir,'wireshark', 'mergecap.exe')
    plink_exepath = os.path.join(ddir, 'plink.exe')    
if OS=='linux':
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
            print ('Received signing request')
            raddr,mbal,myid,cpid = urllib2.unquote(self.path.split('?')[1]).split()
            print ('Received a destination address: '+raddr)
            print ('Received an owned balance: '+mbal)
            print ('Received an owned id: '+myid)
            print ('Received a ctrprty id: '+cpid)
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
            print ('Received a request to get the balance')
            addr = urllib2.unquote(self.path.split('?')[1])
            conf,unconf = multisig.check_balance_at_multisig('x','x',addr=addr)
            print ('got an unconf balance of: '+str(unconf))
            self.send_response(200)
            self.send_header("response","get_balance")
            self.send_header("confirmedbalance",str(conf))
            self.send_header("unconfirmedbalance",str(unconf))
            self.end_headers()
            return
            
        #chat message format going TO oracle: '<uniqueid_recipient> <type> [data..]'
        if self.path.startswith('/send_chat'):
            print ('Received a chat message send request')
            #need everything after the first question mark, including question marks
            chatdata = '?'.join(self.path.split('?')[1:])
            chatdata = urllib2.unquote(chatdata)
            params = chatdata.split()
            if len(params[0]) != 64:
                print ('Error: id of recipient wrong length')
            print ('recipient is: '+params[0])
            print ('type is: '+params[1])
            print ('message is: '+' '.join(params[2:]))
            send_chat_to_oracle(params[0],params[1],' '.join(params[2:]))
            print ('Received a chat message and sent to oracle')
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
            print ('Sending back: '+retval + assigned_port)
            if retval == 'reconnect':
                self.send_response(200)
                self.send_header("response", "start_tunnel")
                #assigned_port now contains the new port which sshd wants us to reconnect to
                self.send_header("value", "reconnect;"+assigned_port)
                self.end_headers()                
            if retval != 'success':
                print ('Error while setting up a tunnel: '+retval, end='\r\n')
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
def buyer_start_minihttp_thread(parentthread):
    global FF_to_backend_port
    print ('Starting mini http server to communicate with Firefox plugin',end='\r\n')
    try:
        httpd = StoppableHttpServer(('127.0.0.1', FF_to_backend_port), buyer_HandlerClass)
    except Exception, e:
        print ('Error starting mini http server', e,end='\r\n')
        exit(1)
    sa = httpd.socket.getsockname()
    print ("Serving HTTP on", sa[0], "port", sa[1], "...",end='\r\n')
    retval = httpd.serve_forever()

    
def setup(btcAddress):
    global myBtcAddress, ddir
    myBtcAddress = btcAddress
    shared.makedir([g("DATA_DIRS","Personal Data"),myBtcAddress])
    
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
    msg = {tx+'.'+myBtcAddress:'CHAT_MESSAGE:'+msgToSend}
    Msg.sendMessages(msg,ctrprty)
    

#'contractDetails' will be a dict
#passed in from the client interface
#a False return indicates you tried to sign a contract
#which didn't match the one sent by your counterparty
def signContractCNE(contractDetails):
    
    global workingContract
    tmpContract = Contract.Contract(contractDetails)
    if not workingContract:
        workingContract = tmpContract    
    else:
        tmpContract = Contract.Contract(contractDetails)
        if not tmpContract==workingContract:
            return False
        
    #for multisigs and for signing during this tx
    addr,pub,priv = multisig.create_tmp_address_and_store_keypair(workingContract.textHash)
    
    sig = multisig.ecdsa_sign(workingContract.textHash,priv)
    
    contractLock.acquire()
    try:
        workingContract.sign(myBtcAddress,sig)
    finally:
        contractLock.release()
    
    if len(workingContract.signatures.keys()) > 1:
        #2 signatures is ready to send
        sendSignedContractToEscrowCNE()
    
    return True

#contract has been sent by counterparty
#we need to (a) look at it, (b) validate the signature
#(c) sign and send back (if we like it).
def receiveContractCNE(msg):
    global workingCtrprtyPub,myBtcAddress,workingContract
    
    ctrprtyPub,contractDetails,ctrprtySig = msg.split(':')[1].split('|')
    #the contract is in json; need to change it to a Contract object
    contractDetails = json.loads(contractDetails)
    
    workingCtrprtyPub = ctrprtyPub
    
    #check the sig
    tmpContract = Contract.Contract(contractDetails)
    valid = False
    for k,v in tmpContract.signatures.iteritems():
        if (k != myBtcAddress):
            valid = multisig.ecdsa_verify(tmpContract.textHash,v,ctrprtyPub)
            ctrprtyAddress = k
    if not valid:
        shared.debug(1,['Error: no valid signature from counterparty'])
        return 'Invalid contract signature'
    contractLock.acquire()
    try:
        workingContract = tmpContract
    finally:
        contractLock.release()
    
    return 'Signed contract successfully received from counterparty: '+ctrprtyAddress

#send a json dump of the contract contents
#optionally also send to the chosen escrow
def sendSignedContractToCtrprtyCNE(escrow=False):
    
    #should already be signed
    if not workingContract.isSigned:
        return False
    
    #the counterparty is in the contract:
    for addr in [workingContract.text['Buyer BTC Address'],\
                 workingContract.text['Seller BTC Address']]:
        if addr != myBtcAddress:
            ctrprty = addr
            
    #get our pubkey, since the ctrprty needs it to verify the sig
    pub = multisig.getKeysFromUniqueID(myBtcAddress)
    
    if not workingContract.signatures:
        shared.debug(0,["Error: tried to send an unsigned contract."])
    msg_details = [pub,workingContract.getContractText()]
    msg_details.extend([v for k,v in workingContract.signatures.iteritems()])
    msg = {workingContract.textHash+'.'+myBtcAddress:'CNE_SIGNED_CONTRACT:'+\
           '|'.join(msg_details)}
    Msg.sendMessages(msg,ctrprty)
    if escrow:
        Msg.sendMessages(msg,escrow)      
    return True

#messages coming from the "back end"
#(escrow MQ server) will either be processed
#directly by Python or sent to the front end
#for display
#MQ syntax will be isolated here
def processInboundMessages():
    #infinite loop for getting messages
    while True:
        time.sleep(1)
        msg = Msg.getSingleMessage(myBtcAddress)
        for t,m in msg.iteritems():
            if 'CNE_SIGNED_CONTRACT' in m:
                response = receiveContractCNE(m)
                #let the front end know we got it etc.
                qFrontEnd.put('CONTRACT RECEIVED:'+response)
                
            elif 'CNE_CHAT' in m:
                qFrontEnd.put('CHAT RECEIVED:'+t.split('.')[1]+':'+m.split(':')[1:])
            
            elif 'QUERY_STATUS_RESPONSE' in m:
                #status is online or offline (counterparty was specified in request)
                qFrontEnd.put('QUERY_STATUS_RESPONSE'+m.split(':')[1])
                
                
                
if __name__ == "__main__":
    #first connect to CNE
    #code for reading order books and choosing escrow here?
    
    #need a connection to an escrow to do anything
    Msg.instantiateConnection()
    
    #for responding to messages from the escrow MQ server
    receiverThread = ThreadWithRetval(target= processInboundMessages)
    receiverThread.daemon = True
    receiverThread.start()  
    
    FF_to_backend_port = random.randint(1025,65535)
    FF_proxy_port = random.randint(1025,65535)
    thread = ThreadWithRetval(target= buyer_start_minihttp_thread)
    thread.daemon = True
    thread.start()    

