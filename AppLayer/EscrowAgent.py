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
            
            #if any transaction is in a state where we have to do 
            #something without client input
            self.takeAppropriateActions()
            
            msg = self.getSingleMessage(5)
            if not msg:
                shared.debug(0,["Got nothing, waiting.."])
                continue
            
            k,m = msg.items()[0]
            txID, requester = k.split('.')
            #check: is the request asking for information only?
            if 'TRANSACTION_SYNC_REQUEST:' in m:
                self.sendTransactionSynchronization([k,m])
                continue
            
            #the message is about a transaction; find it in the db:
            tx = self.getTxByID(k.split('.')[0])
            if (not tx) and ('TRANSACTION_REQUEST' not in m):
                self.sendMessages(messages={'0.'+self.escrowID:\
                'REQUEST_REJECTED:0,No such transaction'},recipientID=requester)
                continue
                    
            #check that request asks for a valid transition
            if tx:
                if int(m.split(':')[1].split(',')[0]) not in shared.vtst[tx.state]:
                    self.sendMessages(messages={txID+'.'+self.escrowID:\
                    'REQUEST_REJECTED:'+str(tx.state)+',You cannot do that.'},\
                                      recipientID=requester)
                    continue
            
            # from here we know that the requester has asked to do
            # something legal to one of its transactions
            # This is effectively a switch/case situation.
            # may look into a more Pythonic way of doing it later TODO
            if 'TRANSACTION_REQUEST' in m:
                self.processTransactionRequest([k,m]) 
                continue
            
            elif 'TRANSACTION_ABORT' in m:
                #TODO: self.abortTransaction([k,m])
                continue
            
            elif 'BANK_SESSION_START_REQUEST' in m:
                self.negotiateBankSessionStartRequest([k,m])
                continue
            
            elif 'BANK_SESSION_ENDED' in m:
                self.cleanUpBankSession([k,m])
                continue
                
            elif 'DISPUTE_L1_REQUEST' in m:
                self.requestSSLHashes([k,m])
                continue
                
            elif 'SSL_DATA_SEND' in m:
                self.receiveSSLHashes({k:m})
                continue
            
            elif 'DISPUTE_L2_SEND_SSL_KEYS' in m:
                self.receiveSSLKeysAndSendHtml([k,m])
                continue
    
    def takeAppropriateActions(self):
        
        for t in self.transactions:
            if t.state==703:
                self.adjudicateL1Dispute(t)
            elif t.state==501:
                t.state=300
            elif t.state==706:
                t.state=800
                
            #TODO absolutely not for prod! This is just to help
            #debugging L2; always allow ssl key resending
            elif t.state==801 or t.state==802:
                t.state=800
        
        self.transactionUpdate(full=True)
        
    def cleanUpBankSession(self,msg):
        #shut down the stcppipe for this run
        #TODO - this is obviously incompatible with multiple sessions
        #TODO: this creates a zombie - does it matter?
        shared.local_command(['pkill', '-SIGTERM', 'stcppipe'])
        requested_state=int(msg[1].split(':')[1].split(',')[0])
        tx = self.getTxByID(msg[0].split('.')[0])
        #note that the requester will have encoded success/failure
        #in his requested state
        self.transactionUpdate(tx=tx,new_state=requested_state)
        #inform the seller
        self.sendMessages({tx.uniqID()+'.'+\
        tx.seller:'BANK_SESSION_ENDED:'+str(requested_state)},recipientID=tx.seller)
        
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
       
        #find the transaction
        txID,sender = instruction[0].split('.')
        tmptx = self.getTxByID(txID)
        if not tmptx:
            shared.debug(0,["Error, transaction cannot be aborted,not in db"])
            return
        for recipient in [tmptx.buyer,tmptx.seller]:
                self.sendMessages({txID+'.'+self.escrowID:\
    'TRANSACTION_ABORT_ACCEPTED:400,requested by '+sender},recipientID=recipient)
        #abort
        self.transactionUpdate(txID=txID,new_state=400) 
                               
    #in L2 dispute, we ask the buyer for one or more keys
    #then we grab whatever html we can get with those keys
    #and send them on to super escrow
    def receiveSSLKeysAndSendHtml(self, msg):
        #get the transaction first
        tx = self.getTxByID(msg[0].split('.')[0])
        shared.debug(0,["Received these keys:",msg])
        #grab the keys from the message and turn them into a single 
        #keyfile for use by tshark
        sslkeylines = msg[1].split(':')[1].split(',')[1:]
        keydir = os.path.join(g("Directories","escrow_base_dir"),\
                '_'.join(['escrow',tx.uniqID(),'banksession']))
        kf = os.path.join(keydir,'user_sent.keys')
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
            self.sendMessages({m_k:bytearray('DISPUTE_L2_SEND_HTML_EVIDENCE:')+\
                               a},recipientID=self.superEscrow)
            
        self.transactionUpdate(tx=tx,new_state=802)
        
    #This function should be called when any TRANSACTION_REQUEST message
    #is sent. It checks for the existence of another message of the 
    #same type with the same parameters. If found, and the requests are
    #deemed compatible, it will send out
    #a transaction accepted message to both parties.
    def processTransactionRequest(self, request):
        response=[]
        
        requester = request[0].split('.')[-1]
        
        #state management
        requested_state = int(request[1].split(':')[1].split(',')[0])
        
        #buyerID,sellerID,amount,price,currency
        req_msg_data = request[1].split(':')[1].split(',')[1:]
        
        #sanity check: don't go any further unless the transaction involves
        #the requester:
        if not requester in req_msg_data[0:2]:
            return
        
        tmptx = Transaction(*req_msg_data)
        
        existing = self.getTxByID(tmptx.uniqID())
        
        if existing:
            shared.debug(0,\
                ["Found a pre-existing transaction matching this request"])
            #we need to validate that the financial information matches,
            #else reject the request
            if not existing.buyer==req_msg_data[1] and \
                existing.seller==req_msg_data[0]:
                response=['reject','mismatched counterparties']
            #now we know the counterparties match; need to check the 
            #financial part
            if not existing.currency==req_msg_data[4]:
                response= ['reject','wrong currency']
            elif not existing.amount==req_msg_data[2]:
                response= ['reject','mismatched bitcoin amount']
            #TODO: use a "mid" approach for prices
            elif not existing.price==req_msg_data[3]:
                response= ['reject','mismatched prices']
            else:
                response=['accept']
            
            if response[0]=='reject':
                message={'0.'+self.escrowID:'TRANSACTION_REJECTED:'\
                         +str(existing.state)+','+response[1]}
                for recipientID in req_msg_data[0:1]:
                    self.sendMessages(message,recipientID)
                
            #check state machine rules; if valid, initialize
            if (requested_state ==300 and existing.state == 202) or \
                (requested_state==300 and existing.state == 201):
                #all as normal; initialise
                existing.initialize()
                self.transactionUpdate(tx=existing,new_state=300)
                message={existing.uniqID()+'.'+self.escrowID:'TRANSACTION_ACCEPTED:'\
                         +','.join([str(existing.state),existing.buyer,\
                        existing.seller,existing.amount,existing.price,\
                        existing.currency,str(existing.creationTime)])}
                for recipientID in req_msg_data[0:2]:
                    self.sendMessages(message,recipientID)
            else:
                shared.debug(0,["error; seems to be in a corrupted state?"])
       
        else:
            #there is no pre-existing transaction request; set this one
            requester_is_buyer = True if requester==req_msg_data[0] else False
            tmptx.state = 201 if requester_is_buyer else 202
            self.transactions.append(tmptx)
            self.transactionUpdate(full=True)
            
            
          
        
    #this is called, i.e. initiated, by buyer only, but
    #we need to send a message to seller to check squid+ssllog is running,
    #and to start their stcppipe. So a reject can be sent back to the buyer
    #if that doesn't work. The main point is that the seller should not need
    #to perform user input, only to have ssllog running.         
    def negotiateBankSessionStartRequest(self,request):
        response=[]
        
        #ID of requesting agent is after the .
        requester = request[0].split('.')[1]
        
        tx = self.getTxByID(request[0].split('.')[0])
        
        #first step is to ask the seller to confirm readiness
        self.sendMessages({tx.uniqID()+'.'+tx.seller:\
                'BANK_SESSION_START_REQUEST:'+str(tx.state)},\
                          recipientID=tx.seller)
        #wait for response; likelihood of no response is high!
        msg = self.getSingleMessage(200)
        if not msg:
            response = ['reject','seller is not responding']
        elif 'BANK_SESSION_READY' not in msg.values()[0]:
            response=['reject','seller did not respond to request to start banking']
        else:
            response = ['accept']
            
        if response[0]=='reject':
            message={tx.uniqID()+'.'+self.escrowID:'BANK_SESSION_START_REJECTED:'\
                     +str(tx.state)+','+response[1]}
            #send rejection to both parties involved
            for recipientID in [buyerID,sellerID]:
                self.sendMessages(message,recipientID)
            return False
        
        #seller is ready if we got here
                    
        self.transactionUpdate(tx=tx,new_state=500)
        
        #TODO: killing pre-existing pipes here is only valid
        #for one-session-at-a-time model; OK for now
        shared.local_command(['pkill','-SIGTERM','stcppipe'],bg=True)
        #time.sleep(2)
        #prepare file storage on escrow for logs, start stcppipe
        runID='_'.join(['escrow',tx.uniqID(),'banksession'])
        d = shared.makedir([g("Directories","escrow_base_dir"),runID])
        stcpd = shared.makedir([d,'stcplog'])
        shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
        stcpd, '-b','127.0.0.1', g("Escrow","escrow_stcp_port"),\
        g("Escrow","escrow_input_port")],bg=True)
        message = {tx.uniqID()+'.'+self.escrowID:'BANK_SESSION_START_ACCEPTED:'\
                   +str(tx.state)}
        #send acceptance to buyer
        self.sendMessages(message,tx.buyer)
        
    #request ssl hashes from counterparties, wait for a return
    #and check against escrow's own record. Adjudicate on that basis.
    def requestSSLHashes(self,request):
        #first fire off request for hashes from both counterparties.
        #even if they are online this may take some time. State is maintained
        #in the transaction.
        txID, requester = request[0].split('.')
        tx = self.getTxByID(txID)
        
        #immediately set as disputed
        self.transactionUpdate(txID=txID,new_state=700)
        
        #need the ssl data from the counterparties to resolve the dispute
        counterparty = tx.buyer if tx.buyer != requester else tx.seller
        for recipient in [requester, counterparty]:
            msg={txID+'.'+self.escrowID:','.join([str(tx.state),'SSL_DATA_REQUEST'])}
            self.sendMessages(msg,recipient)
        
    #on receipt of hashes, match them with a transaction
    #check that it's currently in the correct dispute state; store persistently
    #finally, trigger adjudication if both sets have been received
    def receiveSSLHashes(self,msg):
        
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
        requested_state = int(msg.values()[0].split(':')[1].split(',')[0])
        sent_data = msg.values()[0].split(':')[-1]
        
        if role=='buyer':
            hashes_string,magic_string=sent_data.split('^')
            #v important: magic_hashes very likely to be null
            tmptx.buyerHashes = hashes_string.split(',')[1:]
            tmptx.magicHashes = magic_string.split(',')
        else:
            tmptx.sellerHashes = sent_data.split(',')[1:]
            
        if (role=='buyer' and tmptx.state==702) or \
            (role=='seller' and tmptx.state==701):
            self.transactionUpdate(tx=tmptx,new_state=requested_state)
            #send confirmation of receipt:
            rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED:'+str(requested_state)}
            self.sendMessages(rmsg,sender)
            #adjudicate
            self.adjudicateL1Dispute(tmptx)
            
        elif tmptx.state==700:
            ns = 701 if role=='buyer' else 702
            self.transactionUpdate(tx=tmptx,new_state=ns)
            #send confirmation of receipt:
            rmsg = {txID+'.'+self.escrowID:'SSL_DATA_RECEIVED:'+str(ns)}
            self.sendMessages(rmsg,sender)
        else:
            shared.debug(0,["Serious error, shouldn't get here"])
            return False
        
                
    #logic: if one of three is inconsistent, the third party is lying
    #if all three are consistent, raise dispute level to super-escrow
    #(also if all three are inconsistent, hopefully this won't happen!!)
    def adjudicateL1Dispute(self,transaction):
        
        #TODO: actual bitcoin movements!
        
        #first step: generate our own ssl hash list using the NetworkAudit module
        my_hash_list = self.getHashList(transaction)
        stcpdir = os.path.join(g("Directories","escrow_base_dir"),\
                    '_'.join(['escrow',transaction.uniqID(),"banksession"]),\
                        "stcplog")
        hashes_to_ignore = sharkutils.get_hashes_to_ignore(stcpdir,\
                                                    transaction.magicHashes)
        shared.debug(0,["Hashes to ignore are:",hashes_to_ignore])
        #now we can basically perform set operations to come to a decision
        
        #first subtract ignorable hashes from all hashlist records
        my_hash_list = set(my_hash_list)-set(hashes_to_ignore)
        buyer_hash_list = set(transaction.buyerHashes)-set(hashes_to_ignore)
        seller_hash_list = set(transaction.sellerHashes)-set(hashes_to_ignore)
        
        buyer = transaction.buyer
        seller = transaction.seller
        
        if not my_hash_list:
            #in this failure case, elevate dispute
            msg = {transaction.uniqID()+'.'+self.escrowID:\
                'DISPUTE_L1_ADJUDICATION_FAILURE:'+str(transaction.state)+\
                ',escrow hash list not found for this transaction'}
            #leave it in dispute for now
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
        
         #second step: comparison of three hash lists
         #third step: send adjudication messages to both counterparties
        if (buyer_hash_list == my_hash_list) and seller_hash_list != my_hash_list:
            self.transactionUpdate(tx=transaction,new_state=704)
            msg={transaction.uniqID()+'.'+self.escrowID:\
                'DISPUTE_L1_ADJUDICATION:'+str(transaction.state)+\
                ',awarded to buyer, seller\'s ssl record is invalid'}
            #insert bitcoin transfer TODO
            for recipient in [buyer,seller]:
                self.sendMessages(msg,recipient)
                
        elif (buyer_hash_list != my_hash_list) and seller_hash_list == my_hash_list:
            self.transactionUpdate(tx=transaction,new_state=705)
            msg={transaction.uniqID()+'.'+self.escrowID:\
                'DISPUTE_L1_ADJUDICATION:'+str(transaction.state)+\
                ',awarded to seller, buyer\'s ssl record is invalid'}
            #insert bitcoin transfer TODO
            for recipient in [buyer,seller]:
                self.sendMessages(msg,recipient)
        
        #TODO: check escrow or not?
        elif buyer_hash_list == seller_hash_list: 
            self.transactionUpdate(tx=transaction,new_state=706)
            msg={transaction.uniqID()+'.'+self.escrowID:\
                'DISPUTE_L1_ADJUDICATION_FAILURE:'+str(transaction.state)+\
                ',ssl data is consistent - dispute escalated to super escrow'}
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
                
        else:
            self.transactionUpdate(tx=transaction,new_state=706)
            msg = {transaction.uniqID()+'.'+self.escrowID:\
                'DISPUTE_L1_ADJUDICATION_FAILURE:'+str(transaction.state)+\
                ',all three ssl data records are inconsistent'}
            #This is a catastrophic failure of the system; TODO prob. escalate
            for recipient in [buyer,seller,self.superEscrow]:
                self.sendMessages(msg,recipient)
                
        #v. helpful for debugging and testing
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
            messages={transaction.uniqID()+'.'+self.uniqID():messages.values()[0]}
        
        shared.debug(0,["About to send a message to",recipientID])
        return Msg.sendMessages(messages,recipientID=recipientID)
    
    def getSingleMessage(self,timeout=1):
        return Msg.getSingleMessage(self.escrowID,timeout)
    
    
    def providePort(self):
        #TODOcode to provide a currently unused port for concurrent transactions
        #this seems like it could be tricky
        #for now, static
        return g("Escrow","escrow_input_port")

    
