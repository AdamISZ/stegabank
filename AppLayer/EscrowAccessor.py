import shared
import time
import Messaging
from AppLayer.Agent import Agent
from AppLayer.Transaction import Transaction
from AppLayer.UserAgent import UserAgent
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class EscrowAccessor(Agent):
    #note that certain information will have to be retrieved to access escrow
    def __init__(self,agent,host='',username='',password='',port='',escrowID=''):
        print "instantiating a remote escrow accessor"
        self.agent = agent #this is the user agent who is using this accessor
        self.host = host
        #TODO:need to consider how to securely transfers logins to 
        #people who need it
        self.userName=username
        self.password=password
        self.accessPort=port
        self.uniqID = escrowID
        
        #at start up of connection with escrow, our message buffer 
        #will be empty. it has form {'transactionid.agentid':message}
        self.messageBuffer={}
        
    def sendMessages(self,messages=[],recipientID='',transaction=None):
        recipientID = self.uniqID if recipientID == '' else recipientID
        return Msg.sendMessages(messages,recipientID,self.host)
        
    
    #this method collects all messages addressed to the user specified
    #by recipientID (which should be the useragent id who owns this accessor)
    def collectMessages(self):
        msgs = Msg.collectMessages(self.agent.uniqID())
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
    
    
    def requestTransaction(buyer,seller,amount,price):
        #construct a message to the escrow
        tx_rq_key = '0.'+self.agent.uniqID()
        #todo: handle numeric conversions with appropriate accuracy
        tx_rq_msg = {tx_rq_key:'TRANSACTION_REQUEST:'+','.join(buyer,seller,\
                                                    str(amount),str(price))}
                                                               
        Msg.sendMessages(tx_rq_msg)
        
    
    
    def getLogin(self):
        return [self.host,self.userName,self.password,self.accessPort]
        
        
    def getReponseToTxnRq(tx):
        
        accepted=0
        for i in range(1,10):
            if escrow.waitForMessages(10): break
        
        for k,m in self.messageBuffer.iteritems():
            if 'TRANSACTION_ACCEPTED' in m and tx.uniqID() in k:
                accepted=1
            elif 'TRANSACTION_REJECTED' in m and tx.uniqID() in k:
                accepted=-1
                
        if accepted==-1:    
            shared.debug(0,["Our transaction was rejected :( - quitting."])
            exit(1)    
        elif accepted==1:
            shared.debug(1,["Transaction was accepted by escrow."])
            return True
            
        if not accepted:
            shared.debug(0,["Failed to get the tx message after a long wait."])
            return False
        
        

            
        
        