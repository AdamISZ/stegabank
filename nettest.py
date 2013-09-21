import shared
import shutil
import psutil
import sys
import helper_startup
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import os


if __name__ == "__main__":
    helper_startup.loadconfig()
    auto = sys.argv[1]
    #if (auto != 'manual'): auto = ''
    
    for file in os.listdir(g("Directories","testing_web_list_dir")):
        #Bug identified 19 Sep 2013: running command without "python" causes
        #a problem when redirecting to stdout; see:
        #http://stackoverflow.com/questions/3018848/ - top answer
        #Also, note this has implications for sys.argv!
        if (os.system('python testdatagenerator.py '+file+' '+ auto+' > '+file+'output.txt') != 0):
            print "Error was detected in run:"+file+"\n"
        else:
            print "Run:"+file+" was successful.\n"
        shutil.copy2(file+'output.txt',os.path.join(g("Directories",\
        "buyer_base_dir"),file,"results.txt"))
