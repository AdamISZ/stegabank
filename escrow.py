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

#=====LIBRARY IMPORTS===============
import sys
import subprocess
import shutil
#import os
#import requests
import time
#import signal
import re
import shared
import sharkutils 
import helper_startup
#=====END LIBRARY IMPORTS==========


def test_ssl_matching(file1,file2,role_string):
    
    if (role_string == 'bs'):
        port1 = int(shared.config.get("Buyer","buyer_proxy_port"))
        port2 = int(shared.config.get("Seller","seller_proxy_port"))
        userOS1 = shared.config.get("Buyer","buyer_OS")
        userOS2 = shared.config.get("Seller","seller_OS")
    elif (role_string == 'es'):
        port1 = int(shared.config.get("Escrow","escrow_port"))
        port2 = int(shared.config.get("Seller","seller_proxy_port"))
        userOS1 = shared.config.get("Escrow","escrow_OS")
        userOS2 = shared.config.get("Seller","seller_OS")
    elif (role_string == 'be'):
        port1 = int(shared.config.get("Buyer","buyer_proxy_port"))
        port2 = int(shared.config.get("Escrow","escrow_port"))
        userOS1 = shared.config.get("Buyer","buyer_OS")
        userOS2 = shared.config.get("Escrow","escrow_OS")
    else:
        print "error, incorrect role string passed to test_ssl_matching()"
        exit()
        
    #preparatory step: filter and reduce files
    #to contain only SSL data and only data for the right port:
    
    shared.debug(1, \
    ["We're about to call get hashes from capfile with file name: ",file1])
    hashes1 = sharkutils.get_all_ssl_hashes_from_capfile(file1,  \
                port=port1,userOS=userOS1)
    shared.debug(1,["Length of hashes1 is : ",str(len(hashes1))])
    shared.debug(1, \
    ["We're about to call get hashes from capfile with file name: ",file2])
    hashes2 = sharkutils.get_all_ssl_hashes_from_capfile(file2, \
            port=port2,userOS=userOS2)
    shared.debug(1,["Length of hashes2 is : ",str(len(hashes2))])
       
    if (role_string == 'es'):
        if (set(hashes2).issubset(set(hashes1))):
            print "The seller's capture file matches the escrow's capture file; \
                   \n The buyer's ssl keys must be faulty."
            exit()
        else:
            print "The ssl traffic in the seller's capture file does not match \
                   \n that in the escrow capture file. The seller has not \
                       \n provided a genuine capture file."
            intersection = [val for val in hashes2 if val in hashes1]
            print "The intersection has length: " + str(len(intersection))
            exit()
    else:
        if set(hashes1) ==set(hashes2): 
            print "The seller's capture file matches the buyer's capture file; \
                \n The buyer's ssl keys must be faulty."
        
        else:
            intersection = [val for val in hashes2 if val in hashes1]
            for hash in list(hashes1):
                if hash not in intersection:
                    print "from hash1, this hash was not found: " + str(hash)
            for hash in list(hashes2):
                if hash not in intersection:
                    print "from hash2, this hash was not found: " + str(hash)
            
            print "The ssl traffic in the capture file delivered by the seller \n \
               does not match that in the escrow capture file. The seller \n \
               has not provided a genuine capture file. "
        
        
        

if __name__ == "__main__":
            
    #Load all necessary configurations:
    #========================
    helper_startup.loadconfig()
    
    if len(sys.argv) < 3:
        print 'Usage escrow.py 0/1/2/3 [transactionid] [ssl key file] [stunnel key file] [L1filter]'
        exit()
    level = sys.argv[1]

    #testing core functionality TODO remove from prod
    if int(level) == 99:
        test_ssl_matching(sys.argv[2],sys.argv[3], sys.argv[4])
        exit()
    if int(level) == 98:
        port1 = shared.config.get("Buyer","buyer_proxy_port")
        port2 = shared.config.get("Seller","seller_proxy_port")
        sharkutils.debug_find_mismatch_frames(sys.argv[2],port1,sys.argv[3],port2)
        exit() 
    if int(level) == 97:
        port1 = shared.config.get("Buyer","buyer_proxy_port")
        port2 = shared.config.get("Seller","seller_proxy_port")
        sharkutils.debug_find_mismatch_frames_stream_filter(sys.argv[2],port1,sys.argv[3],port2)
        exit()
        
    if int(level) == 1:
        print 'Level 1 dispute not yet implemented'
        exit()
    elif int(level) !=2:
        print 'Only level 2 dispute currently implemented'
        exit()

    
    #========LEVEL 2 DISPUTE RESOLUTION==========
    #First, logic of resolution process:
    #L2D is called if L1D failed. In L1D, buyer has provided ssl keys
    #and seller has provided an edited/reduced capture file.
    #But the file did not decrypt and the escrow has no way of knowing
    #for sure who is at fault.
    #So L2D goes as follows:
    #Then, escrow uses wireshark to view seller's capture file (scf) with buyer's
    #ssl keys. If decryption is successful (which it may be despite failure
    #of L1D, because we now have the unedited capture file), escrow views the 
    #internet banking session and makes a judgement as to who should receive
    #the bitcoins.
    #If decryption in this way fails (more likely):
    #Seller is requested to provide stunnel key. If he refuses, bitcoins are
    #passed to buyer.
    #Escrow (using this script) first decrypts the first layer of decryption in 
    #his own "escrow capture file" (ecf), leaving the data in a still-ssl-encrypted form.
    #He then tries to find matches for each ssl app data record between ecf and scf.
    #If matches are not found he concludes that the seller's file is not valid
    #and the bitcoins are awarded to the buyer. 
    #If the ssl appdata in ecf and scf DO match, then he concludes that the 
    #buyer's ssl keys are not valid, and awards the bitcoins to the seller.
    
    
    ssl_keys_file = argv[2]
    stunnel_key_file = argv[3]
    transaction_id = argv[4]
    #Plan of action: take existing escrow capture file (indexed by transaction id)
    #run stunnel key against the contents of the capture, then store a list of
    #hashes. We need that each hash in the escrow file matches the seller file,
    #else we consider the seller file to be invalid
    
    ecf = get_ecf_by_txid(transaction_id)
    if not ecf:
        print "the escrow capture file for transaction: " + transaction_id + " was not found."
        exit()
    
    scf = get_scf_by_txid(transaction_id)
    if not scf:
        print "the seller capture file for transaction: " + transaction_id + " was not found."
        exit()
        
    decrypted_ecf = decrypt_escrow_cap(ecf,stunnel_key_file)
    if not decrypted_ecf:
        print "Failed to decrypt the capture file: " + ecf
        exit()
    
    #get a list of ssl hashes from the ecf:
    escrow_hashes = sharkutils.get_all_ssl_hashes_from_capfile(decrypted_ecf)
    if not escrow_hashes:
        print "failed to get the list of ssl hashes from the escrow capture file"
        exit()
    
    #check that all the escrow hashes are in the scf:
    #(this is the serious business..)
    #issue: what if they're COMPLETELY out of order? Is it still OK?
    result = sharkutils.check_ssl_hashes_are_all_in_capfile(escrow_hashes, scf)
    if result:
        print "The seller's capture file matches the escrow's capture file; \
               \n The buyer's ssl keys must be faulty."
        exit()
    else:
        print "The ssl traffic in the capture file delivered by the seller \n \
               does not match that in the escrow capture file. The seller \n \
               has not provided a genuine capture file. "
        exit()



        

        


