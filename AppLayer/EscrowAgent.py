import time
import os
import pickle
import shared
import Agent
from AppLayer.Transaction import Transaction
import NetworkAudit.sharkutils as sharkutils
import Messaging.MessageWrapper as Msg
import helper_startup as hs
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
        self.escrowID='123'
        
        #in case of escalation to human adjudication
        self.superEscrow = 'adam111'
        
        #this  needs to be persisted as it contains
        #state information - in order to accept requests involving two parties,
        #the escrow needs to keep a record of earlier requests downloaded
        #from the MQ. The format is a list of lists, each inner list having
        #a key,message pair [k,m]
        self.requestStore=[]
        
        #a list of list of hashes; same comments as for requeststore above
        self.hashStore={}
        self.magicStore={}
        
    def run(self):
        #the main loop to be called for the daemon meaning we're
        #listening for messages/requests/instructions from useragents.
        while True:
            msg = self.getSingleMessage(5)
            if not msg:
                shared.debug(0,["Got nothing, waiting.."])
                continue
            #we received at least one message: check the headers,
            #perform the appropriate action
            shared.debug(0,["We received at least one message in the main loop:",\
                            msg])
            for k,m in msg.iteritems():
            # this is effectively a switch/case situation.
            # may look into a more Pythonic way of doing it later TODO
                if 'TRANSACTION_SYNC_REQUEST' in m:
                    shared.debug(0,["Received a transaction sync request"])
                    self.sendTransactionSynchronization([k,m])
                    
                if 'TRANSACTION_REQUEST' in m:
                    shared.debug(0,["Found a transaction request in the buffer"])
                    self.processTransactionRequest([k,m]) 
                
                elif 'TRANSACTION_ABORT' in m:
                    shared.debug(0,["Found a transaction abort instruction in the buffer"])
                    self.abortTransaction([k,m])
                    
                elif 'BANK_SESSION_START_REQUEST' in m:
                    shared.debug(0,["Found a bank session start request in the buffer"])
                    self.negotiateBankSessionStartRequest([k,m])
                
                elif 'BANK_SESSION_ABORT' in m:
                    shared.debug(0,["Found a bank session abort instruction in the buffer"])
                    self.abortBankingSession([k,m])
                
                elif 'BANK_SESSION_ENDED' in m:
                    shared.debug(0,["Found a bank session ended notification in the buffer"])
                    self.cleanUpBankSession([k,m])
                    
                elif 'DISPUTE_L1_REQUEST' in m:
                    shared.debug(0,["Found a Level 1 dispute request in the buffer"])
                    self.requestSSLHashes([k,m])
                    
                elif 'SSL_DATA_SEND' in m:
                    shared.debug(0,["Found a ssl data transfer in the buffer"])
                    self.receiveSSLHashes({k:m})
                
                elif 'DISPUTE_L2_SEND_SSL_KEYS' in m:
                    shared.debug(0,["Found a ssl key delivery message in the buffer"])
                    self.receiveSSLKeysAndSendHtml([k,m])
    
    def cleanUpBankSession(self,msg):
        #shut down the stcppipe for this run
        #TODO - this is obviously incompatible with multiple sessions
        #TODO: this creates a zombie - does it matter?
        shared.local_command(['pkill', '-SIGTERM', 'stcppipe'])
        tx = self.getTxByID(msg[0].split('.')[0])
        if msg[1].split(':')[1]=='n':
            self.transactionUpdate(tx=tx,new_state=19)
        elif msg[1].split(':')[1]=='y':
            self.transactionUpdate(tx=tx,new_state=18)
            
        else:
            shared.debug(0,["Serious error, bank session completed message in",\
                            "wrong format"])
        
        #inform the seller, who may currently be confused if it didn't work
        self.sendMessages({tx.uniqID()+'.'+\
                        tx.seller:'BANK_SESSION_ENDED:'+msg[1].split(':')[1]},recipientID=tx.seller)
        
    def sendTransactionSynchronization(self,msg):
        requester = msg[0].split('.')[1]
        shared.debug(0,["Requester:",requester])
        smsg_key = '0.'+self.escrowID
        for tx in self.transactions:
            if requester == tx.buyer or requester == tx.seller:
                #build message:
                smsg = {smsg_key:'TRANSACTION_SYNC_RESPONSE:'+pickle.dumps(tx)}
                self.sendMessages(smsg,requester)
        #send a final message to mark end of list
        self.sendMessages({smsg_key:'TRANSACTION_SYNC_COMPLETE:'},requester)
        
    #for this function we use "instruction" rather than
    #"request" because users should be able to cancel WITHOUT
    #permission BEFORE bank session start; after that point,
    #the transaction rollback may require permission of others
    def abortTransaction(self,instruction):
        response=[]
        tmptx=None
        #find the transaction
        txID,recipient = instruction[0].split('.')
        if txID not in (x.uniqID() for x in self.transactions):
            response =  ['reject','invalid transaction id']
        for t in self.transactions:
            if t.uniqID()==txID:
                tmptx=t
                break
        if tmptx.state in [2,1]:
            response=['accept']
        elif tmptx.state in [0,3]:
            response=['accept',\
                      'no action - transaction is already aborted or invalid']
        else:
            #here we need to find a abort negotation protocol for in-process txs
            response=['reject','transaction is in process "\
                      +"and cannot be aborted without agreement']
        if response[0]=='accept':
            for recipient in [buyerID,sellerID]:
                self.sendMessages({txID+'.'+self.escrowID:\
                            'TRANSACTION_ABORT_ACCEPTED'},recipient)
            #abort
            self.transactionUpdate(txID=txID,new_state=3) 
            
        else:
            for recipient in [buyerID,sellerID]:
                self.sendMessages({txID+'.'+self.escrowID:\
                        'TRANSACTION_ABORT_REJECTED:'+response[1]},recipient)
                               
    #in L2 dispute, we ask the buyer for one or more keys
    #then we grab whatever html we can get with those keys
    #and send them on to super escrow
    def receiveSSLKeysAndSendHtml(self, msg):
        #get the transaction first
        tx = self.getTxByID(msg[0].split('.')[0])
        
        #grab the keys from the message and turn them into a single 
        #keyfile for use by tshark
        sslkeylines = msg[1].split(':')[1].split(',')
        keydir = os.path.join(g("Directories","escrow_base_dir"),\
                '_'.join('escrow',tx.uniqID(),'banksession'))
        kf = os.path.join(keydir,'user_sent.keys')
        with open(kf,'w') as f:
            for kl in sslkeylines:
                f.write(kl)
            f.close()
        
        #now we can use user_sent.keys as our input to tshark
        stcpdir=os.path.join(keydir,'stcplog')
        merged_trace = os.path.join(stcpdir,'merged.pcap')
        sharkutils.mergecap(merged_trace,stcpdir,dir=True)
        htmlarray = sharkutils.get_all_html_from_keyfile(capfile=merged_trace,keyfile=kf)
        #for user security, delete keys immediately ? TODO
        
        #send html to super escrow for adjudication TODO
        shared.debug(0,["Sending html to super escrow for this transaction"])
        self.sendMessages(msg={tx.uniqID()+'.'+\
        self.superEscrow:'DISPUTE_L2_SEND_HTML_EVIDENCE:'+','.join(htmlarray)},\
        transaction=tx)
        
    #This function should be called when any TRANSACTION_REQUEST message
    #is sent. It checks for the existence of another message of the 
    #same type with the same parameters. If found, and the requests are
    #deemed compatible, it will send out
    #a transaction accepted message to both parties.
    def processTransactionRequest(self, request):
        response=[]
        #ID of requesting agent is after the .
        shared.debug(0,["starting processTR"])
        requester = request[0].split('.')[-1]
        shared.debug(0,["set the requester to : ",requester])
        #sanity check: make sure the agent is requesting a transaction
        #involving themselves!
        if not requester in request[1]:
            response = ['reject','ID of requesting party not found in transaction']
            
        req_msg_data = request[1].split(':')[1].split(',')
        
        for [k,m] in self.requestStore:
            #ignore the message that made the request
            if [k,m]==request:
                continue
            #ignore the message if it isn't a tx req
            if 'TRANSACTION_REQUEST' != m.split(':')[0]:
                continue
            #parse the data in the message
            msg_data = m.split(':')[1].split(',')
            if not msg_data[0]==req_msg_data[1] and msg_data[1]==req_msg_data[0]:
                continue
            #now we know the counterparties match; need to check the 
            #financial part
            if not msg_data[4]==req_msg_data[4]:
                response= ['reject','wrong currency']
            elif not msg_data[2]==req_msg_data[2]:
                response= ['reject','mismatched bitcoin amount']
            #TODO: use a "mid" approach for prices
            elif not msg_data[3]==req_msg_data[3]:
                response= ['reject','mismatched prices']
            else:
                response=['accept']
                
        if response:
            if response[0]=='accept':
                #create the transaction object and store it
                tx = Transaction(req_msg_data[0],req_msg_data[1],req_msg_data[2]\
                                ,req_msg_data[3],req_msg_data[4])
                self.transactionUpdate(tx=tx,new_state=2)
                
                #create the acceptance message - we MUST give the recipient
                #the unique ID otherwise it won't match in future correspondence
                message = {tx.uniqID()+'.'+self.escrowID:'TRANSACTION_ACCEPTED:'\
                        +','.join([tx.buyer,tx.seller,str(tx.amount),\
                            str(tx.price),tx.currency,str(tx.creationTime)])}
                
                #send acceptance to BOTH parties
                for recipientID in req_msg_data[0:2]:
                    shared.debug(0,["send acceptance to counterparty:",recipientID])
                    self.sendMessages(message,recipientID)
                    
                #delete any earlier requests matching this
                #counterparty pair from the requestStore (wipe slate clean)
                self.requestStore = \
                [x for x in self.requestStore if (req_msg_data[0] not in \
                x[1].split(':')[1].split(',')) and (req_msg_data[1] not in \
                x[1].split(':')[1].split(','))]
                shared.debug(0,["After accepting transaction the request",\
                                "store is now:",self.requestStore])
                
            elif response[0]=='reject':
                #send rejection to both; no need to create a tx object!
                message={'0.'+self.escrowID:'TRANSACTION_REJECTED:'+response[1]}
                for recipientID in req_msg_data[0:1]:
                    self.sendMessages(message,recipientID)
                
                #delete any earlier requests matching this
                #counterparty pair from the requestStore (wipe slate clean)
                self.requestStore = \
                [x for x in self.requestStore if (req_msg_data[0] not in \
                x[1].split(':')[1].split(',')) and (req_msg_data[1] not in \
                x[1].split(':')[1].split(','))]
                        
            else:
                shared.debug(0,["something seriously wrong here"])
                exit(1)
        else:
            self.requestStore.append(request)
        
    #this is called, i.e. initiated, by buyer only, but
    #we need to send a message to seller to check squid+ssllog is running,
    #and to start their stcppipe. So a reject can be sent back to the buyer
    #if that doesn't work. The main point is that the seller should not need
    #to perform user input, only to have ssllog running.         
    def negotiateBankSessionStartRequest(self,request):
        response=[]
        #ID of requesting agent is after the .
        requester = request[0].split('.')[1]
        #sanity check: make sure the agent is requesting a session for a 
        #transaction that (a) they own and (b) is in the correct state
        txID = request[0].split('.')[0]
        
        if txID not in (x.uniqID() for x in self.transactions):
            response =  ['reject','invalid transaction id']
        for i,t in enumerate(self.transactions):
            if t.uniqID()==txID:
                buyerID,sellerID = [t.buyer, t.seller]
                #include state 19 as a possible restart after a failure
                if t.state not in [2,17,19]:
                    response = ['reject','transaction is not in a state ready \
                                to do banking session']
                else:
                    self.sendMessages({t.uniqID()+'.'+t.seller:\
                        'BANK_SESSION_START_REQUEST:'},recipientID=t.seller)
                    msg = self.getSingleMessage(20)
                    if not msg:
                        response = ['reject','seller is not responding']
                        break
                    elif 'BANK_SESSION_READY' not in msg.values()[0]:
                        response = ['reject',\
                        'seller did not respond to request to start banking']
                        break
                    
                    #seller is ready if we got here
                    
                    self.transactionUpdate(tx=self.transactions[i],new_state=17)
    
                    #TODO: killing pre-existing pipes here is only valid
                    #for one-session-at-a-time model; OK for now
                    shared.local_command(['pkill','-SIGTERM','stcppipe'],bg=True)
                    #prepare file storage on escrow for logs, start stcppipe
                    runID='_'.join(['escrow',txID,'banksession'])
                    d = shared.makedir([g("Directories","escrow_base_dir"),runID])
                    stcpd = shared.makedir([d,'stcplog'])
                    shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
                    stcpd, '-b','127.0.0.1', g("Escrow","escrow_stcp_port"),\
                    g("Escrow","escrow_input_port")],bg=True)
                    message = {txID+'.'+self.escrowID:'BANK_SESSION_START_ACCEPTED:'}
                    #send acceptance to buyer
                    self.sendMessages(message,buyerID)
                    return True
                    
        if response[0]=='reject':
            message={txID+'.'+self.escrowID:'BANK_SESSION_START_REJECTED:'+response[1]}
            #send rejection to both parties involved
            for recipientID in [buyerID,sellerID]:
                self.sendMessages(message,recipientID)
            return False
                    
        else:
            shared.debug(0,["something seriously wrong here"])
            exit(1)
        
    #request ssl hashes from counterparties, wait for a return
    #and check against escrow's own record. Adjudicate on that basis.
    def requestSSLHashes(self,request):
        #first fire off request for hashes from both counterparties.
        #even if they are online this may take some time. State is maintained
        #in the transaction.
        
        txID, requester = request[0].split('.')
        tx = self.getTxByID(txID)
        #whether we put the tx in dispute depends on its current state, so check
        if tx.state != 18:
            self.sendMessages({txID+'.'+self.escrowID:'L1_DISPUTE_REJECTED: \
                This transaction cannot yet be disputed as the banking session \
                    has not been completed.'},requester)
        
        #we have the right current state - move to the disputed state
        self.transactionUpdate(txID=txID,new_state=5)
        
        #need the ssl data from the counterparties to resolve the dispute
        counterparty = tx.buyer if tx.buyer != requester else tx.seller
        for recipient in [requester, counterparty]:
            msg={txID+'.'+self.escrowID:'SSL_DATA_REQUEST'}
            self.sendMessages(msg,recipient)
        
    #on receipt of hashes, match them with a transaction
    #check that it's currently in the correct dispute state; store persistently
    #finally, trigger adjudication if both sets have been received
    def receiveSSLHashes(self,msg):
        #ignore the message if it isn't a ssl data set
        if 'SSL_DATA_SEND' != msg.values()[0].split(':')[0]:
                shared.debug(0,["Serious error - message of type:",\
            msg.values()[0].split(':')[0],"instead of SSL_DATA_SEND"])
                return False
            
        response=[]
        
        shared.debug(0,["starting receiveSSLHashes"])
        txID, sender = msg.keys()[0].split('.')
        shared.debug(0,["set the sender to : ",sender])
        
        #establish in advance which transaction this data refers to
        tmptx = self.getTxByID(txID)
        if not tmptx:
            shared.debug(0,["Serious error: ssl data was sent for a transaction"\
                            " not stored on the escrow!"])
            exit(1)
        
        #check the role as behaviour depends on it
        role = tmptx.getRole(sender)
        pre_states = [5,7] if role=='buyer' else [5,6]
        #transaction should be waiting for buyer data
        if not tmptx.state in pre_states:
            rmsg = {txID+'.'+self.escrowID:'SSL_DATA_REJECTED:You should \
                not have sent your ssl data at this time, it has been ignored.'}
            self.sendMessages(rmsg,sender)
      
        #we have valid data, at the right time; so store it.
        
        #buyers send magic hashes after '^' so:
        sent_data = msg.values()[0].split(':')[-1]
        
        if role=='buyer':
            hash_data_string,magic_hashes_string=sent_data.split('^')
            #v important: magic_hashes very likely to be null
            hash_data = hash_data_string.split(',')
            magic_hashes = magic_hashes_string.split(',')
        else:
            hash_data = sent_data.split(',')
        
        matched=False
        for k,m in self.hashStore.iteritems():
            tmptxID, tmpsender = k.split('.')
            tmphashdata = m.split(':')[-1].split(',')
            #parse the data in the message
            #we need to find out if the counterparty has sent a corresponding
            #data set
            if tmptxID==txID:
                #we have a match; send the adjudication,after confirming
                #receipt
                matched=True
                rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED'}
                self.sendMessages(rmsg,sender)
                self.transactionUpdate(txID=txID,new_state=8)
                buyer_hashes = tmphashdata if role =='seller'\
                    else hash_data
                seller_hashes = tmphashdata if role =='buyer'\
                    else hash_data
                
                #to decide which magic_hashes to send to adjudication, we can't
                #use something like "if magic_hashes" because it's perfectly
                #normal for it to be None. 
                if role=='buyer':
                    sent_magic_hashes = magic_hashes
                else:
                    sent_magic_hashes = self.magicStore[txID]
                self.adjudicateL1Dispute(tmptx,tmptx.buyer,buyer_hashes,\
                                tmptx.seller,seller_hashes,sent_magic_hashes)
                #action complete; remove the temporary items from the hash store
                #TODO handle this properly, with persistence also
                self.hashStore = {}
                self.magicStore= {}
            
        if not matched:
            #reaching here means the data wasn't found in the current hashStore,
            #so store it and wait for the next
            rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED'}
            self.sendMessages(rmsg,sender) 
            
            #for buyers, clean out the magic hashes from the msg to be stored
            #so that we can properly compare it with the seller's hashes
            if role=='buyer':
                self.magicStore.update({txID:magic_hashes})
                msg ={msg.keys()[0]:msg.values()[0].split('^')[0]}
                
            #for buyers and sellers
            self.hashStore.update(msg)
            
            ns = 6 if role=='buyer' else 7
            self.transactionUpdate(txID=txID,new_state=ns)
                
    #logic: if one of three is inconsistent, the third party is lying
    #if all three are consistent, raise dispute level to super-escrow
    #(also if all three are inconsistent, hopefully this won't happen!!)
    def adjudicateL1Dispute(self,transaction,buyer,buyer_hash_list,seller,\
                                        seller_hash_list,magic_hashes):
        
        #TODO: actual bitcoin movements!
        
        #first step: generate our own ssl hash list using the NetworkAudit module
        my_hash_list = self.getHashList(transaction)
        stcpdir = os.path.join(g("Directories","escrow_base_dir"),\
                    '_'.join(['escrow',transaction.uniqID(),"banksession"]),"stcplog")
        hashes_to_ignore = sharkutils.get_hashes_to_ignore(stcpdir,magic_hashes)
        shared.debug(0,["Hashes to ignore are:",hashes_to_ignore])
        #now we can basically perform set operations to come to a decision
        
        #first subtract ignorable hashes from all hashlist records
        my_hash_list = set(my_hash_list)-set(hashes_to_ignore)
        buyer_hash_list = set(buyer_hash_list)-set(hashes_to_ignore)
        seller_hash_list = set(seller_hash_list)-set(hashes_to_ignore)
        
        if not my_hash_list:
            #in this failure case, elevate dispute
            msg = {transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION_FAILURE:escrow hash list not found for this transaction'}
            #leave it in dispute for now
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
        
         #second step: comparison of three hash lists
         #third step: send adjudication messages to both counterparties
        if (buyer_hash_list == my_hash_list) and seller_hash_list != my_hash_list:
            msg={transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION:awarded to buyer, seller\'s ssl record is invalid'}
            #insert bitcoin transfer TODO
            self.transactionUpdate(txID=transaction.uniqID(),new_state=9)
            for recipient in [buyer,seller]:
                self.sendMessages(msg,recipient)
                
        elif (buyer_hash_list != my_hash_list) and seller_hash_list == my_hash_list:
            msg={transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION:awarded to seller, buyer\'s ssl record is invalid'}
            #insert bitcoin transfer TODO
            self.transactionUpdate(txID=transaction.uniqID(),new_state=10)
            for recipient in [buyer,seller]:
                self.sendMessages(msg,recipient)
                
        elif buyer_hash_list == seller_hash_list: #in this case, we don't need to check escrow
            msg={transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION_FAILURE: ssl data is consistent - dispute escalated to super escrow'}
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
            self.transactionUpdate(tx=transaction,new_state=12)
        else:
            msg = {transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION_FAILURE:all three ssl data records are inconsistent'}
            #This is a catastrophic failure of the system; TODO prob. escalate
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
            self.transactionUpdate(tx=transaction,new_state=11)
        shared.debug(0,["Mismatches between buyer and seller:", \
        set(buyer_hash_list).symmetric_difference(set(seller_hash_list))])
        shared.debug(0,["Mismatches between buyer and escrow:", \
        set(buyer_hash_list).symmetric_difference(set(my_hash_list))])
        shared.debug(0,["Mismatches between seller and escrow:", \
        set(my_hash_list).symmetric_difference(set(seller_hash_list))]) 
               
#========MESSAGING FUNCTIONS======================                
    def sendMessages(self,messages={},recipientID='',transaction=None):
        recipientID = self.uniqID if recipientID == '' else recipientID
        
        #this standardised way will work if we have only one message
        if transaction:
            messages = {transaction.uniqID()+'.'+self.agent.uniqID():messages.values()[0]}
        
        shared.debug(0,["About to send a message to",recipientID])
        return Msg.sendMessages(messages,recipientID=recipientID)
    
    def getSingleMessage(self,timeout=1):
        return Msg.getSingleMessage(self.escrowID,timeout)
    
    
    def providePort(self):
        #TODOcode to provide a currently unused port for concurrent transactions
        #this seems like it could be tricky
        #for now, static
        return g("Escrow","escrow_input_port")
        
#Hopefully defunct:
'''
    def collectMessages(self):
        msgs = Msg.collectMessages(self.agent.uniqID())
        if not msgs: 
            return None
        else:
            return msgs
        
    def waitForMessages(self,timeout):
        for x in range(1,timeout):
            if (self.collectMessages()):
                return True
            time.sleep(1)
        shared.debug(1,["Waiting for messages timed out"])
        return False
'''    
         

    
