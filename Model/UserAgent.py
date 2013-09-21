import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class UserAgent(Agent):
    #all users must be able to login to the escrow host
    escrow_host_login=[]
    
    def __init__(self):
        print "instantiating a user agent"
        self.escrow=None
        
    def startBankingSession(self,transaction):
        print "starting banking session\n"
    
    def endBankingSession(self,transaction):
        print "ending banking session\n"
    
    def getEscrow(self):
        print "finding escrow\n"
        self.escrow = EscrowAgent()
        
    def connectToEscrow(self,escrow):
        #do stuff
        if (True):
        print "Successfully connected to escrow:",self.escrow,"\n"
        
    def messageCounterparty(self,message,counterparty,transaction=None):
        print " want to send message: \n",message," to agent: ",counterparty,'\n'
    
    def messageEscrow(self,message,escrow,transaction=None):
        print "sending message or data: \n",message," to escrow: ",escrow,"\n"
    
    def raiseDispute(self,transaction,reason):
        print "Raising dispute: ",reason," for transaction: ",transaction,"\n"
        
    def requestTransactionStart(self, transaction,counterparty):
        print "Requesting initialisation of a transaction: ",transaction,\
            " with counterparty:"counterparty,"\n"
            
    def requestTransactionStop(self,transaction,counterparty):
        print "Requestion completion of a transaction: ", transaction,\
        " with counterparty:"counterparty,"\n"
            
    def requestAbortTransaction(self,transaction,counterparty):
        print "Request aborting a transaction: ",transaction," with counterparty:"\
            counterparty,"\n"
