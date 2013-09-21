import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
#this class should be defined as abstract as it must be inherited from
#not sure how to do this in Python
class Agent:
    #all agents must have a base directory for storing data
    base_dir=''
    #all agents must register a bitcoin address
    btc_address=''
    #all agents should store their OS details for communication with other agents
    OS = shared.OS
    #persistent store of incomplete transactions connected to this agent
    transactions=[]
    
    def __init__(self):
        print "instantiating an agent"
    
    #this method should be virtual; not sure how to do it in Python
    def initialiseNetwork(self):
        print "setting up network architecture"
        
