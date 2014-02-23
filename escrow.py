#escrow.py - daemon to run the escrow
#=====LIBRARY IMPORTS===============
import os, sys
import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import helper_startup
import AppLayer
from AppLayer import EscrowAgent
import logging
import pika
logging.getLogger('pika').setLevel(logging.DEBUG)
#=====END LIBRARY IMPORTS==========

if __name__ == "__main__":
    #Load all necessary configurations:
    #========================
    print sys.argv[1]
    helper_startup.loadconfig(sys.argv[1])
    
    #In the next section we instantiate the escrow agent object
    myself = EscrowAgent(g("Directories","escrow_base_dir"),\
                    g("Escrow","escrow_id"))
    myself.printCurrentTransactions()
    myself.run(sys.argv[2])
    











