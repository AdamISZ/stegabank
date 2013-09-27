import os
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
        role = transaction.getRole(self.uniqID())
        if role=='invalid':
            return False
        
        #create local directories to store this banking session
        #format of name is: role_txid_'banksession'
        #TODO consider how banking sessions may be first class objects;
        #may need more than one per tx
        runID='_'.join([role,transaction.uniqID(),'banksession'])
        d = shared.makedir([g("Directories",role+'_base_dir'),runID])
        #make the directories for the stcp logs
        new_stcp_dir=shared.makedir([d,'stcp_buyer'])
        
        shared.debug(0,["starting banking session as ",role,"\n"])
        
        #notice that the calls for buyer and seller are very similar
        #but the duplication is safer as there are small, easy to miss differences!
        if role == 'buyer':
            shared.local_command([g("Exepaths","sshpass_exepath"), \
g("Buyer","escrow_ssh_user") +'@'+g("Escrow","escrow_host"),'-P', \
g("Escrow","escrow_ssh_port"), '-pw', g("Buyer","escrow_ssh_pass"),'-N','-L', \
g("Buyer","buyer_stcp_port")+':127.0.0.1:'+g("Escrow","escrow_input_port")],\
    bg=True)
            
            shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
            new_stcp_dir,'-b','127.0.0.1',g("Buyer","buyer_stcp_port"),\
            g("Buyer","buyer_input_port")],bg=True)
            
        else: 
            shared.local_command([g("Exepaths","sshpass_exepath"), \
g("Seller","escrow_ssh_user")+'@'+g("Escrow","escrow_host"),'-P', \
g("Escrow","escrow_ssh_port"), '-pw', g("Seller","escrow_ssh_pass"),'-N','-R',\
g("Escrow","escrow_host")+':'+g("Escrow","escrow_stcp_port")+':127.0.0.1:'\
+g("Seller","seller_input_port")],bg=True)
            
            shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
            new_stcp_dir,'-b','127.0.0.1',g("Seller","seller_stcp_port"),\
            g("Seller","seller_input_port")],bg=True)
         
         #we must return to confirm success in startup of net arch
        return True   
    
    #unused for now
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
        
    
