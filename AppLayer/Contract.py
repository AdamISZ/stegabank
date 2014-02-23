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
        shared.debug(5,["\n instantiating a contract \n"])
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
    
    def getContractDetails(self):
        return "Contract:\n"+self.getContractText()+"Signatures:\n"+str(self.signatures)
    
    def getSignature(self,role):
        agent =self.text['Buyer BTC Address'] if role == 'buyer' else self.text['Seller BTC Address']
        if not agent in self.signatures.keys(): return None
        return self.signatures[agent]
    
    def getCounterparty(self,requester):
        buyer,seller = [self.text['Buyer BTC Address'],self.text['Seller BTC Address']]
        if requester not in [buyer,seller]:
            shared.debug(1,["Error, this contract does not contain",requester])
            return None
        ca = buyer if seller==requester else seller 
        return ca        
    
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
    
    def getTotalFees(self,role):
        '''Return total fee to pay
        at CNE in mBTC (float format).
        role must be 'buyer' or 'seller'
        '''
        #all fees parse from btc amount, fiat is ignored
        btc = int(self.text['mBTC Amount'])
        bd = int(self.text['Buyer Deposit Fee'])
        sd = int(self.text['Seller Deposit Fee'])
        bf = int(self.text['Buyer Escrow Fee'])
        sf = int(self.text['Seller Escrow Fee'])
        req_dep = float(g("Escrow","escrow_CNE_deposit"))
        req_txfp = float(g("Escrow","escrow_tx_fee_percent"))        
        if role=='buyer':
            return bd + bf
        elif role=='seller':
            return sd + sf
        else:
            raise Exception("role must be buyer or seller")
        
    def __eq__(self, other):
        if self.text == other.text and isinstance(other,Contract):
            return True
        else:
            return False
        
    def __ne__(self,other):
        return not(self.__eq__)
