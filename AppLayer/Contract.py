import os
import shared
import time
import hashlib
import json

#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
#the agent class contains all properties and methods general to ALL of
#escrows,buyers,sellers
class Contract(object):
    
    #def __init__(self,buyerBtc,sellerBtc,fiatCcyIso,fiatCcyAmt,btcAmt,\
                 #sellerDepositFee,buyerDepositFee,sellerEscrowFee,\
                 #buyerEscrowFee,paymentSendingDeadline,sellerProxyServiceAgreement,\
                 #buyerBankDetails=None,sellerBankDetails=None,creationDate=None):
    def __init__(self,contractDetailsDict):
        print "instantiating a contract"
        
        #note that the 'btc' fields are addresses for RECEIPT
        #of bitcoins during the protocol. This is to allow
        #all crypto- transactions to occur using pubkeys generated
        #on the fly (which can be nearly entirely hidden from users)
        #while not having the feature-creep of including a wallet
        #in this codebase.
        #self.text={'Buyer BTC Address':buyerBtc,
        #'Seller BTC Address':sellerBtc,
        #'Fiat Currency ISO':fiatCcyIso,
        #'Fiat Currency Amount':fiatCcyAmt,
        #'BTC Amount':btcAmt,
        #'Buyer Bank Details':buyerBankDetails,
        #'Seller Bank Details':sellerBankDetails,
        #'Seller Deposit Fee':sellerDepositFee,
        #'Buyer Deposit Fee':buyerDepositFee,
        #'Seller Escrow Fee':sellerEscrowFee,
        #'Buyer Escrow Fee':buyerEscrowFee,
        #'Bank Wire Sending Deadline':paymentSendingDeadline,
        #'Seller Proxy Service Agreement':sellerProxyServiceAgreement}
        
        self.text = contractDetailsDict
        
        #if this is a new contract, it will
        #not yet have a creation timestamp,
        #in which case, set it now
        #if not creationDate:
            #self.creationDate = int(time.time()) #to the nearest second, since the epoch
        #else:
            #self.creationDate=creationDate        
        
        #hash the contents
        self.textHash=hashlib.md5(self.getContractText()).hexdigest()
        #no signature on creation
        self.isSigned=False
        #allow multiple signatures "appended"
        self.signatures={}    
        
    #the contract object knows nothing about the signing method
    #so both signing and verification have to be done outside
    #'addr' takes role of identity
    def sign(self,addr,signature):
        self.isSigned=True
        if addr in self.signatures.keys():
            return False
        else:
            self.signatures[addr]=signature
            return True
    
    def getContractText(self):
        return json.dumps(self.text)
        
    def __eq__(self, other):
            if self.text == other.text:
                return True
            else:
                return False

