import shared
import Agent
#for brevity
def g(x,y):
    return shared.config.get(x,y)

#this object runs on the escrow server
class EscrowAgent(Agent.Agent):
    
    def __init__(self):
        
        #first thing is to have a port available for messaging
        self.messagingPort = g("Escrow","escrow_messaging_port")
        shared.debug(1,[\
        "instantiating an escrow agent, listening for messages on port:"\
        ,self.messagingPort])
        
        #start a messaging server in a new thread
        self.messagingConnection = \
        pika.BlockingConnection(pika.ConnectionParameters('127.0.0.1'))
        
        #put code here to load transactions from permanent storage
        self.transactions = [] 
        
    def run(self):
        
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
