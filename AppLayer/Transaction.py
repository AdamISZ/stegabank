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
        self.buyer = contract.text['Buyer BTC Address']
        self.seller = contract.text['Seller BTC Address']
        
        #state machine described above
        self.state = state
        
        #for waiting for deadlines
        self.deadline=None
        
        #script needed for signing OUTBOUND 
        #transactions from this address        
        self.msigAddr = None
        self.mscript = None
        
        self.CNEDepositAddr = multisig.pubtoaddr(g("Escrow","escrow_pubkey"))
        
        #locally stored key file with all keys for this transaction
        #set by buyer only at end of banking session
        self.keyFile=''
        
        #transaction hash that the seller claims provides his side of the trade
        self.sellerFundingTransactionHash=None
        
        #hash of the transaction containing buyer and seller's
        #initial deposit and fees. Passed into RE by CNE.
        self.depositHash = None
        
        #record of the publically chosen RE for this tx
        self.chosenEscrow = None
        
        #record of the escrow on which contract negotiation was performed
        self.CNE = None
        
        #to be set once all signatures  have been applied; gives a unique identity
        self.signatureCompletionTime=None
        
    #functions as a name for the transaction; note a transaction
    #object cannot be instantiated without a contract, and is not
    #defined completely until the date of signatures is marked
    def uniqID(self):
        if not self.signatureCompletionTime:
            raise Exception("Transaction is not well defined without all signatures")
        return hashlib.md5(self.contract.textHash+str(self.signatureCompletionTime)).hexdigest()
    
    def setDeadline(self, timePeriod):
        self.deadline = int(time.time())+timePeriod
    
    def timedOut(self):
        if int(time.time())>self.deadline:
            self.deadline=None
            return True
        return False
    
    def getCtrprtyPubkey(self, c):
        addr = self.buyer if c else self.seller
        msg = self.contract.getContractTextOrdered()
        for sig in self.contract.signatures.values():
            pub = multisig.ecdsa_recover(msg,sig)
            if addr==multisig.pubtoaddr(pub):
                return pub
                
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

        
    
        
