import shared
import Agent
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class UserAgent(Agent.Agent):
    #list of available logins to any UserAgent instance, so class level
    
    
    def __init__(self,basedir,btcaddress,bankinfo,currency):
        
        super(UserAgent,self).__init__(basedir=basedir, btcadd=btcaddress,currency=currency)
        print "instantiating a user agent"
        self.escrows=[]
        #all user agents (not escrows) must provide basic bank info
        #TODO: put validation code that info has correct form
        self.bankInfo=bankinfo
        
        #The active escrow is not yet defined.
        self.activeEscrow = None
        
    def startBankingSession(self,transaction):
        role = 'buyer' if transaction.getRole(self)=='buyer' else 'seller'
        #create a local directory to store this banking session
        #format of name is: role_txid_'banksession'
        #TODO consider how banking sessions may be first class objects;
        #may need more than one
        runID='_'.join(role,transaction.uniqID(),'banksession')
         new_dir = os.path.join(g("Directories",role+'_base_dir',runID)
        if not os.path.exists(new_dir): os.makedirs(new_dir)
        
        shared.debug(0,["starting banking session as ",role,"\n"])
        
        #notice that the calls for buyer and seller are very similar
        #but the duplication is safer as there are small, easy to miss differences!
        if role == 'buyer':
            shared.local_command([g("Exepaths","sshpass_exepath"), \
g("Buyer","buyer_ssh_user") +'@'+g("Escrow","escrow_host"),'-P', \
g("Escrow","escrow_ssh_port"), '-pw', g("Buyer","buyer_ssh_pass"),'-N','-L', \
g("Buyer","buyer_stcp_port")+':127.0.0.1:'+g("Escrow","escrow_input_port")])
            
            shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
            os.path.join(g("Directories","buyer_base_dir",runID,"stcp_buyer"),\
            '-b','127.0.0.1',g("Buyer","buyer_stcp_port"),\
            g("Buyer","buyer_input_port")])
            
        else: 
            shared.local_command([g("Exepaths","sshpass_exepath"), \
g("Seller","seller_ssh_user")+'@'+g("Escrow","escrow_host"),'-P', \
g("Escrow","escrow_ssh_port"), '-pw', g("Seller","seller_ssh_pass"),'-N','-R',\
g("Escrow","escrow_host")+':'+g("Escrow","escrow_stcp_port")+':127.0.0.1:'\
+g("Seller","seller_input_port")])
            
            shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
            os.path.join(g("Directories","buyer_base_dir",runID,"stcp_"+agent),\
            '-b','127.0.0.1',g(agent.title(),agent+"_stcp_port"),\
            g(agent.title(),agent+"_input_port")])
            
    
    def endBankingSession(self,transaction):
        print "ending banking session\n"
    
    def findEscrow(self):
        print "finding escrow\n"
        self.escrow = EscrowAgent()
    
    def addEscrow(self,escrow):
        self.escrows.append(escrow)
        return self
    
    def setActiveEscrow(self,escrow):
        if escrow in self.escrows:
            self.activeEscrow = escrow 
        else:
            raise Exception("Attempted to set active an escrow which is not known to this user agent!.\n")
        return self
    
    def (self,escrow):
        #do stuff
        if (True):
            print "Successfully connected to escrow:",self.escrow,"\n"
        
    def messageCounterparty(self,message,counterparty,transaction=None):
        print " want to send message: \n",message," to agent: ",counterparty,'\n'
        self.activeEscrow.sendMessages(messages=[message],\
            recipient=counterparty,transaction=transaction)
    
    def messageEscrow(self,message,escrow,transaction=None):
        print "sending message or data: \n",message," to escrow: ",escrow,"\n"
    
    def raiseDispute(self,transaction,reason):
        print "Raising dispute: ",reason," for transaction: ",transaction,"\n"
        
    def requestTransactionStart(self, transaction,counterparty):
        print "Requesting initialisation of a transaction: ",transaction,\
            " with counterparty:",counterparty,"\n"
            
    def requestTransactionStop(self,transaction,counterparty):
        print "Requestion completion of a transaction: ", transaction,\
        " with counterparty:",counterparty,"\n"
            
    def requestAbortTransaction(self,transaction,counterparty):
        print "Request aborting a transaction: ",transaction," with counterparty:"\
            ,counterparty,"\n"
