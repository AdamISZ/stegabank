import os
import shared
import pickle
import hashlib
#import multisig_lspnr.multisig as multisig
#import NetworkAudit.sharkutils as sharkutils
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
#the agent class contains all properties and methods general to ALL of
#escrows,buyers,sellers
class Agent(object):
    
    def __init__(self, basedir='',btcadd='',currency='USD'):
        print "instantiating an agent"
        #all agents must have a base directory for storing data
        self.baseDir = basedir
        #all agents must register a bitcoin address; this is NOT the btc address used to talk to other parties,
        #but the btc address used to withdraw to outside the app
        self.btcAddress = btcadd
        #all agents must have a default currency as numeraire for btc price
        self.baseCurrency = currency
        #all agents should store their OS details for communication with other agents
        self.OS = shared.OS
        #persistent store of incomplete transactions connected to this agent;
        #initially empty
        self.txFile = os.path.join(self.baseDir,'transactions'+self.btcAddress+'.p')
        if os.path.exists(self.txFile):
            with open(self.txFile) as txf:
                self.transactions = pickle.load(txf)
        else:
            self.transactions=[]

    
    #To ensure correct persistence, transaction states can only be updated
    #via this method.
    #If full is set, we just persist the current list with no changes.
    #Otherwise, the transaction can be set either with a tx object
    #or an ID. The new state should be defined (see Transaction.Transaction)
    #if it's not, the transaction will be deleted from the store
    def transactionUpdate(self, full=False, txID='',tx=None,new_state=''):
        #a little error checking:
        if new_state:
            try:
                new_state = int(new_state)
            except:
                shared.debug(0,["Critical error: we tried to update a transaction",\
                                "to a non-integer state! Quitting."])
                exit(1)
            
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
