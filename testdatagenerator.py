#Script to automatically run test of structure:
#buyer, escrow, seller make connection
#buyer requests some set of website addresses defined in a file
#all network traffic is logged in given run directory
#escrow.py mode 1 is run to verify hash matches, and result is logged.

#++LIBRARY IMPORTS+++++++++
import sys
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
imacros_dir = "C:/Users/AdamISZ/Documents/iMacros/Macros/"
#========================


#excellent tool based on module psutil;
#will kill all processes in the tree (which on Windows is otherwise impossible)
def killtree(pid, including_parent=True):    
    parent = psutil.Process(pid)
    for child in parent.get_children(recursive=True):
        child.kill()
    if including_parent:
        parent.kill()


#this is the basic macro format:
#VERSION BUILD=8510617 RECORDER=FX
#SET !REPLAYSPEED SLOW
#TAB T=1
#URL GOTO=https://bitcointalk.org/index.php?topic=295926.0
#WAIT SECONDS=5
#URL GOTO=http://news.bbc.co.uk/
#SET !EXTRACT done
#SAVEAS TYPE=EXTRACT FOLDER=C:\ssllog-master FILE=iSignal.txt
def make_imacro(websites,runID):
    
    macro_file = shared.verify_file_creation(imacros_dir+runID+'.iim',\
                                             "Macro file exists")
    macro_file_handle = open(macro_file,'w')
    
    #build the lines for the file, starting with header lines
    file_contents = ['VERSION BUILD=8510617 RECORDER=FX',\
                     'SET !REPLAYSPEED SLOW','TAB T=1',\
                     'SET !TIMEOUT_PAGE 180']
    for website in websites:
        shared.debug(1,["writing this website to the macro: ",website])
        file_contents.append('URL GOTO='+website)
        file_contents.append('WAIT SECONDS=5')
    
    #now append footer
    file_contents.extend(['SET !EXTRACT done',\
    'SAVEAS TYPE=EXTRACT FOLDER=C:\\ssllog-master FILE=iSignal.txt'])
    
    for item in file_contents:
        print>>macro_file_handle, item

#function acts as a wrapper for background processes
#which we get by using the multiprocessing (threading implemented at process
# level) module
def run_process(command):
    for a in command:
        #A mind bogglingly ugly hack; TODO choose which way to call on a flag
        if 'stcp_escrow' in a:
            command_str = ''.join(command)
            os.system(command_str)
    command_str = ' '.join(command) + ' > NUL 2>&1'
    os.system(command_str)
    #stcppipes never return, but ssh does; just lose it
    exit()
        

def run_test(runID, websites_to_visit):
    
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
    os.system('start /B /D \"'+os.path.dirname(g("Exepaths","firefox_exepath"))+\
    '\" '+os.path.basename(g("Exepaths","firefox_exepath")))
    
    #This delay was incorporated as per the instructions at the iMacros wiki;
    #it's needed because Firefox must load the add-on completely before we
    #make the call to our individual macro
    time.sleep(15) 
    os.system('\"'+g("Exepaths","firefox_exepath")+'\" imacros://run/?m='+runID+'.iim')
    
    #wait for imacro to signal us finished
    while not os.path.isfile('iSignal.txt'):
        time.sleep(1)
    #got the signal so remove the signal file
    os.remove('iSignal.txt')
    
    print "Firefox macro finished for run:",runID
    
    
def cleanup():
    #once we've finished all the runs
    #we'll want to shutdown all stcppipes and POSSIBLY ssh
    #this will kill everything on the local machine
    killtree(os.getpid(),including_parent=False)
    #we still need to kill the remote stcppipe
    remote_command('pkill -SIGTERM stcppipe')
    
    #unfortunately firefox is not in our tree, will have to hunt it down!
    ff_killed=False
    for proc in psutil.process_iter():
        if 'firefox' in proc.name:
            proc.kill()
            ff_killed=True
    
    if not ff_killed: print "Failed to kill firefox"
    
    #allow a little time for OS cleanup
    time.sleep(2)
    
    print "infrastructure for tests is now shut down.\n"

#run a shell command on the remote escrow server.
def remote_command(command):
    os.system(g("Exepaths","sshpass_exepath")+' '\
                +g("Buyer","buyer_ssh_user")+'@'+g("Escrow","escrow_host")+' -P '\
                +g("Escrow","escrow_ssh_port")+' -pw '+g("Buyer","buyer_ssh_pass")\
                +' \"'+command+'\"')

#copy all files from remote_dir on the remote (escrow) server to the local_dir
#directory on the local machine
def get_remote_files(remote_dir,local_dir):
    os.system('\"'+g("Exepaths","scp_exepath")+'\" -P '\
    +g("Escrow","escrow_ssh_port")+' -pw '+g("Buyer","buyer_ssh_pass")+\
    ' -unsafe '+g("Buyer","buyer_ssh_user")+'@'+g("Escrow","escrow_host")+':'+\
    remote_dir+'/* '+local_dir+'/.')
    
if __name__ == "__main__":
    
    #we need config file loaded
    helper_startup.loadconfig()
    
    #define where the run data from stcppipe is going to be stored
    #by using the unique runID which called this script
    runID = sys.argv[1]
    if not runID:
        print "runID was not found. Quitting.\n"
        exit()
    #read the websites from the filename:
    website_list=[]
    with open(os.path.join(g("Directories",\
        "testing_web_list_dir"),runID)) as f:
        website_list=filter(None,f.read().splitlines())
    
    
    #make the directories to store the log files
     #logged data will be stored here on the buyer,escrow, and seller
    #(note that the escrow is on a remote host, in this case Linux)
    run_dir_base = {'buyer':g("Directories","buyer_base_dir"),\
                    'seller':g("Directories","seller_base_dir"),\
                    'escrow':g("Directories","escrow_base_dir")}
    #set up the directory structure for the escrow on the remote host
    remote_command('mkdir '+runID+'; cd '+runID+'; mkdir stcp_escrow')
    new_dir = os.path.join(run_dir_base['buyer'],runID)
    if not os.path.exists(new_dir): os.makedirs(new_dir)
    #Note: in some future test scenario, where buyer and seller
    #have different basedirs, might need to add a line for seller here.
    #Now set up the stcp log directories:
    stcp_buyer_dir = os.path.join(new_dir,'stcp_buyer')
    if not os.path.exists(stcp_buyer_dir): os.makedirs(stcp_buyer_dir)
    stcp_seller_dir = os.path.join(new_dir,'stcp_seller')
    if not os.path.exists(stcp_seller_dir): os.makedirs(stcp_seller_dir)
    stcp_escrow_dir = os.path.join(new_dir,'stcp_escrow')
    if not os.path.exists(stcp_escrow_dir): os.makedirs(stcp_escrow_dir)
    
    #We use data defined in the config file to build the list
    #of commands for network setup
    #build ssh commands
    #first ssh is local port forwarding for buyer
    buyer_ssh_command = [g("Exepaths","sshpass_exepath"), g("Buyer","buyer_ssh_user") \
    +'@'+g("Escrow","escrow_host"),'-P', g("Escrow","escrow_ssh_port"), '-pw', \
    g("Buyer","buyer_ssh_pass"),'-N','-L', g("Buyer","buyer_stcp_port")+':127.0.0.1:'+\
    g("Escrow","escrow_input_port")]
    all_commands.append(buyer_ssh_command)
    #second ssh is remote port forwarding for seller
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
            #Left here as a working string, just in case something breaks in future
            #stcp_commands[agent]=[g("Exepaths","sshpass_exepath")+' escrowbuyer@109.169.23.122 -P 227 -pw NnFtIsSlA1228 \"stcppipe -d autotest1/stcp_escrow -b 127.0.0.1 12347 12346 > /dev/null 2>&1 &\"']
            stcp_commands[agent]=[g("Exepaths","sshpass_exepath")+' '\
            +g("Buyer","buyer_ssh_user")+'@'+g("Escrow","escrow_host")+' -P '\
            +g("Escrow","escrow_ssh_port")+' -pw '+g("Buyer","buyer_ssh_pass")+\
            ' \"stcppipe -d '+runID+'/stcp_escrow -b 127.0.0.1 ' + \
            g(agent.title(),agent+"_stcp_port")+' ' + \
            g(agent.title(),agent+"_input_port")+ ' > /dev/null 2>&1 &\"']
            all_commands.append(stcp_commands[agent])
        else:
            stcp_commands[agent]=[g("Exepaths","stcppipe_exepath"),'-d',\
            os.path.join(dir,runID,"stcp_"+agent),'-b','127.0.0.1',\
            g(agent.title(),agent+"_stcp_port"),\
            g(agent.title(),agent+"_input_port")]
            all_commands.append(stcp_commands[agent])
    

    #all is ready; start test
    run_test(runID,website_list)
    
    #now time to gracefully shut down the pipes and the browser
    cleanup()
    
    #having run the tests, we need to copy the log files from the
    #remote host to the local host in advance of escrow.py testing
    #Can be achieved using scp
    get_remote_files(runID+'/stcp_escrow',stcp_escrow_dir)
    
    #we have all data in stcp_buyer,seller,escrow; we can run the escrow script
    #to check for hash mismatches. All the results are dumped to stdout, which
    #can then be parsed by a wrapper script (and saved to file as appropriate)
    error_in_hash_matching=False
    for role_string in ['bs','eb','es']:
        command_str = 'escrow.py -r '+role_string+' 1 '+runID
        print "Starting analysis script:",command_str
        if os.system(command_str) != 0:
            error_in_hash_matching = True
        #clean out the merged file in case it interferes with the next run
        for char in role_string:
            if char=='b': os.remove(os.path.join(stcp_buyer_dir,"merged.pcap"))
            elif char=='s': os.remove(os.path.join(stcp_seller_dir,"merged.pcap"))
            else: os.remove(os.path.join(stcp_escrow_dir,"merged.pcap"))
        
    print "Test run: ", runID," is complete."
    if error_in_hash_matching: exit(1)
    else: exit(0)
    

