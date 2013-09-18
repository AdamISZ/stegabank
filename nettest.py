import shared
import helper_startup
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import os


if __name__ == "__main__":
    helper_startup.loadconfig()
    run_counter=0
    for file in os.listdir(g("Directories","testing_web_list_dir")):
        if (os.system('testdatagenerator.py '+file) != 0):
            print "Error was detected in run:"+file+"\n"
        else:
            print "Run:"+file+" was successful.\n"
        
