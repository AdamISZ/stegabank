import time
import os
import shared
import Agent
from AppLayer.Transaction import Transaction
import Messaging.MessageWrapper as Msg
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
        
        #temporary buffer for all messages brought down from MQs
        self.messageBuffer={}
        
        #this  needs to be persisted as it contains
        #state information - in order to accept requests involving two parties,
        #the escrow needs to keep a record of earlier requests downloaded
        #from the MQ. The format is a list of lists, each inner list having
        #a key,message pair [k,m]
        self.requestStore=[]
        
        #a list of list of hashes; same comments as for requeststore above
        self.hashStore={}
        
    def run(self):
        #the main loop to be called for the daemon meaning we're
        #listening for messages/requests/instructions from useragents.
        while True:
            self.messageBuffer={}
            self.waitForMessages(5)
            if not self.messageBuffer: continue
            #we received at least one message: check the headers,
            #perform the appropriate action
            shared.debug(0,["We received at least one message in the main loop:",self.messageBuffer])
            for k,m in self.messageBuffer.iteritems():
            # this is effectively a switch/case situation.
            # may look into a more Pythonic way of doing it later TODO
                if 'TRANSACTION_REQUEST' in m:
                    shared.debug(0,["Found a transaction request in the buffer"])
                    self.processTransactionRequest([k,m]) 
                
                elif 'TRANSACTION_ABORT' in m:
                    shared.debug(0,["Found a transaction abort instruction in the buffer"])
                    self.abortTransaction([k,m])
                    
                elif 'BANK_SESSION_START_REQUEST' in m:
                    shared.debug(0,["Found a bank session start request in the buffer"])
                    self.processBankSessionStartRequest([k,m])
                
                elif 'BANK_SESSION_ABORT' in m:
                    shared.debug(0,["Found a bank session abort instruction in the buffer"])
                    self.abortBankingSession([k,m])
                
                elif 'BANK_SESSION_ENDED' in m:
                    shared.debug(0,["Found a bank session ended notification in the buffer"])
                    #shut down the stcppipe for this run
                    #TODO: handle process shutdown better than this!
                    shared.local_command(['pkill', '-SIGTERM', 'stcppipe'])
                    
                elif 'DISPUTE_L1_REQUEST' in m:
                    shared.debug(0,["Found a Level 1 dispute request in the buffer"])
                    self.requestSSLHashes([k,m])
                    
                elif 'SSL_DATA_SEND' in m:
                    shared.debug(0,["Found a ssl data transfer in the buffer"])
                    self.receiveSSLHashes({k:m})
                
                elif 'SSL_DATA_SEND_MAGIC' in m:
                    shared.debug(0,["Found a magic hashes method in the buffer"])
                    self.receiveSSLMagicHashes({k:m})
                    
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
        if tmptx.state in ['INITIALISED','UNINITIALISED']:
            response=['accept']
        elif tmptx.state in ['INVALID','ABORTED']:
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
            self.transactionUpdate(txID=txID,new_state='ABORTED') 
            
        else:
            for recipient in [buyerID,sellerID]:
                self.sendMessages({txID+'.'+self.escrowID:\
                        'TRANSACTION_ABORT_REJECTED:'+response[1]},recipient)
                               
                               
                               
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
                self.transactionUpdate(tx=tx,new_state='INITIALISED')
                
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
    def processBankSessionStartRequest(self,request):
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
                if t.state != 'INITIALISED':
                    response = ['reject','transaction is not in state INITIALISED']
                else:
                    #check that proxy is running?TODO
                    self.transactionUpdate(tx=self.transactions[i],new_state='IN_PROCESS')
    
                    #TODO: killing pre-existing pipes here is only valid
                    #for one-session-at-a-time model; OK for now
                    shared.local_command(['pkill','-SIGTERM','stcppipe'],bg=True)
                    #prepare file storage on escrow for logs, start stcppipe
                    runID='_'.join(['escrow',txID,'banksession'])
                    d = shared.makedir([g("Directories","escrow_base_dir"),runID])
                    stcpd = shared.makedir([d,'stcplogs'])
                    shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
                    stcpd, '-b','127.0.0.1', g("Escrow","escrow_stcp_port"),\
                    g("Escrow","escrow_input_port")],bg=True)
                    message = {txID+'.'+self.escrowID:'BANK_SESSION_START_ACCEPTED:'}
                    #send acceptance to both parties involved
                    for recipientID in [buyerID,sellerID]:
                        self.sendMessages(message,recipientID)
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
        
            
            
    def sendMessages(self,messages,recipientID,transaction=None):
        return Msg.sendMessages(messages,recipientID)
    
    #request ssl hashes from counterparties, wait for a return
    #and check against escrow's own record. Adjudicate on that basis.
    def requestSSLHashes(self,request):
        #first fire off request for hashes from both counterparties.
        #even if they are online this may take some time. However, if they're
        #offline, the request message is stored in the queue until they
        #respond
        
        txID, requester = request[0].split('.')
        self.transactionUpdate(txID=txID,new_state='IN_DISPUTE')
        tx = filter(lambda a: a.uniqID()==txID,self.transactions)[0]
        counterparty = tx.buyer if tx.buyer != requester else tx.seller
        for recipient in [requester, counterparty]:
            msg={txID+'.'+self.escrowID:'SSL_DATA_REQUEST'}
            self.sendMessages(msg,recipient)
        
    #on receipt of hashes, match them with a transaction
    #check that it's currently in a dispute state; store persistently
    #finally, trigger adjudication if both sets have been received
    def receiveSSLHashes(self,msg):
        #ignore the message if it isn't a ssl data set
        if 'SSL_DATA_SEND' != msg.values()[0].split(':')[0]:
                shared.debug(0,["Serious error - message of type:",\
            msg.values()[0].split(':')[0],"instead of SSL_DATA_SEND"])
                return False  
        #check the role as behaviour depends on it
        role = tx.getRole(sender)
        response=[]
        
        shared.debug(0,["starting receiveSSLHashes"])
        txID, sender = msg.keys()[0].split('.')
        shared.debug(0,["set the sender to : ",sender])
        
        #this is a list of all the hashes
        #buyers send magic hashes after '^' so:
        sent_data = msg.values()[0].split(':')[-1]
        if role=='buyer':
            hash_data_string,magic_hashes_string=sent_data.split('^')
            #v important: magic_hashes very likely to be null
            hash_data = hash_data_string.split(',')
            magic_hashes = magic_hashes_string.split(',')
        else:
            hash_data = sent_data.split(',')
        
        #establish in advance which transaction this data refers to
        tmptx = filter(lambda a: a.uniqID()==txID,self.transactions)[0]
        
        if not tmptx:
            shared.debug(0,["Serious error: ssl data was sent for a transaction"\
                            " not stored on the escrow!"])
            exit(1)
        
        
        for k,m in self.hashStore.iteritems():
            tmptxID, tmpsender = k.split('.')
            tmphashdata = m.split(':')[-1].split(',')
            #parse the data in the message
            #we need to find out if the counterparty has sent a corresponding
            #data set
            if tmptxID==txID:
                #we have a match; send the adjudication,after confirming
                #receipt
                rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED'}
                self.sendMessages(rmsg,sender)
                
                buyer_hashes = tmphashdata if tmptx.getRole(tmptxID)=='buyer'\
                    else hash_data
                seller_hashes = tmphashdata if tmptx.getRole(tmptxID)=='seller'\
                    else hash_data
                
                #to decide which magic_hashes to send to adjudication, we can't
                #use something like "if magic_hashes" because it's perfectly
                #normal for it to be None. 
                if role=='buyer':
                    sent_magic_hashes = magic_hashes
                else:
                    sent_magic_hashes = self.magicStore[txID+'.'+tmptx.buyer]
                self.adjudicateL1Dispute(tmptx,tmptx.buyer,buyer_hashes,\
                                tmptx.seller,seller_hashes,sent_magic_hashes)
                #action complete; remove the temporary items from the hash store
                #TODO handle this properly, with persistence also
                self.hashStore = {}
                self.magicStore= {}
            
        #reaching here means the data wasn't found in the current hashStore,
        #so store it and wait for the next
        rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED'}
        self.sendMessages(rmsg,sender) 
        
        #for buyers, clean out the magic hashes from the msg to be stored
        #so that we can properly compare it with the seller's hashes
        if role=='buyer':
            self.magicStore.update({txID:magic_hashes})
            msg ={msg.keys()[0]:msg.values()[0].split('^')[0]} #fun eh?
            
        #for buyers and sellers
        self.hashStore.update(msg)
        
        
                
    #logic: if one of three is inconsistent, the third party is lying
    #if all three are consistent, raise dispute level to super-escrow
    #(also if all three are inconsistent, hopefully this won't happen!!)
    def adjudicateL1Dispute(self,transaction,buyer,buyer_hashlist,seller,\
                                        seller_hashlist,magic_hashes):
        
        #TODO: actual bitcoin movements!
        
        #first step: generate our own ssl hash list using the NetworkAudit module
        my_hash_list = self.getHashList(transaction)
        stcpdir = os.path.join(g("Directories","escrow_base_dir"),\
                    '_'.join(['escrow',tx.uniqID(),"banksession"]),"stcplog")
        hashes_to_ignore = sharkutils.get_hashes_to_ignore(stcpdir,magic_hashes)
        
        #now we can basically perform set operations to come to a decision
        
        #first subtract ignorable hashes from all hashlist records
        my_hash_list = list(set(my_hash_list)-set(hashes_to_ignore))
        buyer_hash_list = list(set(buyer_hash_list)-set(hashes_to_ignore))
        seller_hash_list = list(set(seller_hashlist)-set(hashes_to_ignore))
        
        if not my_hash_list:
            #in this failure case, elevate dispute
            msg = {transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION_FAILURE:escrow hash list not found for this transaction'}
            #leave it in dispute for now
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
        
         #second step: comparison of three hash lists
         #third step: send adjudication messages to both counterparties
        if (buyer_hashlist == my_hash_list) and seller_hashlist != my_hash_list:
            msg={transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION:awarded to buyer, seller\'s ssl record is invalid'}
            #insert bitcoin transfer TODO
            self.transactionUpdate(txID=transaction.uniqID(),new_state='COMPLETE')
            for recipient in [buyer,seller]:
                self.sendMessages(msg,recipient)
                
        elif (buyer_hashlist != my_hash_list) and seller_hashlist == my_hash_list:
            msg={transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION:awarded to seller, buyer\'s ssl record is invalid'}
            #insert bitcoin transfer TODO
            self.transactionUpdate(txID=transaction.uniqID(),new_state='COMPLETE')
            for recipient in [buyer,seller]:
                self.sendMessages(msg,recipient)
                
        elif (buyer_hashlist == my_hash_list) and seller_hashlist == my_hash_list:
            msg={transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION_FAILURE:all ssl data is consistent - dispute escalated to super escrow'}
            #TODO: additional transaction state , L2 dispute
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
        else:
            msg = {transaction.uniqID()+'.'+self.escrowID:\
'DISPUTE_L1_ADJUDICATION_FAILURE:all three ssl data records are inconsistent'}
            #TODO: additional transaction state , L2 dispute
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
                
    #this method collects all messages addressed to this agent
    def collectMessages(self):
        msgs = Msg.collectMessages(self.escrowID)
        shared.debug(0,["Here are the messages collected:",msgs])
        if not msgs: 
            return None
        else:
            self.messageBuffer=msgs
            return True
        
    def waitForMessages(self,timeout):
        for x in range(1,timeout):
            if (self.collectMessages()):
                return True
            time.sleep(2)
        shared.debug(1,["Waiting for messages timed out"])
        return False
        
    def providePort(self):
        #TODOcode to provide a currently unused port for concurrent transactions
        #this seems like it could be tricky
        #for now, static
        return g("Escrow","escrow_input_port")
