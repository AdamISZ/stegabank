import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class EscrowAgent(Agent):
    
    def __init__(self):
        print "instantiating an escrow agent"
        
    def messageUserAgent(self,message,agent,transaction=None):
        print " want to send message: \n",message," to agent: ",agent,'\n'
    
    def messageSuperEscrow(self,message,escrow,transaction=None):
        print "sending message or data: \n",message," to super escrow: ",escrow,"\n"
    
    def handleDispute(self,transaction,reason):
        print "Handling dispute: ",reason," for transaction: ",transaction,"\n"
        
    def startTransaction(self, transaction,counterparties):
        print "initialising a transaction: ",transaction," with counterparties:"\
            counterparties,"\n"
            
    def completeTransaction(self,transaction,counterparty):
        print "completing a transaction: ", transaction," with counterparty:"\
            counterparty,"\n"
            
    def abortTransaction(self,transaction,counterparty):
        print "aborting a transaction: ",transaction," with counterparty:"\
            counterparty,"\n"
