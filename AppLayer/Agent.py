import os
import shared
import pickle
import hashlib
import threading
import Messaging.MessageWrapper as Msg
from multisig_lspnr import multisig
#import multisig_lspnr.multisig as multisig
#import NetworkAudit.sharkutils as sharkutils
#for brevity
def g(x,y):
    return shared.config.get(x,y)

tdbLock = threading.Lock()

#the agent class contains all properties and methods general to ALL of
#escrows,buyers,sellers
class Agent(object):
    
    def __init__(self, basedir='',btcadd='',currency='USD'):
        print "instantiating an agent"
        #all agents must have a base directory for storing data
        self.baseDir = basedir
        #all agents must register a bitcoin address
        self.btcAddress = btcadd
        #all agents must have a default currency as numeraire for btc price
        self.baseCurrency = currency
        #all agents should store their OS details for communication with other agents
        self.OS = shared.OS
        #all agents have to be able to set up simple tcp pipes
        self.stcppipe_proc=None
        #persistent store of incomplete transactions connected to this agent;
        #initially empty
        self.reloadTransactions()
        

    def getEscrowList(self):
            eL = g("Escrow","escrow_list").split(',')
            y=[]
            for i,x in enumerate(eL):
                d = x.split('|')
                y.append({'host':d[1]})
                y[i]['pubkey']=d[2]
                y[i]['id']=d[0]
            shared.debug(4,["Generated this escrow list:",y])
            return y 
    
    def reloadTransactions(self):
        tdbLock.acquire()
        try:
            self.txFile = os.path.join(self.baseDir,'transactions'+self.btcAddress+'.p')
            if os.path.exists(self.txFile):
                with open(self.txFile) as txf:
                    self.transactions = pickle.load(txf)
            else:
                self.transactions=[]
        finally:
            tdbLock.release()
            
        
    def transactionUpdate(self, full=False, txID='',tx=None,new_state=''):
        '''To ensure correct persistence, transaction states can only be updated
            via this method.
            If full is set, we just persist the current list with no changes.
            Otherwise, the transaction can be set either with a tx object
            or an ID. The new state should be defined (see Transaction.Transaction)
            if it's not, the transaction will be deleted from the store '''       
        
        #a little error checking:
        if new_state:
            try:
                new_state = int(new_state)
            except:
                shared.debug(0,["Critical error: we tried to update a transaction",\
                                "to a non-integer state! Quitting."])
                exit(1)
                
        tdbLock.acquire()
        try:    
            if not full:
                if not tx:
                    if not txID:
                        raise Exception("you called transactionUpdate without"+\
                                    "specifying a transaction! Doh!")
                    tx = self.getTxByID(txID)
                
                index = next((i for i in range(0,len(self.transactions)) \
                        if self.transactions[i].uniqID()==tx.uniqID()),None)
                shared.debug(0,["Set index to:",index,"for transaction:",tx.uniqID()])
                #bugfix 6 Oct; zero counts as false!!
                if index is None: #means this is a new transaction; add it
                    self.transactions.append(tx)
                    if not new_state:
                        raise Exception("You cannot add a transaction with no state!")
                    self.transactions[len(self.transactions)-1].state=new_state
                else:
                    if not new_state:
                        #get rid of it
                        del self.transactions[index]
                    else:
                        #update the state
                        shared.debug(0,["Updating transaction state to",new_state])
                        self.transactions[index].state = new_state
            
            #persist to file - note that persistence is definitely necessary,
            #but of course this primitive file-as-database would not really
            #be acceptable except for the fact that performance is not an issue.
            #TODO need to review whether system crash makes this unacceptable;
            #transfer to simple mysql database or something like that 
            with open(self.txFile,'w') as f:
                pickle.dump(self.transactions,f)
                shared.debug(0,["Dumped contents of transaction to file"])
        finally:
            tdbLock.release()
            
    #print out all transactions, indexed, to stdout
    def printCurrentTransactions(self):
        print "**Current Transactions in your transaction store:**"
        for i in range(0,len(self.transactions)):
            print "[",str(i),"] - ",self.transactions[i].uniqID(),\
            "Buyer:",self.transactions[i].buyer,"Seller:",\
            self.transactions[i].seller, "Current state:", \
            self.transactions[i].state
    
    #self-expl
    def getTxByID(self,txID):
        if not self.transactions:
            return None
        else:
            match = [x for x in self.transactions if x.uniqID()==txID]
            if not match:
                return None
            else:
                return match[0]
    
    def getTxByIndex(self,index):
        return self.transactions[index]
    
    #keeping this as simple as possible - will return None if data wasn't collected
    def getHashList(self, tx):
        role = tx.getRole(self.uniqID())
        #TODO: this may be unsafe
        if role=='invalid':
            role='escrow'
        bds = 'escrow_base_dir' if role=='escrow' else 'agent_base_dir'
            
        hash_location = os.path.join(g("Directories",bds),\
                        '_'.join([role,tx.uniqID(),"banksession"]),"stcplog")
        shared.debug(0,["Trying to find the hashes in this directory:",hash_location])
        if role=='escrow':
            return sharkutils.get_all_ssl_hashes_from_capfile(hash_location,\
        stcp_flag=True,port=g("Escrow",'escrow_stcp_port'))
        else:
            return sharkutils.get_all_ssl_hashes_from_capfile(hash_location,\
        stcp_flag=True,port=g("Agent",'agent_stcp_port'))
        
    def initialiseNetwork(self):
        print "setting up network architecture"
                  
    def uniqID(self):
        return self.btcAddress

#========MESSAGING FUNCTIONS======================                   
    def sendMessage(self,msg,recipientID=None,txID=None,chanIndex=0):
        '''wrapper function for sending messages
        to a counterparty. Not all messages have an associated
        transactionid, so that is allowed to be null and is
        replaced by '0'. If recipientID is not set, it defaults
        to the active escrow. A signature of the value of the 
        single dict entry is appended to the value after the last ';'
        as identity authorization.
        '''
        if not txID:
            txID='0'
        if not recipientID:
            #TODO fix
            recipientID = g("Escrow","escrow_id")
        text,sig = multisig.signText(self.uniqID(),':'.join(msg.split(':')[1:]))
        
        newMsg = {}
        newMsg[txID+'.'+self.uniqID()]=msg+';'+sig
        Msg.sendMessages(newMsg,recipientID,chanIndex) 
    
    def sendExternalMessages(self,host,messages={},recipientID='',transaction=None,chanIndex=0):
        #TODO set up the external amqp connection
        #For testing, both escrows on same MQ server
        self.sendMessage(messages,recipientID,transaction,chanIndex)
            
    def getSingleMessage(self,timeout=1,chanIndex=0):
        msg = Msg.getSingleMessage(self.uniqID(),timeout,chanIndex)
        if not msg:
            shared.debug(5,["Message layer returned none"])
            return None
        #all messages from clients must be verified
        sendingID = msg.keys()[0].split('.')[1]
        #retrieve pubkey
        msgInner = ';'.join(':'.join(msg.values()[0].split(':')[1:]).split(';')[:-1])
        sig = ':'.join(msg.values()[0].split(':')[1:]).split(';')[-1]
        addr = multisig.pubtoaddr(multisig.ecdsa_recover(msgInner,sig))
        
        if not addr == sendingID:
            #don't add anything but failure to message to prevent leaks
            shared.debug(0,["Verification failure",sendingID,chanIndex])
            self.sendMessage({msg.keys()[0]:'VERIFICATION_FAILED:'},sendingID,chanIndex)
            return None
        else:
            #having checked the message signature, dispose of it
            v = ';'.join(msg.values()[0].split(';')[:-1])
            msg = {msg.keys()[0]:v}
            shared.debug(4,["Returning this message:",msg])
            return msg    
