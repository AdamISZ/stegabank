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
        
        #this standardised way will work if we have only one message
        if transaction:
            messages = {transaction.uniqID()+'.'+self.agent.uniqID():messages.values()[0]}
        
        shared.debug(0,["About to send a message to",recipientID])
        return Msg.sendMessages(messages,recipientID=recipientID)
        
    
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
    
    def getSingleMessage(self,timeout):
        return Msg.getSingleMessage(self.agent.uniqID(),timeout)
        
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
        
        while True:
            smsg = self.getSingleMessage(timeout=1000)
            if not smsg:
                shared.debug(0,["timed out waiting for the transaction accept message"])
                return False
                         
            for k,m in smsg.iteritems():
                if 'TRANSACTION_ACCEPTED:' in m:
                    if 'TRANSACTION_ACCEPTED:'+','.join([tx.buyer,tx.seller,\
                    str(tx.amount),str(tx.price),tx.currency]) in m:
                        #we need to have the same creation time as the escrow
                        #to ensure the same uniqueID; remember Python is pass-by-ref
                        #so this updates the tx object in the calling script
                        tx.creationTime = int(m.split(':')[1].split(',')[-1])
                        tx.state='INITIALISED'
                        shared.debug(1,["Transaction was accepted by escrow."])
                        #the transaction should now be added to the persistent
                        #store;
                        self.agent.transactions.append(tx)
                        self.agent.pT()
                        return True
                    else:
                        shared.debug(0,["message about the wrong transaction:",\
                                k,m,"-ignoring"])
                elif 'TRANSACTION_REJECTED' in m:
                    shared.debug(0,["Our transaction was rejected :( - quitting."])
                    exit(1)
    
    def requestBankSessionStart(self, tx):
        #construct a message to the escrow
        shared.debug(0,["About to request a banking session start"])
        tx_rq_key = tx.uniqID()+'.'+self.agent.uniqID()
        #todo: handle numeric conversions with appropriate accuracy
        tx_rq_msg = {tx_rq_key:'BANK_SESSION_START_REQUEST'}
        self.sendMessages(tx_rq_msg)
        
    def getResponseToBankSessionStartRequest(self,tx):
        accepted=0
        smsg = self.getSingleMessage(timeout=1000)
        if not smsg:
            shared.debug(0,["timed out waiting for the bank session start accept message"])
            exit(1)
        
        for k,m in smsg.iteritems():
            if 'BANK_SESSION_START_ACCEPTED' in m and tx.uniqID() in k:
                accepted=1
            elif 'BANK_SESSION_START_REJECTED' in m and tx.uniqID() in k:
                accepted=-1
                
        if accepted==-1:    
            shared.debug(0,["Our bank session was rejected :( - quitting."])
            exit(1)    
        elif accepted==1:
            shared.debug(1,["Bank session was accepted by escrow."])
            tx.state='IN_PROCESS'
            self.agent.pT()
            return True
            
        if not accepted:
            shared.debug(0,["Failed to get the bank session response after a long wait."])
            return False
        
    def waitForBankingSessionEnd(self,tx):
        while True:
            smsg = self.getSingleMessage(1000)
            if not smsg:
                shared.debug(0,["timed out waiting for the bank session ended message"])
                return False
            #put a bit more error checking here
            shared.debug(0,["Got this message:",smsg])
            for k,m in smsg.iteritems():
                if 'BANK_SESSION_ENDED' in m:
                    return True
    
    #this message is to be used by buyers only
    def sendConfirmationBankingSessionEnded(self,tx):
        #sanity check
        if tx.getRole(self.agent.uniqID()) != 'buyer':
            shared.debug(0,["Error: user agent:",self.agent.uniqID(),\
        "is not the buyer for this transaction and so can't confirm the end",\
            "of the banking session!"])
            
        #construct a message to the escrow
        shared.debug(0,["Sending bank session end confirm to seller and escrow"])
        tx_rq_key = tx.uniqID()+'.'+self.agent.uniqID()
        #todo: handle numeric conversions with appropriate accuracy
        tx_rq_msg = {tx_rq_key:'BANK_SESSION_ENDED'}
        for recipient in [self.uniqID,tx.seller]:
            self.sendMessages(tx_rq_msg,recipient)
    
    def sendInitiateL1DisputeRequest(self, tx):
        msg = {tx.uniqID()+'.'+self.agent.uniqID():'DISPUTE_L1_REQUEST'}
        self.sendMessages(msg)
    
    def waitForSSLDataRequest(self, tx):
        accepted=0
        while True:
            smsg = self.getSingleMessage(timeout=100)
            if not smsg:
                continue
            shared.debug(0,["Got a message requesting data"])
            for k,m in smsg.iteritems():
                shared.debug(0,["Heres the message:",k,m])
                if 'SSL_DATA_REQUEST' in m and tx.uniqID() in k:
                    return True
        
    def getL1Adjudication(self,tx):
        while True:
            amsg = self.getSingleMessage(timeout=1000)
            if not amsg:
                continue
            for k,m in amsg.iteritems():
                if 'DISPUTE_L1_ADJUDICATION_FAILURE' in m:
                    shared.debug(0,["The escrow-oracle failed to reach a",\
    "decision. The case has been elevated to human escrow adjudication."])
                    return ['no result','adjudication failure']
                elif 'DISPUTE_L1_ADJUDICATION' in m:
                    shared.debug(0,["The escrow-oracle successfully reached",\
    "a decision and made an award."])
                    return m.split(':')[-1].split(',')