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
        shared.debug(0,["\n instantiating a contract \n"])
        self.text = contractDetailsDict 
        #hash the contents
        self.setHash()
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
    
    #output JSON for messaging
    def getContractText(self):
        return json.dumps(self.text)
    
    #output the contents in a deterministic
    #order for signing
    def getContractTextOrdered(self):
        a = []
        for k,v in sorted(self.text.iteritems()):
            a.extend([k,v])
        #curious bug; without 'str', this gives a ascii/unicode error!?
        return str(','.join(a))
    
    #callers can only modify like this!
    def modify(self,param,val):
        self.text[param]=val
        self.setHash()
    
    def setHash(self):
        self.textHash = hashlib.md5(self.getContractTextOrdered()).hexdigest()
        
    def __eq__(self, other):
            if self.text == other.text:
                return True
            else:
                return False

