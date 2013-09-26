import shared
import time
import Messaging.MessageWrapper as Msg
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
        
    def sendMessages(self,messages={},recipientID='',transaction=None):
        recipientID = self.uniqID if recipientID == '' else recipientID
        shared.debug(0,["About to send a message to",recipientID])
        return Msg.sendMessages(messages,recipientID=recipientID,server=self.host)
        
    
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
    
    
    def requestTransaction(self,buyer,seller,amount,price,curr):
        #construct a message to the escrow
        shared.debug(0,["About to request a transaction"])
        tx_rq_key = '0.'+self.agent.uniqID()
        #todo: handle numeric conversions with appropriate accuracy
        tx_rq_msg = {tx_rq_key:'TRANSACTION_REQUEST:'+','.join([buyer.uniqID(),\
                                    seller.uniqID(),str(amount),str(price),str(curr)])}
                                                               
        self.sendMessages(tx_rq_msg)
        
    
    def sendBankingSessionAbortInstruction(self,tx):
        k = tx.uniqID()+'.'+self.agent.uniqID()
        msg = {k:'BANK_SESSION_ABORT'}
        self.sendMessages(msg)
    
    def sendTransactionAbortInstruction(self,tx):
        k = tx.uniqID()+'.'+self.agent.uniqID()
        msg = {k:'TRANSACTION_ABORT'}
        self.sendMessages(msg)
        
    def getLogin(self):
        return [self.host,self.userName,self.password,self.accessPort]
        
    #Note: the transaction object passed as argument is a temporary 
    #structure - it has the wrong creation time and so the wrong unique
    #ID. Hence in this function we check that the fields correspond to 
    #the fields sent from the escrow, then update the creation timestamp
    #before returning it.    
    def getResponseToTxnRq(self, tx):
        
        accepted=0
        for i in range(1,10):
            if self.waitForMessages(10): break
        
        for k,m in self.messageBuffer.iteritems():
            if 'TRANSACTION_ACCEPTED:' in m:
                if 'TRANSACTION_ACCEPTED:'+','.join([tx.buyer,tx.seller,\
                    str(tx.amount),str(tx.price),tx.currency]) in m:
                    accepted=1
                    #we need to have the same creation time as the escrow
                    #to ensure the same uniqueID; remember Python is pass-by-ref
                    #so this updates the tx object in the calling script
                    tx.creationTime = int(m.split(':')[1].split(',')[-1])
                else:
                    shared.debug(0,["something very wrong - transaction accepted with wrong parameters!?"])
                    exit(1)
            elif 'TRANSACTION_REJECTED' in m:
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
    
    def requestBankSessionStart(self, tx):
        #construct a message to the escrow
        shared.debug(0,["About to request a banking session start"])
        tx_rq_key = tx.uniqID()+'.'+self.agent.uniqID()
        #todo: handle numeric conversions with appropriate accuracy
        tx_rq_msg = {tx_rq_key:'BANK_SESSION_START_REQUEST'}
        self.sendMessages(tx_rq_msg)
        
    def getResponseToBankSessionStartRequest(self,tx):
        accepted=0
        for i in range(1,10):
            if self.waitForMessages(10): break
        
        for k,m in self.messageBuffer.iteritems():
            if 'BANK_SESSION_START_ACCEPTED' in m and tx.uniqID() in k:
                accepted=1
            elif 'BANK_SESSION_START_REJECTED' in m and tx.uniqID() in k:
                accepted=-1
                
        if accepted==-1:    
            shared.debug(0,["Our bank session was rejected :( - quitting."])
            exit(1)    
        elif accepted==1:
            shared.debug(1,["Bank session was accepted by escrow."])
            return True
            
        if not accepted:
            shared.debug(0,["Failed to get the bank session response after a long wait."])
            return False

            
        
        