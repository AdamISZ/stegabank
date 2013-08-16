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


def test_ssl_matching(buyer_file,seller_file):
    
    #preparatory step: filter and reduce buyer and seller files
    #to contain only SSL data and only data for the right port:
    #EDITED: realised this has already been done in live capture
    #buyer_file_filtered = \
     #   sharkutils.filter_cap_file(buyer_file, buyer_proxy_port, ssl = True)
    #seller_file_filtered = \
    #    sharkutils.filter_cap_file(seller_file, buyer_proxy_port, ssl = True)
    #
    print "We're about to call get hashes from capfile with file name: " + buyer_file
    buyer_hashes = sharkutils.verify_ssl_hashes_from_capfile(buyer_file, \
                    port = int(shared.config.get("Buyer","buyer_proxy_port")))
    result = sharkutils.check_ssl_hashes_are_all_in_capfile(buyer_hashes,seller_file)
    
    if result:
        print "The seller's capture file matches the escrow's capture file; \
               \n The buyer's ssl keys must be faulty."
        exit()
    else:
        print "The ssl traffic in the capture file delivered by the seller \n \
               does not match that in the escrow capture file. The seller \n \
               has not provided a genuine capture file. "
        exit()

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
        test_ssl_matching(sys.argv[2],sys.argv[3])
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



        

        


