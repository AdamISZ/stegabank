import os
import time
import json
import math
import shutil
import pickle
import codecs
import shared
import Queue
import threading
import subprocess
import Agent
import Contract
import NetworkAudit.sharkutils as sharkutils
import Messaging.MessageWrapper as Msg
from multisig_lspnr import multisig

#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class UserAgent(Agent.Agent):
    #list of available logins to any UserAgent instance, so class level
    
    
    def __init__(self,basedir,btcaddress,bankinfo,currency):
        
        #load our transactions
        super(UserAgent,self).__init__(basedir=basedir,\
                                       btcadd=btcaddress,currency=currency)
        
        self.escrows=[]
        #all user agents (not escrows) must provide basic bank info
        #TODO: put validation code that info has correct form
        self.bankInfo=bankinfo
        
        #The active escrow is not yet defined.
        self.activeEscrow = None
        
        #store the location used for the NSS key log file
        self.keyFile=g("Directories","ssl_keylog_file")
        
        #the running stcppipe which we own
        self.stcppipe_proc=None
        
        #the running ssh or plink process which we own
        self.ssh_proc = None
        
        self.firefox_proc = None
        
        #for initial contract negotation, keep track
        #of the contract we're currently examining
        self.workingContract=None
        
        #a list of candidate contracts sent here by counterparties
        #which we can accept or ignore
        self.pendingContracts = {}
        
        #control thread access to the the contract list
        self.contractLock = threading.Lock()
        
        #temporary storage queue for messages
        #passed from back-end to front-end
        self.qFrontEnd = Queue.Queue() 
        
        #self.inboundMessagingExit=False
        
    #calling this function for a particular transaction means that the user
    #has decided to carry out the required next action.
    #def takeAppropriateActions(self, txID):
        #tx = self.getTxByID(txID)
        
        ##tx.state must be in one of the 'pending' states:
        #if tx.state not in [300,501,502,700,701,702,706,800]:
            #return
        
        #if tx.state in [300,501]:
            #self.doBankingSession(tx)
            
        #elif tx.state==700 or (tx.getRole(self.uniqID())=='buyer' and tx.state==702) \
            #or (tx.getRole(self.uniqID())=='seller' and tx.state==701):
            #my_ssl_data = ','.join(self.getHashList(tx))
            #if tx.getRole(self.uniqID()) == 'buyer':
                ##need to send the magic hashes telling the escrow which other hashes
                ##to ignore in the comparison
                #my_ssl_data += '^'+','.join(self.getMagicHashList(tx))
                
            #self.activeEscrow.sendMessages(messages=\
            #{'x':'SSL_DATA_SEND:'+my_ssl_data},transaction=tx,rs=703)
            
        #elif tx.state==800 and tx.getRole(self.uniqID())=='buyer':
            ##TODO: this action naturally fits a GUI; for now just get
            ##user to choose one or more key numbers
            #keydir = os.path.join(g("Directories","agent_base_dir"),\
            #'_'.join([tx.getRole(self.uniqID()),tx.uniqID(),"banksession"]),"keys")
            #print ("You have chosen to send ssl keys to the escrow."
            #"Do this carefully. Check the folder: ", keydir ," and "
            #"decide which key number or numbers to send by looking at the "
            #"corresponding html in the html directory, then enter those "
            #"numbers here one by one at the prompt. When finished, type 0.")
            ##get a listing of all valid key files
            #all_keys = os.listdir(keydir)
            #requested_keys=[]
            #while True:
                #choice = shared.get_validated_input("Enter a number (0 to quit)",int)
                #if choice == 0:
                    #if not any(requested_keys):
                        #print "Error, you must select at least one key."
                    #else:
                        #print "Keys will now be sent to escrow."
                        #break
                #else:
                    #if str(choice)+'.key' not in all_keys:
                        #print "That number does not correspond to an existing \
                            #key, please try again."
                    #else:
                        #requested_keys.append(os.path.join(keydir,str(choice)+'.key'))
                        
            #self.sendSSLKeys(tx,requested_keys)
            
        #else:
            #shared.debug(0,["Unexpected request to perform action on",\
                            #"a transaction that doesn't need anything done."])
    
    def processInboundMessages(self,parentThread):
        '''messages coming from the "back end" (escrow MQ server) are picked up here.
        Message syntax will be the same for front end and back end communication, 
        improving intelligibility.
        Automatic responses to MQ instructions occurs here, 
        whereas anything that needs user input or is purely informational
        is blindly passed up to the front end.'''   
        
        #need a connection to an escrow to do anything
        Msg.instantiateConnection(chanIndex=1) 
        
        #infinite loop for getting messages
        while True:
            time.sleep(1)
            
            #if self.inboundMessagingExit:
            #    return
               
            msg = self.getSingleMessage(chanIndex=1)
            if not msg:
                continue
            for k,m in msg.iteritems():
                
                if 'CNE_SIGNED_CONTRACT' in m:
                    response = self.receiveContractCNE(m)
                    #let the front end know we got it etc.
                    self.qFrontEnd.put('CONTRACT RECEIVED:'+response)
                    continue
                    
                elif 'CNE_CHAT' in m:
                    self.qFrontEnd.put('CHAT RECEIVED:'+k.split('.')[1]+\
                                  ':'+':'.join(m.split(':')[1:]))
                    continue
                
                elif 'CNE_CONTRACT_SUCCESS' in m:
                    escrowAddressConfirmation,contractJSON,escrowSig =\
                        ':'.join(m.split(':')[1:]).split('|')
                    
                    #validate escrow address
                    if not escrowAddressConfirmation == \
                       multisig.pubtoaddr(g("Escrow","escrow_pubkey")):
                        raise Exception("Panic! We are talking to the wrong escrow:"\
                                        +escrowAddressConfirmation)
                    
                    testingContract = Contract.Contract(json.loads(contractJSON))
                    
                    #validate escrow's signature and append to the contract
                    if not multisig.ecdsa_verify(testingContract.getContractTextOrdered(),\
                                                 escrowSig,g("Escrow","escrow_pubkey")):
                        raise Exception("Panic! We received an invalid signature from the escrow.")
                    
                    #set this as the working contract in case it isn't
                    if self.workingContract != testingContract:
                        shared.debug(0,["Warning, switched back to the contract as informed by escrow"])
                        contractLock.acquire()
                        try:
                            self.workingContract = testingContract
                        finally:
                            contractLock.release()
                    
                    self.qFrontEnd.put(m)
                    continue
                
                elif 'RE_BANK_SESSION_START_REQUEST' in m:
                    t = self.getTxByID(k.split('.')[0])
                    if self.uniqID() != t.seller:
                        shared.debug(0,["Error, received bank session request but not seller"])
                        continue
                    else:
                        self.sendMessage('RE_BANK_SESSION_START_ACCEPTED:',recipientID='RE', txID=t.uniqID(),chanIndex=1)
                        self.startBankingSession(t)
                        continue
                
                elif 'RE_BANK_SESSION_START_ACCEPTED' in m or \
                     'RE_BANK_SESSION_START_REJECTED' in m:
                    shared.debug(0,["Received an acceptance or rejection, putting to queue",k,m])
                    self.qFrontEnd.put({k:m})
                    continue
                
                elif 'RE_TRANSACTION_SYNC_RESPONSE' in m or \
                     'RE_TRANSACTION_SYNC_COMPLETE' in m:
                    self.qFrontEnd.put({k:m})
                    continue
                
                elif 'RE_BANK_SESSION_ENDED' in m:
                    transaction = self.getTxByID(k.split('.')[0])
                    if not transaction.getRole(self.uniqID()) == 'seller':
                        shared.debug(0,["Error, bank session end message received but not the seller"])
                        continue
                    rspns = m.split(':')[1]
                    self.endBankingSession(transaction, rspns)
                
                elif 'RE_SSL_KEYS_REQUEST' in m:
                    transaction = self.getTxByID(k.split('.')[0])
                    
                else:
                    #catch all for messages which just go to the front end
                    shared.debug(0,["Putting this to the q,",m])
                    self.qFrontEnd.put(m)
    
    
    def signContractCNE(self):
        if not self.workingContract:
            shared.debug(0,["Error: contract not defined."])  
            return False   
        dummy,sig = multisig.signText(self.uniqID(),\
                    self.workingContract.getContractTextOrdered())
        shared.debug(3,["Here is the signature we made:",sig])
        self.contractLock.acquire()
        try:
            self.workingContract.sign(self.uniqID(),sig)
        finally:
            self.contractLock.release()
        return True
    
    def sendSignedContractToCtrprtyCNE(self):
        '''send a json dump of the contract contents
        also send to the chosen escrow if both parties signed        
        should already be initialised and signed'''
        if not self.workingContract or not self.workingContract.isSigned:
            return False
        msg_details = [self.workingContract.getContractText()]
        msg_details.extend([v for k,v in self.workingContract.signatures.iteritems()])
        msg = 'CNE_SIGNED_CONTRACT:'+'|'.join(msg_details)
        shared.debug(0,["sending message:",msg])
        if len(self.workingContract.signatures.keys())>1:
            shared.debug(0,["\n **Sending a complete contract to the escrow**\n"])
            self.persistContract(self.workingContract)
            self.sendMessage(msg,recipientID='CNE',\
                             txID=self.workingContract.textHash) 
        self.sendMessage(msg,\
            recipientID=self.workingContract.getCounterparty(self.uniqID()),\
            txID=self.workingContract.textHash)
        return True
    
    def printPendingContracts(self):
        print "Counterparty \t Amount"
        print "**********************"
        for k,v in self.pendingContracts.iteritems():
            print "["+k[:5]+"..] \t"+v.text['mBTC Amount']
        cchoice = shared.get_validated_input("Choose a counterparty identified by 5 characters:",str)
        for x in self.pendingContracts.keys():
            if x.startswith(cchoice):
                self.contractLock.acquire()
                try:
                    self.workingContract = self.pendingContracts[x]
                    print "Contract chosen: " + x
                finally:
                    self.contractLock.release()
                break
    
    def editWorkingContract(self):
        while True:
            print "current working contract:\n"
            for k,v in self.workingContract.text.iteritems():
                print k,v
            for addr,sig in self.workingContract.signatures.iteritems():
                print "Signed by: ",addr[:5],"..."
                print "Signature: ",sig
            kchoice = shared.get_validated_input("Choose a parameter",str)   
            if kchoice not in self.workingContract.text.keys():
                break
            vchoice = shared.get_validated_input("Set the value:",str)
            self.contractLock.acquire()
            try:
                self.workingContract.modify(kchoice,vchoice)
            finally:
                self.contractLock.release()        

    def payInitialFees(self):
        #Working in mbtc here.
        txf = shared.defaultBtcTxFee
        if not self.workingContract:
            raise Exception("Tried to pay fees but there's no active contract")
        
        btc = int(self.workingContract.text['mBTC Amount'])
        bd = int(self.workingContract.text['Buyer Deposit Fee'])
        sd = int(self.workingContract.text['Seller Deposit Fee'])
        bf = int(self.workingContract.text['Buyer Escrow Fee'])
        sf = int(self.workingContract.text['Seller Escrow Fee'])    
        
        #get our role
        role = 'buyer' if self.workingContract.text['Buyer BTC Address']==self.uniqID() else 'seller'
        
        if role == 'buyer':
            feeToPay = bd+bf
        else: 
            #TODO is it either feasible or desirable for the seller to pay 'btc' here? Probably not.
            feeToPay =sd+sf
        
        #check that we hold sufficient funds; values are returned in btc
        c,u = multisig.get_balance_lspnr(self.uniqID())
        #the extra 0.5 fee to be paid is to allow for cost of transfer from cne to re
        if feeToPay+math.ceil(txf*1.5) >= c:
            shared.debug(0,["Cannot pay - insufficient funds. Confirmed funds:",\
                            str(c),",unconfirmed:",str(u),"while fee is: ",str(feeToPay+math.ceil(txf*1.5))])
            return
        
        #we use any utxos, so "payers" is None
        feeSpendingTxHash = multisig.spendUtxos(self.uniqID(),self.uniqID(),\
                            multisig.pubtoaddr(g("Escrow","escrow_pubkey")),None,amt=feeToPay+txf)    
        if not feeSpendingTxHash:
            shared.debug(0,["Error, cannot pay the fee because of insufficient funds at address:",myBtcAddress])
            return False
        else:
            return feeSpendingTxHash
        
    def persistContract(self,contract):
        shared.makedir([g("Directories","agent_base_dir"),"contracts"])
        with open(os.path.join(g("Directories","agent_base_dir"),\
                               "contracts",contract.textHash+'.contract'),'w') as fi:
            fi.write(contract.getContractTextOrdered())
            for k,v in contract.signatures.iteritems():
                fi.write(shared.PINL)
                fi.write("Signer: "+k)
                fi.write(shared.PINL)
                fi.write("Signature: "+v)
    
    def receiveContractCNE(self,msg):
        '''When receiving a contract, first check it's signed and
            throw it out if not. Otherwise, store it in the list of contracts 
            that have been proposed by possible counterparties
            We can choose to accept at anytime, within the process/session.
            However we will not persist contract 'suggestions' across sessions. '''        
        
        allContractDetails = ':'.join(msg.split(':')[1:]).split('|')
        contractDetails = allContractDetails[0]
        #the contract is in json; need to change it to a Contract object
        contractDetailsDict = json.loads(contractDetails)
        tmpContract = Contract.Contract(contractDetailsDict)
        
        ca = tmpContract.getCounterparty(self.uniqID())
        
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
        
        self.contractLock.acquire()
        try:
            #note that this represents an override for
            #repeated sending of contracts; one cp can only
            #be suggesting one contract at a time
            self.pendingContracts[ca] = tmpContract
        finally:
            self.contractLock.release()
        #if the contract is already signed by me AND ctrprty, send it to escrow
        if len(tmpContract.signatures.keys())>1:
            self.contractLock.acquire()
            try:
                self.workingContract = tmpContract
                #wipe the pending contract list; we are only
                #interested in the live contract now
                self.pendingContracts = {}
            finally:
                self.contractLock.release()
            
        return 'Signed contract successfully received from counterparty: '+ca
    
    
    #TODO: this action naturally fits a GUI; for now just get
                #user to choose one or more key numbers
    def chooseSSLKeys(self,tx):
        keydir = os.path.join(g("Directories","agent_base_dir"),\
        '_'.join([tx.getRole(self.uniqID()),tx.uniqID(),"banksession"]),"keys")
        print ("You have chosen to send ssl keys to the escrow."
        "Do this carefully. Check the folder: ", keydir ," and "
        "decide which key number or numbers to send by looking at the "
        "corresponding html in the html directory, then enter those "
        "numbers here one by one at the prompt. When finished, type 0.")
        #get a listing of all valid key files
        all_keys = os.listdir(keydir)
        requested_keys=[]
        while True:
            choice = shared.get_validated_input("Enter a number (0 to quit)",int)
            if choice == 0:
                if not any(requested_keys):
                    print "Error, you must select at least one key."
                else:
                    print "Keys will now be sent to escrow."
                    break
            else:
                if str(choice)+'.key' not in all_keys:
                    print "That number does not correspond to an existing \
                        key, please try again."
                else:
                    requested_keys.append(os.path.join(keydir,str(choice)+'.key'))
                    
        self.sendSSLKeys(tx,requested_keys)  
                
                
                
    #must be called with a list of filenames that the user has chosen,
    #each containing a particular ssl key (in the "keys" subdirectory under
    #the transaction directory)
    def sendSSLKeys(self,transaction,keyfiles):
        if (transaction.getRole(self.uniqID()) != 'buyer'):
            shared.debug(0,["Error, get keys was called for a transaction",\
                            "where we're not the buyer!"])
        keys = []
        for kf in keyfiles:
            with open(kf) as f:
                shared.debug(0,["Trying to open a keyfile:",kf])
                keys.append(f.readline())
        shared.debug(0,["Set keys to:",keys])
        self.sendMessage('RE_SSL_KEYS_SEND:'+','.join(keys),recipientID='RE',\
                         txID=transaction.uniqID())
        
    #to be called after escrow accessor is initialised
    #and transaction list is synchronised.
    #return value is a dict of transaction IDs with actionable items
    def processExistingTransactions(self):
        #any transaction in one of these states means something 
        #needs to be done. See AppLayer/TransactionStateMap.txt
        actionables = {}
        need_to_process = [300,500,501,502,700,701,702,800]
        for tx in self.transactions:
            if tx.state not in need_to_process:
                continue
            if tx.state in [300,501,500]:
                if tx.getRole(self.uniqID())=='buyer':
                    actionables[tx.uniqID()]='Transaction is ready. Please \
                        coordinate with seller to perform internet banking'
                else:
                    actionables[tx.uniqID()]='Transaction is ready. Please \
                    communicate with buyer and ensure squid is running so that\
                        banking session can be performed.'
            elif tx.state==700 or (tx.state==701 and tx.getRole(self.uniqID())=='seller') \
                or (tx.state==702 and tx.getRole(self.uniqID())=='buyer'):
                actionables[tx.uniqID()]='Transaction is in dispute. Please \
                    send ssl data.'
            elif tx.state == 800 and tx.getRole(self.uniqID())=='buyer':
                actionables[tx.uniqID()]='Transaction has been escalated to \
                    human escrow adjudication, since all ssl was consistent. \
                    Please check which html pages you want to expose to escrow \
                    and then send the appropriate ssl key(s) to the escrow.'
                
        return actionables
    
    def startBankingSession(self,transaction):
        role = transaction.getRole(self.uniqID())
        if role=='invalid':
            shared.debug(0,["Trying to start a banking session but we're not"
                            "buyer or seller for the transaction!"])
            return False
        
        #wipe clean the keylog file
        #remove pre-existing ssl key file so we only load the keys for this run
        #TODO: make sure the user has set the ENV variable - pretty disastrous
        #otherwise!
        if role=='buyer':
            shared.silentremove(self.keyFile)
            os.putenv('SSLKEYLOGFILE',self.keyFile)
        
        #create local directories to store this banking session
        #format of name is: role_txid_'banksession'
        #TODO consider how banking sessions may be first class objects;
        #may need more than one per tx
        runID='_'.join([role,transaction.uniqID(),'banksession'])
        d = shared.makedir([self.baseDir,runID])
        #make the directories for the stcp logs
        new_stcp_dir=shared.makedir([d,'stcplog'])
        
        shared.debug(0,["setting up banking session as ",role,"\n"])
        
        #notice that the calls for buyer and seller are very similar
        #but the duplication is safer as there are small, easy to miss differences!
        
        #TODO how to make sure we start clean (no old stcppipe procs)?
        if self.stcppipe_proc:
            self.stcppipe_proc.kill()        

        if role == 'buyer':
            self.ssh_proc = shared.local_command([g("Exepaths","ssh_exepath"), \
g("Agent","escrow_ssh_user") +'@'+g("Escrow","escrow_host"),'-p', \
g("Escrow","escrow_ssh_port"), '-i', g("Agent","escrow_ssh_keyfile"),'-N','-L', \
g("Agent","agent_stcp_port")+':127.0.0.1:'+g("Escrow","escrow_input_port")],\
    bg=True)
            
            self.stcppipe_proc = shared.local_command([g("Exepaths","stcppipe_exepath"),\
            '-d',new_stcp_dir,'-b','127.0.0.1',g("Agent","agent_stcp_port"),\
            g("Agent","agent_input_port")],bg=True)
            
        else: 
            self.ssh_proc = shared.local_command([g("Exepaths","ssh_exepath"), \
g("Agent","escrow_ssh_user")+'@'+g("Escrow","escrow_host"),'-p', \
g("Escrow","escrow_ssh_port"), '-i', g("Agent","escrow_ssh_keyfile"),'-N','-R',\
g("Escrow","escrow_host")+':'+g("Escrow","escrow_stcp_port")+':127.0.0.1:'\
+g("Agent","agent_input_port")],bg=True)
            
            self.stcppipe_proc = shared.local_command([g("Exepaths","stcppipe_exepath"),\
            '-d',new_stcp_dir,'-b','127.0.0.1',g("Agent","agent_stcp_port"),\
            g("Agent","agent_input_port")],bg=True)
        
        if role=='buyer':
            print ("When firefox starts, please perform internet banking."
            "If you can't connect, please close the browser."
            "If you can connect, then when you have finished your internet"
            "banking, please close firefox.")
            
            #set correct proxy port
            os.putenv("FF_proxy_port", g("Agent","agent_input_port"))
            
            time.sleep(5)
            if not self.startFirefox():
                shared.debug(0,["Critical error, failed to start firefox."])
                return False
            
            #wait for firefox to close
            while True:
                    time.sleep(1)
                    if self.ff_proc.poll() != None:
                        #FF window was closed, shut down all subsystems and exit gracefully
                        self.stcppipe_proc.kill()
                        self.ssh_proc.kill()
                        break            
            rspns = shared.get_binary_user_input(\
                "Did you complete the payment successfully?",'y','y','n','n')
            
            #we have finished our banking session. We need to tell the others.
            self.sendConfirmationBankingSessionEnded(transaction,rspns)
            #TODOput some code to get the confirmation of storage from escrow
            #(and counterparty?) so as to be sure everything was done right
            return rspns

        #seller returns true if network arch set up was OK
        return True 
        
    #this message is to be used by buyers only
    def sendConfirmationBankingSessionEnded(self,tx,rspns):
        #sanity check
        if tx.getRole(self.uniqID()) != 'buyer':
            shared.debug(0,["Error: user agent:",self.agent.uniqID(),\
        "is not the buyer for this transaction and so can't confirm the end",\
            "of the banking session!"])  
        #construct a message to the escrow
        shared.debug(0,["Sending bank session end confirm to seller and escrow"])
        self.sendMessage('RE_BANK_SESSION_ENDED:'+rspns,recipientID='RE',txID=tx.uniqID())
    
    def makeRedemptionSignature(self,transaction,toCounterparty=True):
        
        ctrprtyID = transaction.buyer if transaction.seller == self.uniqID()\
            else transaction.seller
        receiver = ctrprtyID if toCounterparty else self.uniqID()
        #TODO this assumes the seller is signing
        return multisig.createSigForRedemptionRaw(transaction.getCtrprtyPubkey(False),\
                                                  transaction.getCtrprtyPubkey(True),\
                                                  g("Escrow","escrow_pubkey"),\
                                                  transaction.sellerFundingTransactionHash, 
                                                 receiver)
        
    def startFirefox(self):    
        #if not os.path.isdir(os.path.join(datadir, 'firefox')): 
        #    os.mkdir(os.path.join(datadir, 'firefox'))
        ffdir = shared.makedir([self.baseDir,'firefox'])
        #touch files
        for fn in ['stdout','stderr']:
            open(os.path.join(ffdir,'firefox.'+fn), 'w').close()
        if not os.path.isfile(os.path.join(ffdir,'FF-profile', 'extensions.ini')):
        #FF rewrites extensions.ini on first run, so we allow FF to create it,
        #then we kill FF, rewrite the file and start FF again
            try:
                self.ff_proc = subprocess.Popen([g("Exepaths","firefox_exepath"),\
                '-no-remote','-profile', os.path.join(ffdir, 'FF-profile')], \
                stdout=open(os.path.join(ffdir,"firefox.stdout"),'w'), \
                stderr=open(os.path.join(ffdir, "firefox.stderr"),'w'))
                
            except Exception,e:
                shared.debug(0,["Error starting Firefox"])
                return ["Error starting Firefox"]
            
            while 1:
                time.sleep(0.5)
                if os.path.isfile(os.path.join(ffdir,'FF-profile', 'extensions.ini')):
                    self.ff_proc.kill()
                    break
                
            try:
                #enable extension                            
                with codecs.open (os.path.join(ffdir, 'FF-profile', \
                                               'extensions.ini'), "w") as f1:
                    f1.write("[ExtensionDirs]\nExtension0=" + \
                             os.path.join(ffdir, 'FF-profile',\
                             "extensions", "lspnr@lspnr") + "\n")
                #show addon bar
                with codecs.open(os.path.join(ffdir, \
                                'FF-profile', 'localstore.rdf'), 'w') as f2:
                    f2.write('<?xml version="1.0"?><RDF:RDF xmlns:NC="http://home.netscape.com/NC-rdf#" xmlns:RDF="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><RDF:Description RDF:about="chrome://browser/content/browser.xul"><NC:persist RDF:resource="chrome://browser/content/browser.xul#addon-bar" collapsed="false"/></RDF:Description></RDF:RDF>')    
            except Exception,e:
                shared.debug(0,['File open error'])
                return False 
              
        os.putenv("SSLKEYLOGFILE", self.keyFile)
        
        #used to prevent addon's confusion when certain sites open new FF windows
        #TODO wtf is this?
        os.putenv("FF_first_window", "true")
        
        shared.debug(0,["Starting a new instance of Firefox with Paysty's profile"])
        
        try:
            self.ff_proc = subprocess.Popen([g("Exepaths","firefox_exepath"),\
                    '-no-remote', '-profile', os.path.join(ffdir, 'FF-profile')],\
                    stdout=open(os.path.join(ffdir, "firefox.stdout"),'w'),\
                    stderr=open(os.path.join(ffdir, "firefox.stderr"), 'w'))
        except Exception,e:
            shared.debug(0,["Error starting Firefox"])
            return ["Error starting Firefox"]   
        return True
     
    #the argument rspns indicates whether or not the banking session 
    #was successful
    def endBankingSession(self,transaction,rspns):
        
        #tear down network connections
        self.stcppipe_proc.kill()
        
        role = transaction.getRole(self.uniqID())
            
        if role=='buyer' and rspns=='y':
            #copy the premaster secrets file into the testing directory
            #so that it can be decrypted at a later stage by the buyer
            runID='_'.join([role,transaction.uniqID(),'banksession'])
            key_file_name = os.path.join(g("Directories",'agent_base_dir'),\
                                         runID,runID+'.keys')
            shutil.copy2(self.keyFile,key_file_name)
            transaction.keyFile = key_file_name
            
            #TODO: consider how in the transaction model, the keyFile
            #info is/is not propagated to the escrow, who after all must
            #be the arbiter of the correct state of the transaction object
            
            #3 Oct 2013: now we want to provide the buyer with the ability to 
            #(a) read the html traced and (b) to separate it per ssl key for
            #selective upload to escrow in case of dispute
            #note: this will work assuming the user has chosen to clear
            #the ssl cache after each click, or some automated version of
            #that has been implemented in the plugin
            #(first step is to create a merged trace file:)
            stcpdir=os.path.join(g("Directories",'agent_base_dir'),runID,'stcplog')
            merged_trace = os.path.join(stcpdir,'merged.pcap')
            sharkutils.mergecap(merged_trace,stcpdir,dir=True)
            html = sharkutils.get_html_key_by_key(merged_trace,transaction.keyFile)
            d = os.path.join(os.path.dirname(transaction.keyFile),'html')
            if not os.path.exists(d): os.makedirs(d)
            for k,v in html.iteritems():
                if not v:
                    continue
                for i,h in enumerate(v):
                    #file format: key number_htmlindex.html, all
                    #stored in a subdirectory called 'html'.
                    f = os.path.join(d,k+'_'+str(i)+'.html')
                    fh = open(f,'w')
                    print>>fh, h
                    fh.close()
            #in GUI(?) we can now give user ability to select html
            #to send, in case there's a dispute, and he'll only send the 
            #key(s) that correspond to that html
            
        new_state = 602 if rspns=='y' else 603
        self.transactionUpdate(tx=transaction,new_state=new_state)
        
    
#Important: it's guaranteed that self.agent has already loaded its 
    #transactions.p database since that action occurs in the Agent constructor.
    #Callers MUST pay attention to return value; if false, the sync failed
    #and we'll have to try again or something.
    def synchronizeTransactions(self):
        
        #make absolutely sure we're not responding to stale data:
        #while True:
        #    msg = self.getSingleMessage()
        #    if not msg:
        #        break
            
        self.sendMessage('RE_TRANSACTION_SYNC_REQUEST:',recipientID='RE')
        
        while True:
            #wait for response; we don't expect a long wait as it's a low
            #intensity workload for escrow
            #msg = self.getSingleMessage() 
            
            msg=None
            
            try:
                msg = self.qFrontEnd.get_nowait()
            except:
                pass #in case queue is empty
            
            shared.debug(5,["Got",msg])
            if not msg:
                #we stay here since we insist on getting a response.
                #in the absence of an up to date transaction list, nothing
                #can proceed
                time.sleep(1)
                shared.debug(5,["Waiting for escrow response.."])
                #TODO need some failure mode here
                continue
            print msg
            
            hdr,data = msg.values()[0].split(':')[0],':'.join(msg.values()[0].split(':')[1:])
            
            if hdr == 'RE_TRANSACTION_SYNC_COMPLETE':
                break
            
            if hdr != 'RE_TRANSACTION_SYNC_RESPONSE':
                shared.debug(0,["The message server sent a wrong message in the"\
                                "stream of transaction data."])
                continue
            
            if not data:
                #there were no pre-existing transactions
                return True
            #load as ascii string; docs promise it works
            tx = pickle.loads(data)
            
            #in this section we'll break the rule of not updating the tx
            #list directly because we commit at the end.
            if tx.uniqID() in [a.uniqID() for a in self.transactions]:
                #replace old with new
                self.transactions = [tx if x.uniqID()==tx.uniqID() \
                                    else x for x in self.transactions]
                
            else:
                #Completely new transaction, unknown to user.
                #This usually won't happen; it means the useragent has "lost"
                #a transaction object
                shared.debug(0,["We're adding a new one"])
                self.transactions.append(tx)
                
        #finished making changes, persist
        try:
            self.transactionUpdate(full=True)
        except:
            shared.debug(0,["Failure to synchronize transaction list!"])
            return False
        
        #success
        self.printCurrentTransactions()
        
        return True  
    
    
    #this method is at useragent level only as it's only for buyers
    #see details in sharkutils.get_magic_hashes
    def getMagicHashList(self, tx):
        if (tx.getRole(self.uniqID()) != 'buyer'):
            shared.debug(0,["Error! You cannot send the magic hashes unless"\
                            "you\'re the buyer!"])
            exit(1)
            
        txdir = os.path.join(g("Directories","agent_base_dir"),\
                        '_'.join(["buyer",tx.uniqID(),"banksession"]))
        stcpdir = os.path.join(txdir,"stcplog")
        kf = os.path.join(txdir,'_'.join(['buyer',tx.uniqID(),'banksession.keys']))
        shared.debug(0,["Trying to find any magic hashes located in:",\
                    stcpdir,"using ssl decryption key:",kf])
        return sharkutils.get_magic_hashes(stcpdir,kf,\
                                        port=g("Agent","agent_stcp_port"))
        
    #unused for now
    def findEscrow(self):
        print "finding escrow\n"
        self.escrow = EscrowAgent()
    
    def addEscrow(self,escrow):
        self.escrows.append(escrow)
        return self
    
    def setActiveEscrow(self,escrow):
        if escrow in self.escrows:
            self.activeEscrow = escrow 
        else:
            raise Exception("Attempted to set active an escrow which is not known to this user agent!.\n")
        return self
        
    
