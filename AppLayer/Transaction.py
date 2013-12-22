import shared
import time
import hashlib
from multisig_lspnr import multisig

#for brevity
def g(x,y):
    return shared.config.get(x,y)

#I suspect transactions should be instantiated on the escrow only,
#so as to have a unique timestamp, and then propagated to the counterparties.
#state machine: see AppLayer/TransactionStateMap.txt
class Transaction():
    
    def __init__(self,contract,state=1):
        print "instantiating a transaction"
        
        self.contract=contract
        
        #expose these elements of the contract
        #explicitly, because the escrow will need
        #to refer to them often in order to manage
        #the transaction state by use of messaging
        self.buyer = contract.text['Buyer Bitcoin Address']
        self.seller = contract.text['Seller Bitcoin Address']
        
        #state machine described above
        self.state = state
        
        #locally stored key file with all keys for this transaction
        #set by buyer only at end of banking session
        self.keyFile=''
    
    #functions as a name for the transaction; note a transaction
    #object cannot be instantiated without a contract 
    def uniqID(self):
        return self.contract.textHash
    
    
    def getRole(self,agentID):
        if agentID==self.buyer: return 'buyer'
        elif agentID==self.seller: return 'seller'
        else: return 'invalid'
        
    def __eq__(self, other):
        if self.state == other.state and \
        self.contract == other.contract:
            return True
        else:
            return False

        
    
        
