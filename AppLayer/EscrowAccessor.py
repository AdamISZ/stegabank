import shared
import time
import pickle
import Messaging.MessageWrapper as Msg
from AppLayer.Agent import Agent
from AppLayer.Transaction import Transaction
from AppLayer.UserAgent import UserAgent
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class EscrowAccessor(object):
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
        
        #now we have a clean messsage queue, we can start normal operations
        #starting up an escrow acccessor means you have to synchronize the
        #state of any transactions associated with it
        if not self.synchronizeTransactions():
            #for now this is dealt with ungracefully, but we can do better TODO
            shared.debug(0,["Serious problem, we failed to synchronize transactions"])
            exit(1)
    
    def requestCNESession(escrowid):
        pass
            
    def requestChatSession(ctrpryid):
        pass
            
            
    #Important: it's guaranteed that self.agent has already loaded its 
    #transactions.p database since that action occurs in the Agent constructor.
    #Callers MUST pay attention to return value; if false, the sync failed
    #and we'll have to try again or something.
    def synchronizeTransactions(self):
        if not Msg.chan:
            #connection channel not instantiated; cannot continue
            return False
        
        #make absolutely sure we're not responding to stale data:
        while True:
            msg = self.getSingleMessage()
            if not msg:
                break
            
        self.sendMessages({'0.'+self.agent.uniqID():'TRANSACTION_SYNC_REQUEST:'},\
                          self.uniqID)
        
        while True:
            #wait for response; we don't expect a long wait as it's a low
            #intensity workload for escrow
            msg = self.getSingleMessage()
            
            if not msg:
                #we stay here since we insist on getting a response.
                #in the absence of an up to date transaction list, nothing
                #can proceed
                continue
            
            hdr_and_data = msg.values()[0].split(':')
            
            #in case we got a naughty message without a colon!
            if len(hdr_and_data) != 2:
                shared.debug(0,["Critical error, received data in wrong format!"])
                continue
            
            hdr, data = hdr_and_data
            
            if hdr == 'RE_TRANSACTION_SYNC_COMPLETE':
                break
            
            if hdr != 'RE_TRANSACTION_SYNC_RESPONSE':
                shared.debug(0,["The message server sent a wrong message in the"\
                                "stream of transaction data."])
                continue
            
            if not data:
                #there were no pre-existing transactions
                return True
            #load as ascii string; docs promise it works
            tx = pickle.loads(data)
            
            #in this section we'll break the rule of not updating the tx
            #list directly because we commit at the end.
            if tx.uniqID() in [a.uniqID() for a in self.agent.transactions]:
                #replace old with new
                self.agent.transactions = [tx if x.uniqID()==tx.uniqID() \
                                    else x for x in self.agent.transactions]
                
            else:
                #Completely new transaction, unknown to user.
                #This usually won't happen; it means the useragent has "lost"
                #a transaction object
                shared.debug(0,["We're adding a new one"])
                self.agent.transactions.append(tx)
                
        #finished making changes, persist
        try:
            self.agent.transactionUpdate(full=True)
        except:
            shared.debug(0,["Failure to synchronize transaction list!"])
            return False
        
        #success
        self.agent.printCurrentTransactions()
        
        return True

    def requestTransaction(self,buyer,seller,amount,price,curr):
        #construct a message to the escrow
        shared.debug(0,["About to request a transaction"])
        tx_rq_key = '0.'+self.agent.uniqID()
        #todo: handle numeric conversions with appropriate accuracy
        tx_rq_msg = {tx_rq_key:'TRANSACTION_REQUEST:300,'+','.join([buyer.uniqID(),\
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
                    if ','.join([tx.buyer,tx.seller,\
                    str(tx.amount),str(tx.price),tx.currency]) in m:
                        #we need to have the same creation time as the escrow
                        #to ensure the same uniqueID; remember Python is pass-by-ref
                        #so this updates the tx object in the calling script
                        tx.creationTime = int(m.split(':')[1].split(',')[-1])
                        shared.debug(1,["Transaction was accepted by escrow."])
                        #the transaction should now be added to the persistent
                        #store;
                        self.agent.transactionUpdate(tx=tx,new_state=300)
                        return True
                    else:
                        shared.debug(0,["message about the wrong transaction:",\
                                k,m,"-ignoring"])
                elif 'TRANSACTION_REJECTED' in m:
                    shared.debug(0,["Our transaction was rejected :( - quitting."])
                    return False
    
    def requestBankSessionStart(self, tx):
        #construct a message to the escrow
        shared.debug(0,["About to request a banking session start"])
        #todo: handle numeric conversions with appropriate accuracy
        tx_rq_msg = {'x':'BANK_SESSION_START_REQUEST:'}
        self.sendMessages(tx_rq_msg,transaction=tx,rs=500)
        
    def negotiateBankSession(self,tx):
        accepted=0
        role = tx.getRole(self.agent.uniqID())
        
        smsg = self.getSingleMessage(timeout=1000)
        k,m = smsg.items()[0]
        
        if not smsg:
            debugmsg = \
'Failed to get a response, probably the seller is not ready. Aborting' \
if role=='buyer' else \
'Failed to get a request to start the bank session from buyer, perhaps they\'re not ready.'
            shared.debug(0,[debugmsg])
            return False
        
        if role=='buyer':
            #we were waiting for an accepted/rejected message:
            if 'BANK_SESSION_START_ACCEPTED' in m:
                rspns = shared.get_binary_user_input("Enter Y/y to start banking session",\
                                        'y','y','n','n')
                if rspns != 'y':
                    self.activeEscrow.sendBankingSessionAbortInstruction(tx)
                    rspns = shared.get_binary_user_input("Do you want to abort the "+\
"transaction entirely? If Y/y, the record of the transaction will be erased on"+\
"the remote escrow. If N/n, the transaction will remain in an initialised "+\
"state, waiting for you to conduct the banking session later.",'y','y','n','n')
                    if rspns=='y':
                        self.activeEscrow.sendTransactionAbortInstruction(tx)
                    return False
                else:
                    return True
            elif 'BANK_SESSION_START_REJECTED' in m:
                shared.debug(0,["Bank session start rejected. Try again?"])
                return False
            else:
                shared.debug(0,["Received an unexpected message from the escrow. Ignoring"])
                return False
        else:
            #we wait for a request message, then send a ready message.
            if 'BANK_SESSION_START_REQUEST' in m:
                rspns = shared.get_binary_user_input(\
"Enter Y/y after you have started the proxy server (squid) on your local machine:",\
        'y','y','n','n')
                if rspns != 'y':
                    shared.debug(0,["You have rejected the banking session. "+\
                            "Abort instruction will be sent."])
                    self.activeEscrow.sendBankingSessionAbortInstruction(tx)
                    rspns = shared.get_binary_user_input("Do you want to abort the "+\
"transaction entirely? If Y/y, the record of the transaction will be erased on"+\
"the remote escrow. If N/n, the transaction will remain in an initialised "+\
"state, waiting for you to conduct the banking session later.",'y','y','n','n')
                    if rspns=='y':
                        self.activeEscrow.sendTransactionAbortInstruction(tx)
                    return False
                else:        
                    self.sendMessages(messages={'x':'BANK_SESSION_READY:'},\
                        recipientID=self.uniqID,transaction=tx,rs=500)
                    #seller has at this point made his best effort, he's ready to do
                    #the business
                    return True
            
        #unreachable, should be
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
                    if ':501' in m:
                        return False
                    elif ':502' in m:
                        return True
                    else:
                        shared.debug(0,["Serious error in wait for bank session",\
                                        "end, message format wrong."])
                        return False
                   
    
    #this message is to be used by buyers only
    def sendConfirmationBankingSessionEnded(self,tx,rspns):
        #sanity check
        if tx.getRole(self.agent.uniqID()) != 'buyer':
            shared.debug(0,["Error: user agent:",self.agent.uniqID(),\
        "is not the buyer for this transaction and so can't confirm the end",\
            "of the banking session!"])
            
        #construct a message to the escrow
        shared.debug(0,["Sending bank session end confirm to seller and escrow"])
        tx_rq_key = tx.uniqID()+'.'+self.agent.uniqID()
        #todo: handle numeric conversions with appropriate accuracy
        rs = 502 if rspns=='y' else 501
        tx_rq_msg = {'x':'BANK_SESSION_ENDED:'}
        for recipient in [self.uniqID,tx.seller]:
            self.sendMessages(tx_rq_msg,recipient,transaction=tx,rs=rs)
    
    def sendInitiateL1DisputeRequest(self, tx):
        msg = {tx.uniqID()+'.'+self.agent.uniqID():'DISPUTE_L1_REQUEST:700,'}
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
    
