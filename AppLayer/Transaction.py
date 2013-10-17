import shared
import time
import hashlib
#for brevity
def g(x,y):
    return shared.config.get(x,y)

#I suspect transactions should be instantiated on the escrow only,
#so as to have a unique timestamp, and then propagated to the counterparties.
#state machine: see AppLayer/TransactionStateMap.txt
class Transaction():
    
    def __init__(self,buyerID,sellerID,amount,price,currency,state=1):
        print "instantiating a transaction"
        
        self.buyer=buyerID
        self.seller=sellerID
        
        #self.escrow=escrow
        self.amount=amount
        self.price=price #need to consider fiat currency: TODO
        self.currency=currency
        
        #?
        self.escrowBTCAddress = ''#escrow.getBTCAddress()
        
        self.multisigAddress = ''#requestMultisigAddress()
        
        #This was removed from initialisation for the following reason:
        #we need to maintain state of uninitialised transactions to prevent
        #buyer and seller having to synchronize in creating it. This means
        #we want to set the creation time to the time when both agreed.
        self.creationTime = ''
        
        #state machine described above
        self.state = state
        
        #locally stored key file with all keys for this transaction
        #set by buyer only at end of banking session
        self.keyFile=''
        
        #hashes used for dispute TODO: probably not practical, 
        #should be a pointer not an actual data set
        self.buyerHashes = []
        self.magicHashes = []
        self.sellerHashes=[]
        
    def initialize(self):
        self.creationTime=int(time.time()) #to the nearest second, since the epoch
            
    def requestMultisigAddress(self):
        print "creating a multisig address for transaction: \n",self
    
    #Need timestamp to ensure uniqueness for fully instantiated txns
    def uniqID(self):
        if self.creationTime:
            return hashlib.md5(self.seller+self.buyer+str(self.creationTime)).hexdigest()
        else:
            return hashlib.md5(self.seller+self.buyer).hexdigest()
    
    def getRole(self,agentID):
        if agentID==self.buyer: return 'buyer'
        elif agentID==self.seller: return 'seller'
        else: return 'invalid'
        
    def __eq__(self, other):
        if self.state == other.state and \
        self.buyer == other.buyer and \
        self.seller== other.seller and \
        self.amount == other.amount and \
        self.price == other.price and \
        self.currency == other.currency and \
        self.multisigAddress == other.multisigAddress and \
        self.creationTime == other.creationTime:
            return True
        else:
            return False
        
    '''    
    #serves for serialization, messaging and debugging, hopefully!
    def __repr__(self):
        string_rep=[]
        for key, value in self.__dict__.iteritems():
            string_rep.append(str(key)+'='+str(value))
        
        return '|'.join(string_rep)'''
        
    
        
