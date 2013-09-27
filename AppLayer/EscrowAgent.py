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
        
        #temporary buffer for all messages brought down from MQs
        self.messageBuffer={}
        
        #persistent store of transaction objects TODO persistence
        self.transactions=[]
        
        #this  needs to be persisted as it contains
        #state information - in order to accept requests involving two parties,
        #the escrow needs to keep a record of earlier requests downloaded
        #from the MQ. The format is a list of lists, each inner list having
        #a key,message pair [k,m]
        self.requestStore=[]
        
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
            #remove the transaction permanently
            self.transactions = filter(lambda a: a!=tmptx,self.transactions)
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
                                ,req_msg_data[3],req_msg_data[4],state='INITIALISED')
                self.transactions.append(tx)
                
                #create the acceptance message - we MUST give the recipient
                #the unique ID otherwise it won't match in future correspondence
                message = {tx.uniqID()+'.'+self.escrowID:'TRANSACTION_ACCEPTED:'\
                        +','.join([tx.buyer,tx.seller,str(tx.amount),str(tx.price),tx.currency,str(tx.creationTime)])}
                
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
                shared.debug(0,["After accepting transaction the request store is now:",self.requestStore])
                
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
        
        print self.transactions
        
        if txID not in (x.uniqID() for x in self.transactions):
            response =  ['reject','invalid transaction id']
        for i,t in enumerate(self.transactions):
            if t.uniqID()==txID:
                buyerID,sellerID = [t.buyer, t.seller]
                if t.state != 'INITIALISED':
                    response = ['reject','transaction is not in state INITIALISED']
                else:
                    #check that proxy is running?TODO
                    self.transactions[i].state = 'IN_PROCESS'
                    #TODO: killing pre-existing pipes here is only valid
                    #for one-session-at-a-time model; OK for now
                    shared.local_command(['pkill','-SIGTERM','stcppipe'],bg=True)
                    #prepare file storage on escrow for logs, start stcppipe
                    runID='_'.join(['escrow',txID,'banksession'])
                    d = shared.makedir([g("Directories","escrow_base_dir"),runID])
                    stcpd = shared.makedir([d,'stcp_escrow'])
                    shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
                    stcpd, '-b','127.0.0.1', g("Escrow","escrow_stcp_port"),\
                    g("Escrow","escrow_input_port")],bg=True)
                    
                    response = ['accept']
                
        if response[0]=='accept':
            #TODO: two actions are needed: set up a stcppipe for this run
            #and then check that seller's proxy is ready
            #
            message = {txID+'.'+self.escrowID:'BANK_SESSION_START_ACCEPTED:'}
            
            #send acceptance to both parties involved
            for recipientID in [buyerID,sellerID]:
                self.sendMessages(message,recipientID)
            
        elif response[0]=='reject':
            message={txID+'.'+self.escrowID:'BANK_SESSION_START_REJECTED:'+response[1]}
            #send rejection to both parties involved
            for recipientID in [buyerID,sellerID]:
                self.sendMessages(message,recipientID)
                    
        else:
            shared.debug(0,["something seriously wrong here"])
            exit(1)
        
            
            
    def sendMessages(self,messages,recipientID,transaction=None):
        return Msg.sendMessages(messages,recipientID,self.host)
        
    
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
