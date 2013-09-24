import shared
import time
#for brevity
def g(x,y):
    return shared.config.get(x,y)

#I suspect transactions should be instantiated on the escrow only,
#so as to have a unique timestamp, and then propagated to the counterparties.
#state machine: INVALID|UNINITIALISED|INITIALISED|IN_PROCESS|IN_DISPUTE|COMPLETE|ABORTED
class Transaction():
    
    def __init__(self,buyer,seller,amount,price):
        print "instantiating a transaction"
        self.state = 'UNINITIALISED'
        self.buyer=buyer
        self.seller=seller
        #self.escrow=escrow
        self.amount=amount
        self.price=price #need to consider fiat currency: TODO
        self.buyerBTCAddress = ''#buyer.getBTCAddress()
        self.sellerBTCAddress = ''#seller.getBTCAddress()
        self.escrowBTCAddress = ''#escrow.getBTCAddress()
        self.multisigAddress = ''#requestMultisigAddress()
        self.creationTime = time.time()
        self.state = 'INITIALISED'
        
    def requestMultisigAddress(self):
        print "creating a multisig address for transaction: \n",self
    
    #this is either really cool or completely stupid
    def uniqID(self):
        return hashlib.md5(__repr__(self)).hexdigest()
        
    #serves for serialization, messaging and debugging, hopefully!
    def __repr__(self):
        string_rep=[]
        for key, value in self.__dict__.iteritems():
            string_rep.append(str(key)+'='+str(value))
        
        return '|'.join(string_rep)
        
    
        
