#Cleanup a capture file so there are no extraneous packets
#Use a filter e.g. "ssl" to choose which packets to KEEP
#(or set reverse = false in call to sharkutils.editcap if 
#you want to remove them). The cleaned file is APPENDED with "_clean".
#

#=====LIBRARY IMPORTS===============
import sys
import subprocess
import shutil
import re
import shared
import sharkutils 
import helper_startup
#=====END LIBRARY IMPORTS==========



if __name__ == "__main__":
            
    #Load all necessary configurations:
    #========================
    helper_startup.loadconfig()
    
    if len(sys.argv) < 3:
        print 'Usage cleancap.py <capfile> <filter string> <reverse>'
        exit()
    outfile = sys.argv[1] + "_clean"
    sharkutils.editcap(sys.argv[1],outfile,filter=sys.argv[2], reverse_flag=int(sys.argv[3]))
    
    



        

        


