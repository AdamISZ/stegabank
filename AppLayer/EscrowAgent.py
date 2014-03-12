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
        
        #log in to message queue server
        Msg.instantiateConnection(un=g("Agent","agent_rabbitmq_user"),pw=g("Agent","agent_rabbitmq_pass"))
        
        #hardcoded for testing TODO
        self.escrowID=btcaddress
        
        self.superID = g("Escrow","super_id")
        
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
            
            msg = self.getSingleMessage(5,prefix='CNE')
            if not msg:
                shared.debug(0,["Got nothing, waiting.."])
                continue
            
            k,m = msg.items()[0]
            txID, requester = k.split('.')
            
            if 'CNE_SIGNED_CONTRACT:' in m:
                verdict,data,contract = self.receiveContractCNE([k,m])
                self.sendContractVerdictCNE(verdict,data,contract)
                continue
            
            #TODO: this code is identical on RE and CNE;
            #how to avoid replicating?
            if 'QUERY_STATUS:' in m:
                queryee = m.split(':')[1]
                self.sendMessage('QUERY_STATUS:'+requester, recipientID=queryee) 
            
            if 'QUERY_STATUS_RESPONSE:' in m:
                rspns,ctrprty = m.split(':')[1].split(',')
                self.sendMessage('QUERY_STATUS_RESPONSE:'+rspns, recipientID=ctrprty)
                
    
    def getMultisigAddress(self, tx, epk):
        multisig.escrow_pubkey = epk
        bpk = tx.getCtrprtyPubkey(True)
        spk = tx.getCtrprtyPubkey(False)
        return multisig.createMultisigRaw(2,3,[epk,bpk,spk])
        

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
            self.sendMessage('RE_CNE_TX_REJECT_RECEIPT:',recipientID='CNE'+sender,txID=tx.uniqID())
            return None
        #initiate the new multisig address for this transaction
        tx.msigAddr,tx.mscript = self.getMultisigAddress(tx,g("Escrow","escrow_pubkey"))
        
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
                self.sendMessage('RE_CNE_TX_REJECT_RECEIPT:',recipientID='CNE'+sender,txID=tx.uniqID())
                return None
            else:
                shared.debug(1,["Correct signature from:",j])
        
        #add the transaction to the persistent store
        #at this point, a valid transaction has been initialised but not funded in any way.
        self.transactionUpdate(tx=tx,new_state=400)
        
        #send back confirmation message (on THIS message queue)
        self.sendMessage('RE_CNE_TX_CONFIRM_RECEIPT:',recipientID='CNE'+sender,txID=tx.uniqID())
   
   
    def runRE(self):
        
        #transactions that are in temporary wait states on system
        #startup should re-instantiate their waiting threads
        self.checkForRestartActions()
        
        while True:
            
            #all autonomous actions (e.g. checking for deposits)
            #are done here before getting external instructions
            self.takeAppropriateActions()
            
            msg = self.getSingleMessage(5,prefix='RE')
            
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
            
            elif 'RE_BANK_SESSION_ENDED:' in m:
                if self.getTxByID(txID).buyer != requester:
                    self.sendRejectionMessage(txID,requester,m)
                else:
                    self.cleanUpBankSession([k,m])
            
            elif 'RE_FIAT_RECEIPT_ACKNOWLEDGE:' in m:
                sig = m.split(':')[1]
                self.releaseFunds(self.getTxByID(txID),True,sig)
                
            elif 'RE_DISPUTE_REQUEST:' in m:
                transaction = self.getTxByID(txID)
                #TODO: we should allow buyer to start a dispute
                #I think, but consider.
                #if transaction.seller != requester:
                #    self.sendRejectionMessage(txID,requester,m)
                #    continue
                reasonForDispute,sig = m.split(':')[1].split('|')
                transaction.disputeReason = reasonForDispute
                self.transactionUpdate( txID=txID,new_state=800)
                self.sendMessage("RE_SSL_KEYS_REQUEST:",recipientID=transaction.buyer)
            
            elif 'RE_SSL_KEYS_SEND:' in m:
                #no attempt to restrict by transaction state;
                #the buyer may send these keys whenever he likes
                transaction = self.getTxByID(txID)
                self.receiveSSLKeysAndSendHtml([k,m])
                
            #TODO: this code is identical on RE and CNE;
            #how to avoid replicating?
            elif 'QUERY_STATUS:' in m:
                queryee = m.split(':')[1]
                self.sendMessage('QUERY_STATUS:'+requester, recipientID=queryee) 
            
            elif 'QUERY_STATUS_RESPONSE' in m:
                rspns,ctrprty = m.split(':')[1].split(',')
                self.sendMessage('QUERY_STATUS_RESPONSE:'+rspns, recipientID=ctrprty)            
    
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
        REMultisigAddr,mscript = self.getMultisigAddress(tx,epk)
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
        
        #Hack for testing: set chosen escrow to the "other"
        chosenEscrow=1
        
        self.sendMessage(m,recipientID='RE'+self.escrowList[chosenEscrow]['id'],txID=tx.uniqID())
        
        msg = self.getSingleMessage(20,prefix='CNE')
        
        if not msg:
            return False
        a,b = msg.keys()[0].split('.')
        if b != self.escrowList[chosenEscrow]['id'] or tx.uniqID() != a:
            #we have received an inappropriate message
            return False
        else:
            if 'RE_CNE_TX_CONFIRM_RECEIPT' in msg.values()[0]:
                #once transaction is confirmed received, we update its state so as not to send it again
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
        
        
        
    def sendDepositTimeout(self,txid,defaulter=None):
        '''
        This is sent when one or both parties have failed to deliver
        their deposit to the CNE after contract signing is complete.
        If defaulter is None, it means both have defaulted,
        meaning only a message is sent to mark the transaction as defunct.
        Otherwise defaulter marks the role of the defaulter and the
        other party's deposit is returned.
        '''
        tx = self.getTxByID(txid)
        
        if defaulter and defaulter not in [tx.buyer,tx.seller]:
            shared.debug(0,["Critical error: wrong argument"])
            
        defaultedList = ','.join([tx.buyer,tx.seller]) if not defaulter else defaulter
        
        for r in [tx.buyer,tx.seller]:
            self.sendMessage('CNE_DEPOSIT_TIMEOUT:'+defaultedList,recipientID=r,txID=txid)
        
        
        for a in [[tx.buyer,tx.buyerInitialDeposits],[tx.seller,tx.sellerInitialDeposits]]:
            if a[1]: #only need to spend back if there are any deposits
                #we want to spend these utxos back to the depositor, minus txfee
                shared.debug(0,["For agent:",a[0],"were refunding this:",a[1]])
                multisig.spendUtxosDirect(self.uniqID(),self.uniqID(),a[0],a[1])
            
        #rewind actions completed as necessary; make the transaction defunct
        self.transactionUpdate(tx=tx,new_state=212)
        
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
            
            #need to start checking the balance; spawn a thread for buyer AND seller
            #TODO magic number for the deposit timeouts?
            
            receivingAddr = self.uniqID()
            
            sendingAddresses= [tx.buyer]
            amts = [tx.contract.getTotalFees('buyer')]
            ctsu=[{203:204,205:206,208:210},{203:207,205:211,208:209}]
            checkBuyerThread = \
                    threading.Thread(target=self.checkBalanceWithTimeout,\
                    args=[tx,60*2,receivingAddr,sendingAddresses,amts,None,None,None,ctsu])
            checkBuyerThread.daemon=True
            checkBuyerThread.start()
            
            sendingAddresses = [tx.seller]
            amts = [tx.contract.getTotalFees('seller')]
            ctsu=[{203:205,204:206,207:211},{203:208,204:210,207:209}]
            checkThread = \
            threading.Thread(target=self.checkBalanceWithTimeout,\
            args=[tx,60*2,receivingAddr,sendingAddresses,amts,None,None,None,ctsu])
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
                                 amts,requestedTxState=None,failedTxState=None,\
                                 txh=None,ctsu=False):
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
        If ctsu is not None, (conditional transaction state update),
        it is an array with two elements each of which is a dict mapping
        from a set of possible prior transaction states to their 
        corresponding succeeding states. The first element is the transitions
        for successful payment receipt and the second for failed/timed out.
        Note that the options txh and ctsu are NOT compatible
        
        All transaction updates use tdbLock lock for thread safety.
        '''
        shared.debug(2,["Starting a balance checking thread with these parameters:",\
                        "receiving address:",receivingAddr,\
                        "sending address:",sendingAddresses,\
                        "amts:",amts,\
                        "requested state:",requestedTxState,\
                        "failed state:",failedTxState,\
                        "tx hash:",txh])
        
        txLock = threading.Lock()
        
        if ctsu and txh:
            shared.debug(0,["Critical error, cannot \
            specify transaction hash and conditional updates"])
        
        startTime = int(time.time())
        while True:
            time.sleep(4) #TODO magic number
                
            if startTime+timeout<int(time.time()):
                txLock.acquire()
                try:
                    if ctsu:
                        #update according to failure dict
                        failureDict = ctsu[1]
                        if tx.state not in failureDict.keys():
                            shared.debug(0,["Critical error, cannot update tx state,\
                            in unrecognized state:",tx.state])
                        else:
                            self.transactionUpdate(tx=tx,new_state=failureDict[tx.state])
                    else:                
                        self.transactionUpdate(tx=tx,new_state=failedTxState)
                finally:
                    txLock.release()
                    return
            else:
                if not txh:
                    utxos=[]
                    for s in sendingAddresses:
                        utxos.append(multisig.getUtxos(receivingAddr,s))
                    
                    flag=True
                    for i,amt in enumerate(amts):
                        if amt > utxos[i][1]:
                            flag=False
                    if flag:
                        if ctsu:
                            #update according to success dict
                            successDict = ctsu[0]
                            if tx.state not in successDict.keys():
                                shared.debug(0,["Critical error, cannot update tx state, in unrecognized state:",tx.state])
                            else:
                                #this code is specifically for initial deposits;
                                #TODO may need refactoring
                                role = tx.getRole(sendingAddresses[0])
                                
                                if role not in ['buyer','seller']:
                                    shared.debug(0,["Critical error, wrong role:",role])
                                if role=='buyer':
                                    tx.buyerInitialDeposits = utxos[0]
                                else:
                                    tx.sellerInitialDeposits = utxos[0]
                                    
                                self.transactionUpdate(tx=tx,new_state=successDict[tx.state])
                        else:                        
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
            elif t.state in [801]:
                self.transactionUpdate(tx=t,new_state=800)
                
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
                #successful receipt of deposits
                self.startRandomEscrowChoice(t.uniqID())
            
            elif t.state in [209,210,211]:
                #TODO: do we want to send a meaningful message? then need to
                #split this into three calls
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
                               
    
    def receiveSSLKeysAndSendHtml(self, msg):
        #get the transaction first
        tx = self.getTxByID(msg[0].split('.')[0])
        shared.debug(0,["Received these keys:",msg])
        #grab the keys from the message and turn them into a single 
        #keyfile for use by tshark
        sslkeylines = msg[1].split(':')[1].split(',')[1:]
        keydir = os.path.join(g("Directories","escrow_base_dir"),\
                '_'.join(['escrow',tx.uniqID(),'banksession']))
        kf = os.path.join(keydir,'buyer_sent.keys')
        with open(kf,'w') as f:
            for kl in sslkeylines:
                f.write(kl)
            f.close()
        
        #keys have been committed to disk:
        self.transactionUpdate(tx=tx,new_state=801)
        
        #now we can use user_sent.keys as our input to tshark
        stcpdir=os.path.join(keydir,'stcplog')
        merged_trace = os.path.join(stcpdir,'merged.pcap')
        sharkutils.mergecap(merged_trace,stcpdir,dir=True)
        htmlarray = sharkutils.get_all_html_from_key_file(capfile=merged_trace,\
                                                          keyfile=kf)
        #for user security, delete keys immediately ? TODO
        
        #send html to super escrow for adjudication TODO
        shared.debug(0,["Sending html to super escrow for this transaction"])
        m_k = tx.uniqID()+'.'+self.escrowID
        for a in htmlarray:
            self.sendMessage('DISPUTE_HTML_EVIDENCE:'+\
                               str(a),recipientID=self.superID,txID=tx.uniqID())
            
        #arbiter has been notified; final action requires human intervention
        self.transactionUpdate(tx=tx,new_state=802)
            
                    
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
        msg = self.getSingleMessage(timeout=5, prefix='RE')
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
                
    def providePort(self):
        #TODOcode to provide a currently unused port for concurrent transactions
        #this seems like it could be tricky
        #for now, static
        return g("Escrow","escrow_input_port")
    
