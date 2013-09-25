import time
import shared
import Agent
import Transaction
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
        
        #hardcoded for testing TODO
        self.escrowID='123'
        
        #temporary buffer for all messages brought down from MQs
        self.messageBuffer={}
        
        #this  needs to be persisted as it contains
        #state information - in order to accept requests involving two parties,
        #the escrow needs to keep a record of earlier requests downloaded
        #from the MQ.
        self.requestStore=[]
        self.bankSessionRequestStore=[]
        
    def run(self):
        #the main loop to be called for the daemon meaning we're
        #listening for messages/requests/instructions from useragents.
        while True:
            self.waitForMessages(5)
            if not self.messageBuffer: continue
            #we received at least one message: check the headers,
            #perform the appropriate action
            for k,m in self.messageBuffer.iteritems():
            # this is effectively a switch/case situation.
            # may look into a more Pythonic way of doing it later TODO
                if 'TRANSACTION_REQUESTED' in m:
                    self.processTransactionRequest([k,m]) 
                    
                elif 'BANK_SESSION_START_REQUESTED' in m:
                    #here need to fire up a stcppipe ready for the
                    #proxying
                    self.processBankSessionRequest([k,m])
                
    
    #This function should be called when any TRANSACTION_REQUEST message
    #is sent. It checks for the existence of another message of the 
    #same type with the same parameters. If found, and the requests are
    #deemed compatible, it will send out
    #a transaction accepted message to both parties.
    #Return values: null return means nothing to do (no matching request)
    #Otherwise return list, first item is 'accept' or 'reject', if 'reject'
    #then reason for rejection is second item
    def processTransactionRequest(request):
        #ID of requesting agent is after the .
        requester = request[0].split('.')[-1]
        #sanity check: make sure the agent is requesting a transaction
        #involving themselves!
        if not requester in request[1]:
            return ['reject','ID of requesting party not found in transaction']
            
        req_msg_data = request[1].split(':')[1].split(',')
        
        response=[]
        for k,m in self.requestStore.iteritems():
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
                                ,req_msg_data[3],state='INITIALISED')
                self.transactions.append(tx)
                
                #create the acceptance message
                message = {tx.uniqID()+'.'+self.escrowID:'TRANSACTION_ACCEPTED:'}
                
                #send acceptance to BOTH parties
                for recipientID in req_msg_data[0:1]:
                    self.sendMessages(message,recipientID)
                    
                #delete any earlier requests matching this
                #counterparty pair from the requestStore (wipe slate clean)
                self.requestStore = \
                [x for x in self.requestStore if req_msg_data[0] in \
                x[1].split(':')[1].split(',') and req_msg_data[1] in \
                x[1].split(':')[1].split(',')]
                
            elif response[0]=='reject':
                #send rejection to both; no need to create a tx object!
                message={'0.'+self.escrowID:'TRANSACTION_REJECTED:'+response[1]}
                for recipientID in req_msg_data[0:1]:
                    self.sendMessages(message,recipientID)
                
                #delete any earlier requests matching this
                #counterparty pair from the requestStore (wipe slate clean)
                self.requestStore = \
                [x for x in self.requestStore if req_msg_data[0] in \
                x[1].split(':')[1].split(',') and req_msg_data[1] in \
                x[1].split(':')[1].split(',')]
                        
            else:
                shared.debug(0,["something seriously wrong here"])
                exit(1)
        else:
            self.requestStore.append(request)
        
            
    def processBankSessionRequest(request):
        response=[]
        #ID of requesting agent is after the .
        requester = request[0].split('.')[-1]
        #sanity check: make sure the agent is requesting a session for a 
        #transaction that (a) they own and (b) is in the correct state
        txID = request[1].split(':')[1]
        
        if txID not in (x.uniqID() for x in self.transactions):
            response =  ['reject','invalid transaction id']
        for t in self.transactions:
            if t.uniqID()==txID:
                buyerID,sellerID = [t.buyerID, t.sellerID] 
                
        response=[]
        for k,m in self.bankSessionRequestStore.iteritems():
            
            #parse the message part; it's just a transaction ID
            msg_data = m.split(':')[1]
            
            #ignore the message that made the request
            if [k,m]==request:
                continue
            #ignore the message if it isn't a session start req
            elif 'BANK_SESSION_START_REQUEST' != m.split(':')[0]:
                continue
            
            
            elif not msg_data==txID:
                continue
            
            else:
                response=['accept']
                break
                
        if response:
            if response[0]=='accept':
                #TODO: two actions are needed: set up a stcppipe for this run
                #and then check that seller's proxy is ready
                #
                
                message = {txID+'.'+self.escrowID:'BANK_SESSION_READY:'}
                
                #send acceptance to both parties involved
                for recipientID in [buyerID,sellerID]:
                    self.sendMessages(message,recipientID)
                    
                #delete any earlier requests matching this
                #counterparty pair from the requestStore (wipe slate clean)
                self.bankSessionRequestStore = \
            [x for x in self.bankSessionRequestStore if x[1].split(':')[1]!=txID]
                
                
            elif response[0]=='reject':
                message={'0.'+self.escrowID:'BANK_SESSION_START_REJECTED:'+response[1]}
                #send rejection to both parties involved
                for recipientID in [buyerID,sellerID]:
                    self.sendMessages(message,recipientID)
                
                #delete any earlier requests matching this
                #counterparty pair from the requestStore (wipe slate clean)
                self.bankSessionRequestStore = \
            [x for x in self.bankSessionRequestStore if x[1].split(':')[1]!=txID]
                        
            else:
                shared.debug(0,["something seriously wrong here"])
                exit(1)
        else:
            self.bankingSessionRequestStore.append(request)
            
            
    def sendMessages(self,messages,recipientID,transaction=None):
        return Msg.sendMessages(messages,recipientID,self.host)
        
    
    #this method collects all messages addressed to this agent
    def collectMessages(self):
        msgs = Msg.collectMessages(self.uniqID())
        if not msgs: 
            return None
        else:
            self.messageBuffer=msgs
            return True
        
    def waitForMessages(self,timeout):
        for x in range(1,timeout):
            if (self.collectMessages()):
                return True
            time.sleep(1)
        shared.debug(1,["Waiting for messages timed out"])
        return False
    
    def messageUserAgent(self,message,agent,transaction=None):
        print " want to send message: \n",message," to agent: ",agent,'\n'
    
    def messageSuperEscrow(self,message,escrow,transaction=None):
        print "sending message or data: \n",message," to super escrow: ",escrow,"\n"
    
    def handleDispute(self,transaction,reason):
        print "Handling dispute: ",reason," for transaction: ",transaction,"\n"
        
        
    def startTransaction(self, transaction,counterparties):
        print "initialising a transaction: ",transaction," with counterparties:"\
            ,counterparties,"\n"
            
    def completeTransaction(self,transaction,counterparty):
        print "completing a transaction: ", transaction," with counterparty:"\
            ,counterparty,"\n"
            
    def abortTransaction(self,transaction,counterparty):
        print "aborting a transaction: ",transaction," with counterparty:"\
            ,counterparty,"\n"
    
    def loadconfig(self):
        self.buyerUserName=g("Escrow","buyer_user")
        self.password=g("Escrow","buyer_pass")
        
    def providePort(self):
        #TODOcode to provide a currently unused port for concurrent transactions
        #this seems like it could be tricky
        #for now, static
        return g("Escrow","escrow_input_port")
