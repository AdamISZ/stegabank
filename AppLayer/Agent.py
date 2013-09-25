import os
import shared
import pickle
import hashlib
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
#this class should be defined as abstract as it must be inherited from
#not sure how to do this in Python
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
        
        
    def initialiseNetwork(self):
        print "setting up network architecture"
        
    
    
    #this is either really cool or completely stupid
    def uniqID(self):
        return hashlib.md5(self.__repr__()).hexdigest()
    
    def __repr__(self):
        string_rep=[]
        for key, value in self.__dict__.iteritems():
            string_rep.append(str(key)+'='+str(value))
        
        return '^'+'|'.join(string_rep)+'^'