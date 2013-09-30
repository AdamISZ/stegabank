import os
import shared
import pickle
import hashlib
import NetworkAudit.sharkutils as sharkutils
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
        #all agents must register a bitcoin address
        self.BTCAddress = btcadd
        #all agents must have a default currency as numeraire for btc price
        self.baseCurrency = currency
        #all agents should store their OS details for communication with other agents
        self.OS = shared.OS
        #persistent store of incomplete transactions connected to this agent;
        #initially empty
        txfile = os.path.join(self.baseDir,'transactions.p')
        if os.path.exists(txfile):
            with open(txfile) as txf:
                self.transactions = pickle.load(txf)
        else:
            self.transactions=[]
        self.printCurrentTransactions()
    
    #To ensure correct persistence, transaction states can only be updated
    #via this method. The transaction can be set either with a tx object
    #or an ID. The new state should be defined (see Transaction.Transaction)
    #if it's not, the transaction will be deleted from the store
    #TODO a bit more error handling - cannot hand a txID with a new tx!
    def transactionUpdate(self, txID='',tx=None,new_state=''):
        if not tx:
            if not txID:
                raise Exception("you called transactionUpdate without specifying a transaction! Doh!")
            tx = filter(lambda a: a.uniqID()==txID,self.transactions)[0]

        index = next((i for i in range(0,len(self.transactions)) \
                if self.transactions[i].uniqID()==tx.uniqID()),None)
        
        if not index: #means this is a new transaction; add it
            self.transactions.append(tx)
            if not new_state:
                raise Exception("You cannot add a transaction with no state!")
            self.transactions[len(self.transactions)-1].state=new_state
        else:
            if not new_state:
                #get rid of it
                del self.transactions[index]
                #self.transactions = [x for x in self.transactions if x != self.transactions[index]]
            else:
                #update the state
                self.transactions[index].state = new_state
        
        #persist to file - note that persistence is definitely necessary,
        #but of course this primitive file-as-database would not really
        #be acceptable except for the fact that performance is not an issue.
        #TODO need to review whether system crash makes this unacceptable;
        #transfer to simple mysql database or something like that 
        with open(os.path.join(self.baseDir,'transactions.p'),'w') as f:
            pickle.dump(self.transactions,f)
            shared.debug(0,["Dumped contents of transaction to file"])
            
            
    #print out all transactions, indexed, to stdout
    def printCurrentTransactions(self):
        print "**Current Transactions in your transaction store:**"
        for i in range(0,len(self.transactions)):
            print "[",str(i),"] - ",self.transactions[i].uniqID(),\
            "Buyer:",self.transactions[i].buyer,"Seller:",self.transactions[i].seller
        
    #keeping this as simple as possible - will return None if data wasn't collected
    def getHashList(self, tx):
        role = tx.getRole(self.uniqID())
        #TODO: this may be unsafe
        if role=='invalid':
            role='escrow'
        hash_location = os.path.join(g("Directories",role+"_base_dir"),\
                        '_'.join([role,tx.uniqID(),"banksession"]),"stcplog")
        shared.debug(0,["Trying to find the hashes in this directory:",hash_location])
        return sharkutils.get_all_ssl_hashes_from_capfile(hash_location,\
        stcp_flag=True,port=g(role.title(),'_'.join([role,'stcp','port'])))

        
    def initialiseNetwork(self):
        print "setting up network architecture"
                  
    def uniqID(self):
        return self.BTCAddress

#after a lot of messing about I decided to stick with just ID=bitcoin address    
''' __repr__(self):
        string_rep = ['dir':self.baseDir,'btcadd':self.btcadd,'currency':self.baseCurrency]
        for property in [self.baseDir,self.btcadd,self.baseCurrency]
        string_rep.append(str(key)+'='+str(value))
        
        return '^'+'|'.join(string_rep)+'^' '''