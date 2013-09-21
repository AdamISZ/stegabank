import shared
import time
#for brevity
def g(x,y):
    return shared.config.get(x,y)

#I suspect transactions should be instantiated on the escrow only,
#so as to have a unique timestamp, and then propagated to the counterparties.
#state machine: UNINITIALISED|INITIALISED|IN_PROCESS|IN_DISPUTE|COMPLETE|ABORTED
class Transaction():

    #separate multisig address per transaction
    multisig_address=''
    
    def __init__(self,buyer,seller,escrow,amount,price):
        print "instantiating a transaction"
        self.state = 'UNINITIALISED'
        self.buyer=buyer
        self.seller=seller
        self.escrow=escrow
        self.amount=amount
        self.price=price #need to consider fiat currency: TODO
        self.buyerBTCAddress = buyer.getBTCAddress()
        self.sellerBTCAddress = seller.getBTCAddress()
        self.escrowBTCAddress = escrow.getBTCAddress()
        self.multisigAddress = requestMultisigAddress()
        self.creationTime = time.time()
        self.state = 'INITIALISED'
        
    def requestMultisigAddress(self):
        print "creating a multisig address for transaction: \n",self
    
    #serves for serialization, messaging and debugging, hopefully!
    def __str__(self):
        return [self.buyerBTCAddress,self.sellerBTCAddress,self.escrowBTCAddress\
                ,self.multisigAddress,self.creationTime,self.state,self.amount\
                    ,self.price]
        
    
        
