import shared
import time
import hashlib
#for brevity
def g(x,y):
    return shared.config.get(x,y)

#I suspect transactions should be instantiated on the escrow only,
#so as to have a unique timestamp, and then propagated to the counterparties.
#state machine: INVALID|UNINITIALISED|INITIALISED|IN_PROCESS|IN_DISPUTE|COMPLETE|ABORTED
class Transaction():
    
    def __init__(self,buyerID,sellerID,amount,price,currency,state='UNINITIALISED'):
        print "instantiating a transaction"
        self.state = state
        self.buyer=buyerID
        self.seller=sellerID
        #self.escrow=escrow
        self.amount=amount
        self.price=price #need to consider fiat currency: TODO
        self.currency=currency
        #?
        self.escrowBTCAddress = ''#escrow.getBTCAddress()
        self.multisigAddress = ''#requestMultisigAddress()
        #
        self.creationTime = int(time.time())
        self.state = state
        
    def requestMultisigAddress(self):
        print "creating a multisig address for transaction: \n",self
    
    #Need timestamp to ensure uniqueness
    def uniqID(self):
        return hashlib.md5(self.seller+self.buyer+str(self.creationTime)).hexdigest()
    
    def getRole(self,agentID):
        if agentID==self.buyer: return 'buyer'
        elif agentID==self.seller: return 'seller'
        else: return 'invalid'
    '''    
    #serves for serialization, messaging and debugging, hopefully!
    def __repr__(self):
        string_rep=[]
        for key, value in self.__dict__.iteritems():
            string_rep.append(str(key)+'='+str(value))
        
        return '|'.join(string_rep)'''
        
    
        
