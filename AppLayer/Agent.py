import shared
import pickle
import hashlib
import pika
from NetUtils import *
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
        tmp = pickle.load('transactions.p','rb')
        self.transactions=tmp if tmp else []
        
    def initialiseNetwork(self):
        print "setting up network architecture"
        
   
    
    #this is either really cool or completely stupid
    def uniqID(self):
        return hashlib.md5(__repr__(self)).hexdigest()
    
    def __repr__(self):
        string_rep=[]
        for key, value in self.__dict__.iteritems():
            string_rep.append(str(key)+'='+str(value))
        
        return '^'+'|'.join(string_rep)+'^'