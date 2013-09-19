import shared
import shutil
import helper_startup
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import os


if __name__ == "__main__":
    helper_startup.loadconfig()
    run_counter=0
    
    for file in os.listdir(g("Directories","testing_web_list_dir")):
        #Bug identified 19 Sep 2013: running command without "python" causes
        #a problem when redirecting to stdout; see:
        #http://stackoverflow.com/questions/3018848/ - top answer
        #Also, note this has implications for sys.argv!
        if (os.system('python testdatagenerator.py '+file+' > '+file+'output.txt') != 0):
            print "Error was detected in run:"+file+"\n"
        else:
            print "Run:"+file+" was successful.\n"
        shutil.copy2(file+'output.txt',os.path.join(g("Directories",\
        "buyer_base_dir"),file,"results.txt"))
#TODO list
#1. understand the issue with double quotes in subprocess.Popen - with intention
#   of using the supported module rather than obsolete os.system, and better chance
#   of cross-platform code
#2. Create second mode of operation for manual testing - switch on network
#   infrastructure, wait for user to close firefox, shut down infrastructure
#   and place files in appropriate places
#3. Have the final output file for each run automatically moved to the run dirDONE
#4. Fix mode 2 debug code in escrow.py; automatically run it if there is a
#   failure.
#5. Greatly extend this list of bank websites to try, as many urls as possible
#6. Try DEEP tests - 10-20 urls in a single website, say