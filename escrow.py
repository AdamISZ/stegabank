#Escrow script
#
#Escrow has two functions:
#(a) record doubly encrypted traffic to bank
#(b) resolve dispute
#
#Usage: escrow.py n [transactionid] [ssl.keys] [stunnel.key] [L1 filter]
# or python escrow.py n [transactionid] [ssl.keys] [stunnel.key] [L1 filter]
# where n is mode: 0 = recording, 1 = L1 dispute 2 = L2 dispute 3 = L3 dispute
#
#The first argument is the dispute level (1 or 2)
#Initially, only level 2 and 3 is implemented for testing
#
#In L3 dispute, escrow performs
#decryption twice in case of strong evidence
#of fraudulent behaviour. The result is that 
#the escrow will get the FULL DECRYPTED TRAFFIC
#which is why L3 is avoided wherever possible.
#Open questions:
#1. Do we need bitcoin functionality here?
#2. What happens if the seller's capture file has all the ssl but
#   it's completely out of order? May or may not be important.

#14 Sep 2013
#Pseudo code for oracle-escrow:
#Wait for requests
#New transaction request arrives (via network) giving txid, buyer info, seller info
#create multisig address
#announce multisig address to seller and wait for BTC arrival
#verify BTC in multisig 
#start ssh/stcppipe daemon
#send ready message to buyer and seller
#record ssl traffic
#receive tx end message from both buyer and seller
#request signed ssl hashes from buyer and seller
#store buyer's and seller's claimed ssl hashes
#end session
#wait for "transaction complete" message from seller (or network), and delete
#ssl logs
#if instead "dispute" message received, perform 3-way check on stored
#ssl, if escrow does/doesn't match with both buyer and seller, pass SUCCESS/FAIL message to 
#(the network/a third escrow/a human escrow).<--not sure which.
#Receive CONFIRMED or NOT CONFIRMED message stating whether the other 
#escrow agrees with you.
#If SUCCESS is confirmed, or if NOT CONFIRMED is received, the case is escalated
#to a human escrow, who then asks the buyer for their html and associated stream key.

#=====LIBRARY IMPORTS===============
import sys
import subprocess
import shutil
import os
#import requests
import time
#import signal
import re
import shared
import sharkutils 
import helper_startup
import argparse
#=====END LIBRARY IMPORTS==========
    
#This function is intended to VERIFY whether the ssl data in the given
#trace files matches appropriately as expected. It does not give a detailed
#breakdown of any unexpected mismatches between those files. For that purpose
#use escrow.py 2 (debug facility)
def test_ssl_matching(runID,buyer,seller,escrow,role_string):
    
    #make sure to have stunnel key loaded if appropriate
    #18 Sep 2013 removed as stunnel not in use for now
    #options = [sharkutils.get_stunnel_keystring()] if (role_string[0]=='e') else []
    #shared.debug(1,["Options to tshark were defined as: ",options])
    
    options=[]
    ports = {}
    stcp_hashes = {}
    
    if not runID:
        shared.debug(0,["Critical error: runID must be provided. Quitting."])
        exit()
    if (role_string == 'xx'):
        #This is not needed for ssl checking! Leaving here for future consideration.
        #The really important point is that you should NOT have the keylog file
        #set correctly as it MASSIVELY slows down tshark which needlessly
        #decrypts all the data!
        #set the keylog file:
        #options.append('ssl.keylog_file:'+\
        #os.path.join(shared.config.get("Directories","escrow_base_dir"),runID,\
        #runID+'.keys'))
        
        for a in ['buyer','seller','escrow']:
            ports[a] = int(shared.config.get(a.title(),a+"_stcp_port"))
            stcp_hashes[a]=[]
        #construct location of stcppipe files
        for agent in ports.iterkeys():
            stcp_log_dir = os.path.join( \
            shared.config.get("Directories","escrow_base_dir"), \
            runID,'stcp_'+agent)
            stcp_hashes[agent]=\
            (sharkutils.get_all_ssl_hashes_from_capfile(stcp_log_dir, \
            port=ports[agent],stcp_flag=True,in_options=options))
            
        if set(stcp_hashes['buyer'])==set(stcp_hashes['seller']) and \
        set(stcp_hashes['seller']) == set(stcp_hashes['escrow']):
            print "All hashes were matched across all three agents. Success."
            exit(0)
        else:
            print "All hashes were not matched. Failure."
            exit(1)
        
    elif (not role_string or role_string == 'bs'):
        port1 = int(shared.config.get("Buyer","buyer_stcp_port"))
        port2 = int(shared.config.get("Seller","seller_stcp_port"))
        file1 = buyer
        file2 = seller
    elif (role_string == 'es'):
        port1 = int(shared.config.get("Escrow","escrow_stcp_port"))
        port2 = int(shared.config.get("Seller","seller_stcp_port"))
        file1 = escrow
        file2 = seller
    elif (role_string == 'eb'):
        port2 = int(shared.config.get("Buyer","buyer_stcp_port"))
        port1 = int(shared.config.get("Escrow","escrow_stcp_port"))
        file1 = escrow
        file2 = buyer
    else:
        print "error, incorrect role string passed to test_ssl_matching()"
        exit(1)
    
    #the next four code blocks gather the ssl hashes according to the conditions
    if (file1): 
        file1 = os.path.join( \
        shared.config.get("Directories","escrow_base_dir"),runID,file1)
        shared.debug(1, \
        ["We're about to call get hashes from capfile with file name: ",file1])
        hashes1 = sharkutils.get_all_ssl_hashes_from_capfile(file1,  \
        port=port1,stcp_flag=False,in_options=options)
    else:
        #construct location of stcppipe files
        dir_name = "stcp_buyer" if (role_string[0]=='b') else "stcp_escrow"
        stcp_log_dir = os.path.join( \
        shared.config.get("Directories","escrow_base_dir"), \
        runID,dir_name)
        hashes1 = sharkutils.get_all_ssl_hashes_from_capfile(stcp_log_dir, \
        port=port1,stcp_flag=True,in_options=options)
    
    shared.debug(1,["Length of hashes1 is : ",len(hashes1)])
    
    
    if (file2): 
        file2 = os.path.join( \
        shared.config.get("Directories","escrow_base_dir"),runID,file2)
        shared.debug(1, \
        ["We're about to call get hashes from capfile with file name: ",file2])
        hashes2 = sharkutils.get_all_ssl_hashes_from_capfile(file2,  \
        port=port2,stcp_flag=False)
        
    else:
        #construct location of stcppipe files
        dir_name = "stcp_seller" if (role_string[1]=='s') else "stcp_buyer"
        stcp_log_dir = os.path.join( \
        shared.config.get("Directories","escrow_base_dir"), \
        runID,dir_name)
        hashes2 = sharkutils.get_all_ssl_hashes_from_capfile(stcp_log_dir, \
        port=port2,stcp_flag=True)   
    
    shared.debug(1,["Length of hashes2 is : ",len(hashes2)])
    
       
    #18 Sep 2013: without stunnel, we don't need to use subset so this if
    #block is redundant as of now.
    #if (role_string[0] == 'e'):
    #    if (set(hashes2).issubset(set(hashes1))):
    #        print "The seller's capture file matches the escrow's capture file; \
    #               \n The buyer's ssl keys must be faulty."
    #        exit()
    #    else:
    #        print "The ssl traffic in the seller's capture file does not match \
    #               \n that in the escrow capture file. The seller has not \
    #                   \n provided a genuine capture file."
    #        intersection = [val for val in hashes2 if val in hashes1]
    #        print "The intersection has length: " + str(len(intersection))
    #        exit()
    #else:
    if set(hashes1) ==set(hashes2): 
        print "The capture files match perfectly (all hashes identical)!"
    
    else:
        intersection = [val for val in hashes2 if val in hashes1]
        for hash in list(hashes1):
            if hash not in intersection:
                print "This hash from buyer was not found in seller list: "\
                     + str(hash)
        for hash in list(hashes2):
            if hash not in intersection:
                print "This hash from seller was not found in buyer list: "\
                     + str(hash)
        print "The intersection has length: " + str(len(intersection))
        print "The ssl traffic in the capture file delivered by the seller \n \
           does not match that in the escrow capture file. The seller \n \
           has not provided a genuine capture file. "
        #need to signal to the calling script that there was a failure
        exit(1)
        
        
        

if __name__ == "__main__":
            
    #Load all necessary configurations:
    #========================
    helper_startup.loadconfig()
    
    #parse the command line arguments
    parser = argparse.ArgumentParser(description='ssllog escrow script')
    parser.add_argument('mode',type=int,help="running mode: choose from 1(\
                        basic matching check) or 2 (full debug check)")
    parser.add_argument('runID',help="enter the unique name of the directory\
                         containing the trace data for this run")
    parser.add_argument('-b',help="enter relative path to the buyer network\
                         trace file, NOT to be used with stcppipe")
    parser.add_argument('-s',help="enter relative path to the seller network\
                         trace file, NOT to be used with stcppipe")
    parser.add_argument('-e',help="enter relative path to the escrow network\
                         trace file, NOT to be used with stcppipe")
    parser.add_argument('-r',help="enter one of \'bs\' (buyer-seller), \'es\' \
                (escrow-seller) or \'eb\' (buyer-escrow). Default is \'bs\'")
    parser.add_argument('-f',help="escrow frame list")
    parser.add_argument('-g',help="seller frame list")
    args = parser.parse_args()
    
    #basic check: do the files match or not?
    if args.mode == 1: 
        test_ssl_matching(args.runID, args.b,args.s,args.e,args.r)
        exit()
    
    #detailed debug option    
    if args.mode == 2: 
        
        #set stunnel key if appropriate
        options = [sharkutils.get_stunnel_keystring()] if (args.r[0]=='e')\
        else []
        base = os.path.join(shared.config.get("Directories","escrow_base_dir"),\
                args.runID)
        
        if (not args.r or args.r == 'bs'):
            port1 = int(shared.config.get("Buyer","buyer_stcp_port"))
            port2 = int(shared.config.get("Seller","seller_stcp_port"))
            buyer = args.b if args.b else "stcp_buyer"
            seller = args.s if args.s else "stcp_seller"
            file1 = os.path.join(base,buyer)
            file2 = os.path.join(base,seller)
            stcp_flag1 = not(args.b)
            stcp_flag2 = not(args.s)
        
        elif (args.r == 'es'):
            port1 = int(shared.config.get("Escrow","escrow_stcp_port"))
            port2 = int(shared.config.get("Seller","seller_stcp_port"))
            escrow = args.e if args.e else "stcp_escrow"
            seller = args.s if args.s else "stcp_seller"
            file1 = os.path.join(base,escrow)
            file2 = os.path.join(base,seller)
            stcp_flag1 = not(args.e)
            stcp_flag2 = not(args.s)
            
        elif (args.r == 'eb'):
            port2 = int(shared.config.get("Buyer","buyer_stcp_port"))
            port1 = int(shared.config.get("Escrow","escrow_stcp_port"))
            escrow = args.e if args.e else "stcp_escrow"
            seller = args.s if args.s else "stcp_buyer"
            file1 = os.path.join(base,escrow)
            file2 = os.path.join(base,seller)
            stcp_flag1 = not(args.e)
            stcp_flag2 = not(args.b)
        else:
            print "error, incorrect role string passed to test_ssl_matching()"
            exit()
        
        sharkutils.debug_find_mismatch_frames(file1,port1,stcp_flag1,\
                                file2,port2,stcp_flag2,options=options)
        exit()
    if args.mode==4:
        capfile = os.path.join(shared.config.get("Directories",\
                "escrow_base_dir"),args.runID,args.e)
        print "converting file:",capfile
        sharkutils.convert_escrow_trace(capfile)
        print "done"
        exit()
    if args.mode==5:
        escrow = os.path.join(shared.config.get("Directories",\
                "escrow_base_dir"),args.runID,args.e)
        seller = os.path.join(shared.config.get("Directories", \
                "escrow_base_dir"),args.runID,args.s)
        escrow_frames = seller_frames = []
        if (args.f): escrow_frames = args.f.split(',')
        if (args.g): seller_frames = args.g.split(',')
        seller_port = int(shared.config.get("Seller","seller_stcp_port"))
        escrow_stcp_port = int(shared.config.get("Escrow","escrow_stcp_port"))
        
        #read in the boolean options to be tried from the config file
        options=[]
        optionvars=shared.config.get("SharkInternals","boolean_flags").split(',')
        for var in optionvars: options.append(var)
        
        #also add options for tcp and ssl ports:
        options.append('http.tcp.port:'+shared.config.get("SharkInternals","http.tcp.port_fixed")+','+shared.config.get("SharkInternals","http.tcp.port_var"))
        options.append('http.ssl.port:'+shared.config.get("SharkInternals","http.ssl.port_fixed")+','+shared.config.get("SharkInternals","http.ssl.port_var"))
        
        hashes_escrow = sharkutils.get_all_hashes_from_escrow(escrow,\
        port=escrow_stcp_port,frames=escrow_frames,in_options=options)
        hashes_seller = sharkutils.get_ssl_hashes_from_capfile(seller,\
        port=seller_port,frames=seller_frames)
        
        #write over the options for the basic run
        #options = [sharkutils.get_stunnel_keystring()]
        hashes_escrow2 = sharkutils.get_all_ssl_hashes_from_capfile(escrow,port=escrow_stcp_port,in_options=options)
        
        print len(set(hashes_escrow))
        print len(set(hashes_escrow2))
        full_escrow = list(set(hashes_escrow).union(set(hashes_escrow2)))
        print len(set(full_escrow))
        print len(set(hashes_seller))
        print len(set(full_escrow).intersection(set(hashes_seller)))
        
        exit()
    print "unrecognised mode"
    exit()



        

        


