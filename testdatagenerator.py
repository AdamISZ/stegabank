#Script to automatically run test of structure:
#buyer, escrow, seller make connection
#buyer requests some set of website addresses defined in a file
#all network traffic is logged in given run directory
#escrow.py mode 1 is run to verify hash matches, and result is logged.

#++LIBRARY IMPORTS+++++++++
import sys
import shutil
import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import os
import subprocess
import multiprocessing
import helper_startup
import time
import signal
import psutil
#++++++++++++++++++++++++++    

#====GLOBALS=============
run_dir_base={}
buyer_ssh_command=[]
seller_ssh_command=[]
stcp_commands={}
all_commands = []
#========================

#excellent tool based on module psutil;
#will kill all processes in the tree (which on Windows is otherwise impossible)
def killtree(pid, including_parent=True):    
    parent = psutil.Process(pid)
    for child in parent.get_children(recursive=True):
        child.kill()
    if including_parent:
        parent.kill()

def make_imacro(websites,runID):
    
    macro_file = shared.verify_file_creation(os.path.join(imacros_dir,runID+'.iim'),\
                        "Macro file exists",overwrite=True,prompt=False,remove_in_advance=False)
    macro_file_handle = open(macro_file,'w')
    
    #build the lines for the file, starting with header lines
    file_contents = ['VERSION BUILD=8510617 RECORDER=FX',\
                     'SET !REPLAYSPEED SLOW','TAB T=1',\
                     'SET !TIMEOUT_PAGE 180']
    for website in websites:
        shared.debug(1,["writing this website to the macro: ",website])
        file_contents.append('URL GOTO='+website)
        file_contents.append('WAIT SECONDS=25')
    
    #now append footer
    file_contents.extend(['SET !EXTRACT done',\
    'SAVEAS TYPE=EXTRACT FOLDER=C:\\ssllog-master FILE=iSignal.txt'])
    
    for item in file_contents:
        print>>macro_file_handle, item

#function acts as a wrapper for background processes
#which we get by using the multiprocessing (threading implemented at process
# level) module
def run_process(command):
    shared.local_command(command,bg=True)
        

def run_test(runID, websites_to_visit,auto=True):
    
    #create a macro to be called for this run:
    make_imacro(websites_to_visit,runID)
    
    #we fork off subprocesses to do network arch setup
    bg_threads = []
    for command in all_commands:
        print "starting thread for command:",command
        new_thread = multiprocessing.Process(target=run_process,args=[command])
        bg_threads.append(new_thread)
        
    for each_t in bg_threads:
        each_t.start()
        
    #Finished starting "background" processes, which means network configuration
    # is ready now: start firefox, pass it a list of websites to visit
    #separated by some sleep
    print "Now transferring to firefox...\n"
    ffdir = os.path.dirname(g("Exepaths","firefox_exepath"))
    ffname = os.path.basename(g("Exepaths","firefox_exepath"))
    shared.local_command([g("Exepaths","firefox_exepath")],bg=True)
    
    if (auto):
        #This delay was incorporated as per the instructions at the iMacros wiki;
        #it's needed because Firefox must load the add-on completely before we
        #make the call to our individual macro
        time.sleep(15) 
        
        shared.local_command([g("Exepaths","firefox_exepath"),\
                              'imacros://run/?m='+runID+'.iim'],bg=True)

        #wait for imacro to signal us finished
        while not os.path.isfile('iSignal.txt'):
            time.sleep(1)
        #got the signal so remove the signal file
        os.remove('iSignal.txt')
        
        print "Firefox macro finished for run:",runID
    else:
        #here the user will do the work and we wait for firefox to close
        
        while True:
            ff_found=False
            for proc in psutil.process_iter():
                if 'firefox' in proc.name:
                    ff_found = True
                    time.sleep(1)
            if not ff_found: break
        
    
    
def cleanup():
    #once we've finished the run
    #we'll want to shutdown all stcppipes and ssh
    killtree(os.getpid(),including_parent=False)
    #we still need to kill the remote stcppipe
    shared.remote_escrow_command('pkill -SIGTERM stcppipe')
    
    #TODO: shutdown is a total mess but I don't want to spend
    #days and days finding the right methods
    #unfortunately firefox is not in our tree, will have to hunt it down!
    for proc in psutil.process_iter():
        if 'firefox' in proc.name:
            proc.kill()
        if 'plink' in proc.name:
            proc.kill()
        if 'stcppipe' in proc.name:
            proc.kill()        
    
    #allow a little time for OS cleanup
    time.sleep(2)
    print "infrastructure for tests is now shut down.\n"
    
if __name__ == "__main__":
    
    #we need config file loaded
    helper_startup.loadconfig()
    imacros_dir = g("Directories","imacros_dir")
    #define where the run data from stcppipe is going to be stored
    #by using the unique runID which called this script
    runID = sys.argv[1]
    auto = True if sys.argv[2]=='auto' else False
    if runID =='testdatagenerator.py': runID =sys.argv[2]
    if not runID:
        print "runID was not found. Quitting.\n"
        exit()
    
    #remove pre-existing ssl key file so we only load the keys for this run
    key_file=g("Directories","ssl_keylog_file")
    shared.silentremove(key_file)
    
    #read the websites from the filename:
    website_list=[]
    with open(os.path.join(g("Directories",\
        "testing_web_list_dir"),runID)) as f:
        website_list=filter(None,f.read().splitlines())
    
    #make the directories to store the log files
    #logged data will be stored here on the buyer,escrow, and seller
    run_dir_base = {'buyer':g("Directories","buyer_base_dir"),\
                    'seller':g("Directories","seller_base_dir"),\
                    'escrow':g("Directories","escrow_base_dir")}
    #set up the directory structure for the escrow on the remote host
    shared.remote_escrow_command('mkdir '+runID+'; cd '+runID+'; mkdir stcp_escrow')
    new_dir = os.path.join(run_dir_base['buyer'],runID)
    if not os.path.exists(new_dir): os.makedirs(new_dir)
    #Note: in some future test scenario, where buyer and seller
    #have different basedirs, might need to add a line for seller here.
    #Now set up the stcp log directories:
    for dirname in ['stcp_buyer','stcp_seller','stcp_escrow']:
        if not os.path.exists(os.path.join(new_dir,dirname)): 
            os.makedirs(os.path.join(new_dir,dirname))
    
    #We use data defined in the config file to build the buyer and seller
    #port forwarding commands.
    #note that these are special, LOCAL HOST commands to set up a network
    #connection so remote_escrow_command is not the right tool
    #Also note: -N is a useful flag that doesn't instantiate a shell
    buyer_ssh_command = [g("Exepaths","sshpass_exepath"), g("Buyer","buyer_ssh_user") \
    +'@'+g("Escrow","escrow_host"),'-P', g("Escrow","escrow_ssh_port"), '-pw', \
    g("Buyer","buyer_ssh_pass"),'-N','-L', g("Buyer","buyer_stcp_port")+':127.0.0.1:'+\
    g("Escrow","escrow_input_port")]
    all_commands.append(buyer_ssh_command)
    
    seller_ssh_command = [g("Exepaths","sshpass_exepath"), g("Seller","seller_ssh_user") \
    +'@'+g("Escrow","escrow_host"),'-P', g("Escrow","escrow_ssh_port"), '-pw', \
    g("Seller","seller_ssh_pass"),'-N','-R', g("Escrow","escrow_host")+':'\
    +g("Escrow","escrow_stcp_port")+':127.0.0.1:'+g("Seller","seller_input_port")]
    all_commands.append(seller_ssh_command)
    
    #stcppipe commands (note escrow is executed remotely over ssh)
    #the difference here is that these processes block (as well as spew output)
    #so we run them as background threads and call terminate() on these threads
    #after EACH RUN is finished, since they are logging to different runID dirs
    #for each test
    for agent,dir in run_dir_base.iteritems():
        if (agent=='escrow'):
            stcp_commands[agent]=[g("Exepaths","sshpass_exepath"),\
            g("Buyer","buyer_ssh_user")+'@'+g("Escrow","escrow_host"),'-P',\
            g("Escrow","escrow_ssh_port"),'-pw',g("Buyer","buyer_ssh_pass"),\
            'stcppipe -d '+runID+'/stcp_escrow -b 127.0.0.1 ' + \
            g(agent.title(),agent+"_stcp_port")+' ' + \
            g(agent.title(),agent+"_input_port")+ ' > /dev/null 2>&1 &']
            all_commands.append(stcp_commands[agent])
        else:
            stcp_commands[agent]=[g("Exepaths","stcppipe_exepath"),'-d',\
            os.path.join(dir,runID,"stcp_"+agent),'-b','127.0.0.1',\
            g(agent.title(),agent+"_stcp_port"),\
            g(agent.title(),agent+"_input_port")]
            all_commands.append(stcp_commands[agent])
    

    #all is ready; start test
    run_test(runID,website_list,auto=auto)
    
    #now time to gracefully shut down the network arch
    cleanup()
    
    #having run the tests, we need to copy the log files from the
    #remote host to the local host in advance of escrow.py testing
    #Can be achieved using scp
    shared.get_remote_files(runID+'/stcp_escrow',\
            os.path.join(run_dir_base['buyer'],runID,'stcp_escrow'))
    
    #we have all data in stcp_buyer,seller,escrow; we can run the escrow script
    #to check for hash mismatches. All the results are dumped to stdout, which
    #can then be parsed by a wrapper script (and saved to file as appropriate)
    error_in_hash_matching=False
    for role_string in ['xx']:
        command_str = 'escrow.py -r '+role_string+' 1 '+runID
        print "Starting analysis script:",command_str
        if os.system(command_str) != 0:
            error_in_hash_matching = True
    
    #copy the premaster secrets file into the testing directory
    shutil.copy2(key_file,os.path.join(run_dir_base['buyer'],runID,runID+'.keys'))
    #keep a local copy of the definition of this test run
    shutil.copy2(os.path.join(g("Directories","testing_web_list_dir"),runID),\
    os.path.join(run_dir_base['buyer'],runID,runID))
    
    #All processing over; only need to make sure stdout is recorded somewhere!
    print "Test run: ", runID," is complete."
    if error_in_hash_matching: exit(1)
    else: exit(0)
    

