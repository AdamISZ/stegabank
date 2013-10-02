import os
import shutil
import shared
import Agent
import NetworkAudit.sharkutils as sharkutils
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
        
        #store the location used for the NSS key log file
        self.keyFile=g("Directories","ssl_keylog_file")
        
    def startBankingSession(self,transaction):
        role = transaction.getRole(self.uniqID())
        if role=='invalid':
            shared.debug(0,["Trying to start a banking session but we're not"
                            "buyer or seller for the transaction!"])
            return False
        
        #wipe clean the keylog file
        #remove pre-existing ssl key file so we only load the keys for this run
        #TODO: make sure the user has set the ENV variable - pretty disastrous
        #otherwise!
        if role=='buyer':
            shared.silentremove(self.keyFile)
        
        #create local directories to store this banking session
        #format of name is: role_txid_'banksession'
        #TODO consider how banking sessions may be first class objects;
        #may need more than one per tx
        runID='_'.join([role,transaction.uniqID(),'banksession'])
        d = shared.makedir([g("Directories",role+'_base_dir'),runID])
        #make the directories for the stcp logs
        new_stcp_dir=shared.makedir([d,'stcplog'])
        
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
    
    def endBankingSession(self,transaction):
        role = transaction.getRole(self.uniqID())
        if role=='buyer':
            #copy the premaster secrets file into the testing directory
            #so that it can be decrypted at a later stage by the buyer
            runID='_'.join([role,transaction.uniqID(),'banksession'])
            key_file_name = os.path.join(g("Directories",role+'_base_dir'),\
                                         runID,runID+'.keys')
            shutil.copy2(self.keyFile,key_file_name)
            transaction.keyFile = key_file_name
            self.transactionUpdate(tx=transaction,new_state='IN_PROCESS')
    
    #this method is at useragent level only as it's only for buyers
    #see details in sharkutils.get_magic_hashes
    def getMagicHashList(self, tx):
        if (tx.getRole(self.uniqID()) != 'buyer'):
            shared.debug(0,["Error! You cannot send the magic hashes unless"\
                            "you\'re the buyer!"])
            exit(1)
            
        stcpdir = os.path.join(g("Directories","buyer_base_dir"),\
                        '_'.join(["buyer",tx.uniqID(),"banksession"]),"stcplog")
        shared.debug(0,["Trying to find any magic hashes located in:",\
                    stcpdir,"using ssl decryption key:",tx.keyFile])
        return sharkutils.get_magic_hashes(stcpdir,tx.keyFile,\
                                        port=g("Buyer","buyer_stcp_port"))
        
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
        
    
