import time
import math
import os
import pickle
import Queue
import threading
import shared
import Agent
from AppLayer.Transaction import Transaction
import NetworkAudit.sharkutils as sharkutils
import Messaging.MessageWrapper as Msg
import helper_startup as hs
from multisig_lspnr import multisig
import Contract
import json
#for brevity
def g(x,y):
    return shared.config.get(x,y)



#this object runs on the escrow server
class EscrowAgent(Agent.Agent):
    
    def __init__(self,basedir,btcaddress):
        super(EscrowAgent,self).__init__(basedir=basedir, btcadd=btcaddress)
        shared.debug(1,[\
        "instantiating an escrow agent, listening for messages"])
        
        #messaging server should always be local for escrow
        self.host='127.0.0.1'
        
        Msg.instantiateConnection(un='escrow',pw='escrow')
        
        #hardcoded for testing TODO
        self.escrowID=btcaddress
        
        #get the public list of escrows for propagation to RE
        self.escrowList = self.getEscrowList()
        
        #this  needs to be persisted as it contains
        #state information - in order to accept requests involving two parties,
        #the escrow needs to keep a record of earlier requests downloaded
        #from the MQ. The format is a list of lists, each inner list having
        #a key,message pair [k,m]
        self.requestStore=[]
        
        d = os.path.join(g("Directories","escrow_base_dir"),"multisig_store")
        p = g("Escrow","escrow_pubkey")
        #initialise multisig
        multisig.initialise(p,d)        
        
    
    def run(self,escrowRole='cne'):
        #the main loop to be called for the daemon meaning we're
        #listening for messages/requests/instructions from useragents.
        if escrowRole=='re':
            self.runRE()
            return
        elif escrowRole != 'cne':
            shared.debug(0,["Error! Role must be cne or re"])
            exit(1)
        
        while True:
            
            #deal with transactions
            self.takeAppropriateActions() 
            
            msg = self.getSingleMessage(5)
            if not msg:
                shared.debug(0,["Got nothing, waiting.."])
                continue
            
            k,m = msg.items()[0]
            txID, requester = k.split('.')
            
            if 'CNE_SIGNED_CONTRACT:' in m:
                verdict,data,contract = self.receiveContractCNE([k,m])
                self.sendContractVerdictCNE(verdict,data,contract)
                continue
    
    def getMultisigAddress(self, tx, epk):
        multisig.escrow_pubkey = epk
        bpk = tx.getCtrprtyPubkey(True)
        spk = tx.getCtrprtyPubkey(False)
        return multisig.createMultisigRaw([epk,bpk,spk])
        

    def processNewTxRE(self,msg):
        
        txHash,sender = msg[0].split('.')
        txString,buyerSig,sellerSig,escrowSig,btcTxhash = \
            ':'.join(msg[1].split(':')[1:]).split('|')
        
        print txString
        print buyerSig
        print sellerSig
        print btcTxhash
        
        #shared.debug(2,["We received a transaction string:",txString])
        #instantiate the transaction
        tx = pickle.loads(txString)
        if tx.uniqID() != txHash:
            shared.debug(0,["Alert: transaction object passed with inconsistent hash, given",txHash,"should be:",tx.uniqID()])
            self.sendMessage('RE_CNE_TX_REJECT_RECEIPT:',recipientID=sender,txID=tx.uniqID())
            return None
        #initiate the new multisig address for this transaction
        tx.msigAddr = self.getMultisigAddress(tx,g("Escrow","escrow_pubkey"))
        
        #allow us to keep track of where the deposits are (fees also collected here) 
        tx.depositHash = btcTxhash       
        
        #permanent record of identity of CNE
        tx.CNE = sender
        
        #validate the signatures
        for i,j in zip([buyerSig,sellerSig,escrowSig],[tx.buyer,tx.seller,sender]):
            testaddress = multisig.pubtoaddr(multisig.ecdsa_recover(tx.contract.getContractTextOrdered(),i))
            shared.debug(4,["Recovery produced this address:",multisig.pubtoaddr(testaddress)])
            if not testaddress == j:
                shared.debug(0,["Alert: this transaction is not correctly signed by",j,"- ignoring"])
                self.sendMessage('RE_CNE_TX_REJECT_RECEIPT:',recipientID=sender,txID=tx.uniqID())
                return None
            else:
                shared.debug(1,["Correct signature from:",j])
        
        #add the transaction to the persistent store
        #at this point, a valid transaction has been initialised but not funded in any way.
        self.transactionUpdate(tx=tx,new_state=400)
        
        #send back confirmation message (on THIS message queue)
        self.sendMessage('RE_CNE_TX_CONFIRM_RECEIPT:',recipientID=sender,txID=tx.uniqID())
   
   
    def runRE(self):
        
        #transactions that are in temporary wait states on system
        #startup should re-instantiate their waiting threads
        self.checkForRestartActions()
        
        while True:
            
            #all autonomous actions (e.g. checking for deposits)
            #are done here before getting external instructions
            self.takeAppropriateActions()
            
            msg = self.getSingleMessage(5)
            
            if not msg:
                shared.debug(0,["Got nothing, waiting.."])
                continue
            
            k,m = msg.items()[0]
            txID, requester = k.split('.')            
            
            #special message: instantiating a transaction transfer from the CNE
            if 'CNE_RE_TRANSFER' in m:
                self.processNewTxRE([k,m])
                continue
            
            elif 'VERIFICATION_FAILURE' in m:
                shared.debug(0,["Critical error: the agent didn\'t recognise our signature"])
                
            elif 'RE_SELLER_DEPOSIT:' in m:
                #wait for completion of deposit transfer
                tx = self.getTxByID(txID)
                
                #deal with repeat messages which may occur due to statelessness here
                if tx.sellerFundingTransactionHash:
                    if tx.sellerFundingTransactionHash == m.split(':')[1]:
                        #means we already have this information; ignore it
                        continue
                    else:
                        shared.debug(0,["Serious error - seller claims \
                        to have deposited into both",tx.sellerFundingTransactionHash,\
                                                    "and",m.split(':')[1]])
                                     
                if tx.state != 500:
                    shared.debug(0,["Transaction",txID,\
                                    "is not ready for seller deposit. Doing nothing"])
                    continue
                
                tx.sellerFundingTransactionHash=m.split(':')[1]
                
                amts = int(tx.contract.text['mBTC Amount'])
                checkThread = threading.Thread(\
                    target=self.checkBalanceWithTimeout,\
                    args=[tx,60*60,tx.msigAddr,tx.seller,amts,\
                          501,503,tx.sellerFundingTransactionHash])
                checkThread.setDaemon(True)
                checkThread.start()
                
            #check: is the request asking for information only?
            elif 'RE_TRANSACTION_SYNC_REQUEST:' in m:
                self.sendTransactionSynchronization([k,m])
                continue            
            
            elif 'RE_BANK_SESSION_START_REQUEST:' in m:
                if self.getTxByID(txID).buyer != requester:
                    self.sendRejectionMessage(txID,requester,m)
                self.processBankSessionStartRequest([k,m])
                continue
            
            elif 'RE_BANK_SESSION_START_READY:' in m:
                if self.getTxByID(txID).seller != requester:
                    self.sendRejectionMessage(txID,requester,m)
                    continue
                self.transactionUpdate(full=False,txID=txID,tx=None,new_state=601)
                continue
            
            elif 'RE_BANK_SESSION_ENDED:' in m:
                if self.getTxByID(txID).buyer != requester:
                    self.sendRejectionMessage(txID,requester,m)
                else:
                    self.cleanUpBankSession([k,m])
                continue
            
            elif 'RE_FIAT_RECEIPT_ACKNOWLEDGE:' in m:
                sig = m.split(':')[1]
                self.releaseFunds(self.getTxByID(txID),True,sig)
                
            ##the message is about a transaction; find it in the db:
            #tx = self.getTxByID(k.split('.')[0])
            #if (not tx) and ('TRANSACTION_REQUEST' not in m):
                #self.sendMessages(messages={'0.'+self.escrowID:\
                #'REQUEST_REJECTED:0,No such transaction'},recipientID=requester)
                #continue
                    
            #check that request asks for a valid transition
            #if tx:
                #if int(m.split(':')[1].split(',')[0]) not in shared.vtst[tx.state]:
                    #self.sendMessages(messages={txID+'.'+self.escrowID:\
                    #'REQUEST_REJECTED:'+str(tx.state)+',You cannot do that.'},\
                                      #recipientID=requester)
                    #continue
            
            # from here we know that the requester has asked to do
            # something legal to one of its transactions
            # This is effectively a switch/case situation.
            # may look into a more Pythonic way of doing it later TODO
            #if 'TRANSACTION_REQUEST' in m:
                #self.processTransactionRequest([k,m]) 
                #continue
            
            #elif 'TRANSACTION_ABORT' in m:
                ##TODO: self.abortTransaction([k,m])
                #continue
                
            #elif 'DISPUTE_L1_REQUEST' in m:
                #self.requestSSLHashes([k,m])
                #continue
                
            #elif 'SSL_DATA_SEND' in m:
                #self.receiveSSLHashes({k:m})
                #continue
            
            #elif 'DISPUTE_L2_SEND_SSL_KEYS' in m:
                #self.receiveSSLKeysAndSendHtml([k,m])
                #continue      
    
    
    def releaseFunds(self,transaction,toBuyer,sig):
        '''Provide signature for multisig release to buyer
        if 'toBuyer' is true then send tx to network
        Also return deposit to buyer and seller
        TODO: if toBuyer is false, release to seller 
        '''
        #construct all pubkeys:
        pubBuyer = transaction.getCtrprtyPubkey(True)
        pubSeller = transaction.getCtrprtyPubkey(False)
        pubEscrow = g("Escrow","escrow_pubkey") #this config is fixed on the escrow        
        receiver = transaction.buyer if toBuyer else transaction.seller
        sig2 = multisig.createSigForRedemptionRaw(pubEscrow, pubBuyer, pubSeller,\
                                                  transaction.sellerFundingTransactionHash,\
                                                 receiver)
        
        pubs = [pubBuyer,pubSeller,pubEscrow]
        #for now, the sig array has ONE element, corresponding to the
        #seller funding transaction hash
        #TODO: add another 1/2 transactions for deposit redemption
        sigArray = [[[sig,sig2],[pubSeller,pubEscrow]]]
        multisig.broadcastToNetworkRaw(sigArray,pubs,transaction.sellerFundingTransactionHash,\
                                      receiver)
        shared.debug(0,["Sent the bitcoins to the buyer; transaction completed successfully!"])
        self.transactionUpdate(tx=transaction,new_state=700)
        
        
    def sendRejectionMessage(self,txID,requester,m):
        self.sendMessage('MESSAGE_REJECTED:'+m,recipientID=requester,txID=txID)
    
    def startRandomEscrowChoice(self,txhash):
        #first upgrade transaction. then notify counterparties.
        #then take timestamp for 1 or 2 minutes after deposits confirmed.
        #read from NIST beacon. convert to small rand in range.
        #message to counterparties and RE of choice.
        
        #mark the waypoint time. This time must be *after* the
        #arrival of both deposits; this is causally guaranteed by the protocol
        #note that this is not yet perfect TODO - we either change it
        #or somehow guarantee synchronisation between client and server
        waypoint = int(time.time())
        
        tx = self.getTxByID(txhash)
        self.transactionUpdate(full=False,txID='',tx=tx,new_state=206)
        m = 'CNE_RE_CHOICE_STARTED:'+str(waypoint)
        for recipient in [tx.buyer,tx.seller]:
            self.sendMessage(m,recipientID=recipient,txID=txhash)
        
        #get public random number
        publicRandomMax=1000000
        timestamp,publicRandom = shared.get_public_random(publicRandomMax)
        
        numEscrows = len(self.escrowList)
        chosenEscrow = int(math.floor((numEscrows/publicRandomMax)*publicRandom))
        
        shared.debug(0,["We chose escrow:",chosenEscrow,"at time:",timestamp])
        
        #TODO hack for testing, remove this
        chosenEscrow=1        
        
        #generate multisig address on remote escrow
        epk = self.escrowList[chosenEscrow]['pubkey']
        REMultisigAddr = self.getMultisigAddress(tx,epk)
        shared.debug(0,["Generated multisig was: ", REMultisigAddr])
               
        #We include the escrow pubkey in the message so as to confirm
        #the RE identity in case of some error syncing the escrow table
        m = 'CNE_RE_CHOSEN:'+'|'.join([self.escrowList[chosenEscrow]['id'],tx.uniqID(),\
                                       tx.contract.getContractText(),str(epk),REMultisigAddr])
        for recipient in [tx.buyer,tx.seller]:
            self.sendMessage(m,recipientID=recipient,txID=tx.uniqID())
        paidAmount,btcTxhash = self.sendCoinsToRE(txhash,REMultisigAddr)
        
        tx.depositHash = btcTxhash
        tx.chosenRE=chosenEscrow 
        
        #update the transaction state
        self.transactionUpdate(full=False,txID=tx.uniqID(),tx=None,new_state=300)                
        self.transferTxToRE(tx,chosenEscrow)
        
    def transferTxToRE(self,tx,chosenEscrow):
        #send a message to the chosen escrow
        #this message contains the full transaction object
        transaction_string = pickle.dumps(tx)
        buyerSig = tx.contract.getSignature('buyer')
        sellerSig = tx.contract.getSignature('seller')
        txt,escrowSig = multisig.signText(self.uniqID(),tx.contract.getContractTextOrdered())
        m = 'CNE_RE_TRANSFER:'+'|'.join([transaction_string,buyerSig,\
                                         sellerSig,escrowSig,tx.depositHash])
        
        #TODO: remote connection will need to be setup, for testing on one MQ
        #Hack for testing: set chosen escrow to the "other"
        chosenEscrow=1
        self.sendMessage(m,recipientID=self.escrowList[chosenEscrow]['id'],txID=tx.uniqID())
        #once transaction is confirmed received, we update its state so as not to send it again
        msg = self.getSingleMessage(20)
        a,b = msg.keys()[0].split('.')
        if not msg or b != self.escrowList[chosenEscrow]['id'] or tx.uniqID() != a:
            #we didn't receive a response in 20 seconds
            return False
        else:
            if 'RE_CNE_TX_CONFIRM_RECEIPT' in msg.values()[0]:
                #this is the final state of the transaction on the contract negotiation side
                self.transactionUpdate(full=False,txID=tx.uniqID(),new_state=301)
                return True
            elif 'RE_CNE_TX_REJECT_RECEIPT' in msg.values()[0]:
                shared.debug(0,["Warning, transaction",tx.uniqID(),"was not accepted by chosen Escrow",self.escrowList[chosenEscrow]['id']])
                #do nothing here; we need to send again
                #TODO what kind of rejection? parse "reason" field?
                return False
            else:
                raise Exception("Random escrow sent unrecognised message type")
            
        
    def sendCoinsToRE(self,txhash,REMultisigAddr):
        #new version 7 Jan: much simpler just send the unspent outputs from
        #the counterparties directly to the new multisig on the RE
        print "About to send to:",REMultisigAddr," with txhash:",txhash
        tx = self.getTxByID(txhash)
        return multisig.spendUtxos(self.uniqID(),\
                            self.uniqID(),REMultisigAddr,[tx.buyer,tx.seller])
        
        
        
    def sendDepositTimeout(self,txid):
        temptx = self.getTxByID(txid)
        for r in [temptx.buyer,temptx.seller]:
            self.sendMessage('CNE_DEPOSIT_TIMEOUT:',recipientID=r,txID=txid)
        #just delete the transaction; no money has changed hands
        #TODO: not quite! any amounts paid less than the required have
        #to be rolled back!
        #edited 20 Jan; just let the transaction stay in default state 207/208
        #self.transactionUpdate(full=False,txID=txid,tx=None,new_state='')
            
    def processTimeOut(self,tx):
        #we know that transaction tx ran past its deadline for something
        #send the cancellation/penalty message to the relevant
        #counterparties, make payments if necessary and reset tx state
        
        if tx.state == 203:
            for c in [tx.buyer,tx.seller]:
                self.sendMessage('CNE_DEPOSIT_TIMEDOUT:',recipientID=r,txID=tx.uniqID())
            #we must also reverse any payments to the senders TODO
            #now remove the transaction entirely as it has been aborted
            self.transactionUpdate(full=False,txID=tx.uniqID(),tx=None,new_state='')
            return
        #add code for later timeouts here: TODO   
        elif tx.state:
            return
        else:
            return
        
    def sendContractVerdictCNE(self,verdict,reason,contract):
        #get the IDs of the two counterparties
        buyer = contract.text['Buyer BTC Address']
        seller = contract.text['Seller BTC Address']
        txid = contract.textHash

        m = 'CNE_CONTRACT_SIG_FAILED:' if not verdict else 'CNE_CONTRACT_SUCCESS:'
        if verdict:
            multisig.msd = os.path.join(self.baseDir,"multisig_store")
            txt,sig = multisig.signText(self.uniqID(),contract.getContractTextOrdered())
            contract.sign(multisig.pubtoaddr(g("Escrow","escrow_pubkey")),sig)
        for a in [buyer,seller]:
            if not verdict:
                ma = m+reason
            else:
                ma = m+'|'.join([reason,contract.getContractText(),sig])
            self.sendMessage(ma,recipientID=a,txID=txid)
        #persist a new transaction object if it was accepted
        if verdict:
            tx = Transaction(contract)
            tx.CNEDepositAddr=reason
            tx.signatureCompletionTime=int(time.time())
            self.transactionUpdate(full=False,txID='',tx=tx,new_state=203)
            #set the deadline for deposit
            #need to start checking the balance; spawn a thread
            sendingAddresses = [tx.buyer,tx.seller]
            amts = [tx.contract.getTotalFees('buyer'),tx.contract.getTotalFees('seller')]
            receivingAddr = self.uniqID()
            requestedState = 206
            failedState = 207
            checkThread = \
            threading.Thread(target=self.checkBalanceWithTimeout,\
            args=[tx,60*60,receivingAddr,sendingAddresses,amts,requestedState,failedState])
            checkThread.daemon=True
            checkThread.start()            
            
    
    def receiveContractCNE(self,msg):
        '''acting as CNE, the escrow can receive a doubly-signed
        contract at any time from any party. After verifying that the signatures are valid, and that the deposits 
        are specified correctly in the contract, the address
        for deposits is reported and the contract signed for the third time by the escrow.
        Messages sent to both parties giving them a deadline for deposit. '''       
        sender = msg[0].split('.')[1]
        #this special message is delimited by |
        allContractDetails = ':'.join(msg[1].split(':')[1:]).split('|')
        
        #the contract is in json format
        contractDetails = allContractDetails[0]
        tmpContract = Contract.Contract(json.loads(contractDetails))
        pubs = {}
        for s in allContractDetails[1:]:
            tmpPub = multisig.ecdsa_recover(tmpContract.getContractTextOrdered(),s)
            ad = multisig.pubtoaddr(tmpPub)
            shared.debug(2,["\n recovery produced this address: ",ad,"\n"])
            tmpContract.signatures[ad]=s
            #store the pubkeys for later use
            pubs[ad]= tmpPub
        
        #immediately check for 2 signatures; otherwise dump immediately
        if len(allContractDetails) != 3:
            return (False,'Not a valid and fully signed contract, ignoring',tmpContract)        
        
        #now the temporary contract object is fully populated; 
        #we can check the signatures match the IDs in the contract
        for k,v in tmpContract.signatures.iteritems():
            if k not in [tmpContract.text['Buyer BTC Address'],tmpContract.text['Seller BTC Address']]:
                shared.debug(1,['Error: signature',v,'from',k,'was invalid'])
                return (False,'Invalid contract signature',tmpContract)
        
        #need to check that the proposed deposits follow the business rules
        verdict,reason = self.checkBusinessRulesCNE(tmpContract)
        if not verdict: return (verdict, reason,tmpContract)
        
        #removed for now.
        #now we're happy that the contract is valid we build the dep multisig
        #multisig.initialise(g("Escrow","escrow_pubkey"),g("Directories","escrow_base_dir"))
        #for a,p in pubs.iteritems():
            #multisig.store_share(p,a)
        #msigaddr, mscript = multisig.create_multisig_address(*pubs.keys())
        
        return (True,multisig.pubtoaddr(g("Escrow","escrow_pubkey")),tmpContract)     
    
    def checkBalanceWithTimeout(self,tx,timeout,\
                                 receivingAddr,sendingAddresses,\
                                 amts,requestedTxState=None,failedTxState=None,txh=None):
        '''waits to see new transactions on the blockchain with required
        payments.
        If no payment before timeout minutes, or insufficient payments
        then returns with transaction tx updated to state failedTxState.
        If txh is specified, we are looking for a specific
        payment from one payer, with transaction hash txh.
        In this case 'amts' is actually just one amount to be paid
        and 'sendingAddresses' is just one sending address.
        If txh is not specified, we are looking for the amounts
        listed in amts paid to the receiving address by each sender
        in sendingAddresses.
        In case of success, the transaction is updated 
        to new state requestedTxState (assuming it follows vtst rules)
        All transaction updates use tdbLock lock for thread safety.
        '''
        shared.debug(2,["Starting a balance checking thread with these parameters:",\
                        "receiving address:",receivingAddr,\
                        "sending addrfess:",sendingAddresses,\
                        "amts:",amts,\
                        "requested state:",requestedTxState,\
                        "failed state:",failedTxState,\
                        "tx hash:",txh])
        
        startTime = int(time.time())
        while True:
            time.sleep(8)
            if startTime+timeout<int(time.time()):
                self.transactionUpdate(tx=tx,new_state=failedTxState)
                return  
            else:
                if not txh:
                    utxos=[]
                    for s in sendingAddresses:
                        u,t = multisig.getUtxos(receivingAddr,s)
                        utxos.append([u,t])
                    flag=True
                    for i,amt in enumerate(amts):
                        if amt > utxos[i][1]:
                            flag=False
                    if flag:
                        self.transactionUpdate(tx=tx,new_state=requestedTxState)
                        return 
                else:
                    u,t = multisig.getUtxos(receivingAddr,sendingAddresses)
                    if t==0:
                        continue
                    for x in u:
                        if x['output'].split(':')[0] == txh:
                            if amts > x['value']:
                                shared.debug(0,\
                                ["Claimed amount spent in transaction:",txh,\
                                 "was not sufficient. Was:",x['value'],"should be:",amts])
                                #TODO: partial payment total rewind?
                                self.transactionUpdate(tx=tx,new_state=failedTxState)
                                return
                            else:
                                self.transactionUpdate(tx=tx,new_state=requestedTxState)
                                return
                                
                        
    #are the monetary amounts valid?
    def checkBusinessRulesCNE(self,contract):
        #all fees parse from btc amount, fiat is ignored
        btc = float(contract.text['mBTC Amount'])
        bd = float(contract.text['Buyer Deposit Fee'])
        sd = float(contract.text['Seller Deposit Fee'])
        bf = float(contract.text['Buyer Escrow Fee'])
        sf = float(contract.text['Seller Escrow Fee'])
        req_dep = float(g("Escrow","escrow_CNE_deposit"))
        req_txfp = float(g("Escrow","escrow_tx_fee_percent"))
        
        #check the deposit fee
        if bd < req_dep or sd < req_dep:
            return (False,'Deposit to escrow is required to be at least '+str(req_dep))
        
        #check the transaction fees
        if bf < btc * req_txfp * 0.01 or sf < btc * req_txfp * 0.01:
            return (False,'Transaction fees are required to be at least '+str(req_txfp)+'\% of the total BTC amount of the transaction.')
        
        return (True, 'All fees are valid, contract accepted.')
    
    def checkForRestartActions(self):
        
        for t in self.transactions:
            #little hack for bank session testing
            if t.state in [600,601,603]:
                self.transactionUpdate(tx=t,new_state=501) 
            elif t.state in [700]:
                self.transactionUpdate(tx=t,new_state=602)
            #TODO are we sure we want to do this?
            elif t.state==402:
                self.transactionUpdate(tx=t,new_state=400)
            elif t.state==500 and t.sellerFundingTransactionHash:
                amts = int(t.contract.text['mBTC Amount'])
                checkThread = threading.Thread(\
                    target=self.checkBalanceWithTimeout,\
                    args=[t,60*60,t.msigAddr,t.seller,amts,\
                          501,503,t.sellerFundingTransactionHash])
                checkThread.setDaemon(True)
                checkThread.start()                
                
    def takeAppropriateActions(self):
        
        for t in self.transactions:
                
            if t.state==400:
                amts=t.contract.getTotalFees('buyer')+t.contract.getTotalFees('seller')
                self.transactionUpdate(tx=t,new_state=402)
                checkThread = threading.Thread(\
                    target=self.checkBalanceWithTimeout,\
                    args=[t,60*60,t.msigAddr,t.CNE,amts,500,401,t.depositHash])
                checkThread.daemon=True
                checkThread.start()            
                
            elif t.state==300:
                #transaction is ready to be propagated to RE:
                #TODO Hacked for testing - chosenEscrow will be a transaction property
                if not self.transferTxToRE(t,chosenEscrow=1):
                    shared.debug(0,["Warning, transfer of ",\
                                    t.uniqID(),"to random escrow was unsuccessful"])
            
            elif t.state==206:
                self.startRandomEscrowChoice(t.uniqID())
            
            elif t.state==207:
                self.sendDepositTimeout(t.uniqID())
                
            elif t.state==501:
                shared.debug(0,["Success! Ready for banking"])
            
            elif t.state==700:
                for recipientID in [t.buyer,t.seller]:
                    self.sendMessage("RE_TRANSACTION_COMPLETED:", \
                                     recipientID=recipientID, txID=t.uniqID())
        
        self.transactionUpdate(full=True)
        
        
    def cleanUpBankSession(self,msg):
        #shut down the stcppipe for this run
        self.stcppipe_proc.kill()
        
        rspns=msg[1].split(':')[1].split(',')[0]
        requested_state = 602 if rspns=='y' else 603
        tx = self.getTxByID(msg[0].split('.')[0])
        
        self.transactionUpdate(tx=tx,new_state=requested_state)
        #inform the seller
        self.sendMessage('RE_BANK_SESSION_ENDED:'+rspns,\
                         recipientID=tx.seller,txID=tx.uniqID())
        
    def sendTransactionSynchronization(self,msg):
        requester = msg[0].split('.')[1]
        shared.debug(0,["Requester:",requester])
        smsg_key = '0.'+self.uniqID()
        for tx in self.transactions:
            if requester == tx.buyer or requester == tx.seller:
                self.sendMessage('RE_TRANSACTION_SYNC_RESPONSE:'\
                                 +pickle.dumps(tx),recipientID=requester,txID=tx.uniqID())
        #send a final message to mark end of list
        self.sendMessage('RE_TRANSACTION_SYNC_COMPLETE:',recipientID=requester,txID=tx.uniqID())
        
    ##for this function we use "instruction" rather than
    ##"request" because users should be able to cancel WITHOUT
    ##permission BEFORE bank session start; after that point,
    ##the transaction rollback may require permission of others
    #def abortTransaction(self,instruction):
        #response=[]
       
        ##find the transaction
        #txID,sender = instruction[0].split('.')
        #tmptx = self.getTxByID(txID)
        #if not tmptx:
            #shared.debug(0,["Error, transaction cannot be aborted,not in db"])
            #return
        #for recipient in [tmptx.buyer,tmptx.seller]:
                #self.sendMessages({txID+'.'+self.escrowID:\
    #'TRANSACTION_ABORT_ACCEPTED:400,requested by '+sender},recipientID=recipient)
        ##abort
        #self.transactionUpdate(txID=txID,new_state=400) 
                               
    ##in L2 dispute, we ask the buyer for one or more keys
    ##then we grab whatever html we can get with those keys
    ##and send them on to super escrow
    #def receiveSSLKeysAndSendHtml(self, msg):
        ##get the transaction first
        #tx = self.getTxByID(msg[0].split('.')[0])
        #shared.debug(0,["Received these keys:",msg])
        ##grab the keys from the message and turn them into a single 
        ##keyfile for use by tshark
        #sslkeylines = msg[1].split(':')[1].split(',')[1:]
        #keydir = os.path.join(g("Directories","escrow_base_dir"),\
                #'_'.join(['escrow',tx.uniqID(),'banksession']))
        #kf = os.path.join(keydir,'user_sent.keys')
        #with open(kf,'w') as f:
            #for kl in sslkeylines:
                #f.write(kl)
            #f.close()
        
        ##keys have been committed to disk:
        #self.transactionUpdate(tx=tx,new_state=801)
        
        ##now we can use user_sent.keys as our input to tshark
        #stcpdir=os.path.join(keydir,'stcplog')
        #merged_trace = os.path.join(stcpdir,'merged.pcap')
        #sharkutils.mergecap(merged_trace,stcpdir,dir=True)
        #htmlarray = sharkutils.get_all_html_from_key_file(capfile=merged_trace,\
                                                          #keyfile=kf)
        ##for user security, delete keys immediately ? TODO
        
        ##send html to super escrow for adjudication TODO
        #shared.debug(0,["Sending html to super escrow for this transaction"])
        #m_k = tx.uniqID()+'.'+self.escrowID
        #for a in htmlarray:
            #self.sendMessages({m_k:bytearray('DISPUTE_L2_SEND_HTML_EVIDENCE:')+\
                               #a},recipientID=self.superEscrow)
            
        #self.transactionUpdate(tx=tx,new_state=802)
        
    ##This function should be called when any TRANSACTION_REQUEST message
    ##is sent. It checks for the existence of another message of the 
    ##same type with the same parameters. If found, and the requests are
    ##deemed compatible, it will send out
    ##a transaction accepted message to both parties.
    #def processTransactionRequest(self, request):
        #response=[]
        
        #requester = request[0].split('.')[-1]
        
        ##state management
        #requested_state = int(request[1].split(':')[1].split(',')[0])
        
        ##buyerID,sellerID,amount,price,currency
        #req_msg_data = request[1].split(':')[1].split(',')[1:]
        
        ##sanity check: don't go any further unless the transaction involves
        ##the requester:
        #if not requester in req_msg_data[0:2]:
            #return
        
        #tmptx = Transaction(*req_msg_data)
        
        #existing = self.getTxByID(tmptx.uniqID())
        
        #if existing:
            #shared.debug(0,\
                #["Found a pre-existing transaction matching this request"])
            ##we need to validate that the financial information matches,
            ##else reject the request
            #if not existing.buyer==req_msg_data[1] and \
                #existing.seller==req_msg_data[0]:
                #response=['reject','mismatched counterparties']
            ##now we know the counterparties match; need to check the 
            ##financial part
            #if not existing.currency==req_msg_data[4]:
                #response= ['reject','wrong currency']
            #elif not existing.amount==req_msg_data[2]:
                #response= ['reject','mismatched bitcoin amount']
            ##TODO: use a "mid" approach for prices
            #elif not existing.price==req_msg_data[3]:
                #response= ['reject','mismatched prices']
            #else:
                #response=['accept']
            
            #if response[0]=='reject':
                #message={'0.'+self.escrowID:'TRANSACTION_REJECTED:'\
                         #+str(existing.state)+','+response[1]}
                #for recipientID in req_msg_data[0:1]:
                    #self.sendMessages(message,recipientID)
                
            ##check state machine rules; if valid, initialize
            #if (requested_state ==300 and existing.state == 202) or \
                #(requested_state==300 and existing.state == 201):
                ##all as normal; initialise
                #existing.initialize()
                #self.transactionUpdate(tx=existing,new_state=300)
                #message={existing.uniqID()+'.'+self.escrowID:'TRANSACTION_ACCEPTED:'\
                         #+','.join([str(existing.state),existing.buyer,\
                        #existing.seller,existing.amount,existing.price,\
                        #existing.currency,str(existing.creationTime)])}
                #for recipientID in req_msg_data[0:2]:
                    #self.sendMessages(message,recipientID)
            #else:
                #shared.debug(0,["error; seems to be in a corrupted state?"])
       
        #else:
            ##there is no pre-existing transaction request; set this one
            #requester_is_buyer = True if requester==req_msg_data[0] else False
            #tmptx.state = 201 if requester_is_buyer else 202
            #self.transactions.append(tmptx)
            #self.transactionUpdate(full=True)
            
                    
    def processBankSessionStartRequest(self,request):
        '''In response to buyer's request, update the transaction
        state and set up the ssh/stcp pipe for the proxying'''
        
        #ID of requesting agent is after the .
        requester = request[0].split('.')[1]
        
        tx = self.getTxByID(request[0].split('.')[0])
        
        self.transactionUpdate(full=False,tx=tx,new_state=600)
        
        #next need to request the session to the seller
        self.sendMessage('RE_BANK_SESSION_START_REQUEST:', recipientID=tx.seller, txID=tx.uniqID())
        #we'll block here, but not for long as after all we're checking availability!
        msg = self.getSingleMessage(timeout=5)
        if not msg or 'RE_BANK_SESSION_START_ACCEPTED' not in msg.values()[0]:
            self.sendMessage('RE_BANK_SESSION_START_REJECTED:seller unavailable',\
                             recipientID=tx.buyer, txID=tx.uniqID())
        
        else:
            self.transactionUpdate(full=False, tx=tx, new_state=601)
            #seller is ready; set up pipes and then let buyer know
            
            #TODO how to make sure we start clean (no old stcppipe procs)?
            if self.stcppipe_proc:
                self.stcppipe_proc.kill()
            #time.sleep(2)
            #prepare file storage on escrow for logs, start stcppipe
            runID='_'.join(['escrow',tx.uniqID(),'banksession'])
            d = shared.makedir([g("Directories","escrow_base_dir"),runID])
            stcpd = shared.makedir([d,'stcplog'])
            self.stcppipe_proc=shared.local_command(\
                [g("Exepaths","stcppipe_exepath"),'-d',stcpd, '-b','127.0.0.1',\
                 g("Escrow","escrow_stcp_port"),g("Escrow","escrow_input_port")],bg=True)
            
            self.sendMessage('RE_BANK_SESSION_START_ACCEPTED:', \
                             recipientID=tx.buyer,txID=tx.uniqID())
            
         
        
    ##request ssl hashes from counterparties, wait for a return
    ##and check against escrow's own record. Adjudicate on that basis.
    #def requestSSLHashes(self,request):
        ##first fire off request for hashes from both counterparties.
        ##even if they are online this may take some time. State is maintained
        ##in the transaction.
        #txID, requester = request[0].split('.')
        #tx = self.getTxByID(txID)
        
        ##immediately set as disputed
        #self.transactionUpdate(txID=txID,new_state=700)
        
        ##need the ssl data from the counterparties to resolve the dispute
        #counterparty = tx.buyer if tx.buyer != requester else tx.seller
        #for recipient in [requester, counterparty]:
            #msg={txID+'.'+self.escrowID:','.join([str(tx.state),'SSL_DATA_REQUEST'])}
            #self.sendMessages(msg,recipient)
        
    ##on receipt of hashes, match them with a transaction
    ##check that it's currently in the correct dispute state; store persistently
    ##finally, trigger adjudication if both sets have been received
    #def receiveSSLHashes(self,msg):
        
        #response=[]
        
        #shared.debug(0,["starting receiveSSLHashes"])
        #txID, sender = msg.keys()[0].split('.')
        #shared.debug(0,["set the sender to : ",sender])
        
        ##establish in advance which transaction this data refers to
        #tmptx = self.getTxByID(txID)
        #if not tmptx:
            #shared.debug(0,["Serious error: ssl data was sent for a transaction"\
                            #" not stored on the escrow!"])
            #exit(1)
        
        ##check the role as behaviour depends on it
        #role = tmptx.getRole(sender)
        #requested_state = int(msg.values()[0].split(':')[1].split(',')[0])
        #sent_data = msg.values()[0].split(':')[-1]
        
        #if role=='buyer':
            #hashes_string,magic_string=sent_data.split('^')
            ##v important: magic_hashes very likely to be null
            #tmptx.buyerHashes = hashes_string.split(',')[1:]
            #tmptx.magicHashes = magic_string.split(',')
        #else:
            #tmptx.sellerHashes = sent_data.split(',')[1:]
            
        #if (role=='buyer' and tmptx.state==702) or \
            #(role=='seller' and tmptx.state==701):
            #self.transactionUpdate(tx=tmptx,new_state=requested_state)
            ##send confirmation of receipt:
            #rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED:'+str(requested_state)}
            #self.sendMessages(rmsg,sender)
            ##adjudicate
            #self.adjudicateL1Dispute(tmptx)
            
        #elif tmptx.state==700:
            #ns = 701 if role=='buyer' else 702
            #self.transactionUpdate(tx=tmptx,new_state=ns)
            ##send confirmation of receipt:
            #rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED:'+str(ns)}
            #self.sendMessages(rmsg,sender)
        #else:
            #shared.debug(0,["Serious error, shouldn't get here"])
            #return False
        
                
    ##logic: if one of three is inconsistent, the third party is lying
    ##if all three are consistent, raise dispute level to super-escrow
    ##(also if all three are inconsistent, hopefully this won't happen!!)
    #def adjudicateL1Dispute(self,transaction):
        
        ##TODO: actual bitcoin movements!
        
        ##first step: generate our own ssl hash list using the NetworkAudit module
        #my_hash_list = self.getHashList(transaction)
        #stcpdir = os.path.join(g("Directories","escrow_base_dir"),\
                    #'_'.join(['escrow',transaction.uniqID(),"banksession"]),\
                        #"stcplog")
        #hashes_to_ignore = sharkutils.get_hashes_to_ignore(stcpdir,\
                                                    #transaction.magicHashes)
        #shared.debug(0,["Hashes to ignore are:",hashes_to_ignore])
        ##now we can basically perform set operations to come to a decision
        
        ##first subtract ignorable hashes from all hashlist records
        #my_hash_list = set(my_hash_list)-set(hashes_to_ignore)
        #buyer_hash_list = set(transaction.buyerHashes)-set(hashes_to_ignore)
        #seller_hash_list = set(transaction.sellerHashes)-set(hashes_to_ignore)
        
        #buyer = transaction.buyer
        #seller = transaction.seller
        
        #if not my_hash_list:
            ##in this failure case, elevate dispute
            #msg = {transaction.uniqID()+'.'+self.escrowID:\
                #'DISPUTE_L1_ADJUDICATION_FAILURE:'+str(transaction.state)+\
                #',escrow hash list not found for this transaction'}
            ##leave it in dispute for now
            #for recipient in [buyer,seller,self.superEscrow]:
                #self.sendMessages(msg,recipient)
        
         ##second step: comparison of three hash lists
         ##third step: send adjudication messages to both counterparties
        #if (buyer_hash_list == my_hash_list) and seller_hash_list != my_hash_list:
            #self.transactionUpdate(tx=transaction,new_state=704)
            #msg={transaction.uniqID()+'.'+self.escrowID:\
                #'DISPUTE_L1_ADJUDICATION:'+str(transaction.state)+\
                #',awarded to buyer, seller\'s ssl record is invalid'}
            ##insert bitcoin transfer TODO
            #for recipient in [buyer,seller]:
                #self.sendMessages(msg,recipient)
                
        #elif (buyer_hash_list != my_hash_list) and seller_hash_list == my_hash_list:
            #self.transactionUpdate(tx=transaction,new_state=705)
            #msg={transaction.uniqID()+'.'+self.escrowID:\
                #'DISPUTE_L1_ADJUDICATION:'+str(transaction.state)+\
                #',awarded to seller, buyer\'s ssl record is invalid'}
            ##insert bitcoin transfer TODO
            #for recipient in [buyer,seller]:
                #self.sendMessages(msg,recipient)
        
        ##TODO: check escrow or not?
        #elif buyer_hash_list == seller_hash_list: 
            #self.transactionUpdate(tx=transaction,new_state=706)
            #msg={transaction.uniqID()+'.'+self.escrowID:\
                #'DISPUTE_L1_ADJUDICATION_FAILURE:'+str(transaction.state)+\
                #',ssl data is consistent - dispute escalated to super escrow'}
            #for recipient in [buyer,seller,self.superEscrow]:
                #self.sendMessages(msg,recipient)
                
        #else:
            #self.transactionUpdate(tx=transaction,new_state=706)
            #msg = {transaction.uniqID()+'.'+self.escrowID:\
                #'DISPUTE_L1_ADJUDICATION_FAILURE:'+str(transaction.state)+\
                #',all three ssl data records are inconsistent'}
            ##This is a catastrophic failure of the system; TODO prob. escalate
            #for recipient in [buyer,seller,self.superEscrow]:
                #self.sendMessages(msg,recipient)
                
        ##v. helpful for debugging and testing
        #shared.debug(0,["Mismatches between buyer and seller:", \
        #set(buyer_hash_list).symmetric_difference(set(seller_hash_list))])
        #shared.debug(0,["Mismatches between buyer and escrow:", \
        #set(buyer_hash_list).symmetric_difference(set(my_hash_list))])
        #shared.debug(0,["Mismatches between seller and escrow:", \
        #set(my_hash_list).symmetric_difference(set(seller_hash_list))]) 
               
    
    def providePort(self):
        #TODOcode to provide a currently unused port for concurrent transactions
        #this seems like it could be tricky
        #for now, static
        return g("Escrow","escrow_input_port")
    
