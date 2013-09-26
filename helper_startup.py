import shared
import ConfigParser
import sys
import os

#TODO: This loading function currently assumes that 
#the config file is called "ssllog.ini" and that it's
#stored in the same directory as the program code.
def loadconfig():
    # First try to load the config file  from the program
    # directory
    shared.config.read('ssllog.ini')
'''    
    #print config.sections() #for testing
        
    #load paths of executables
    tshark_exepath = shared.config.get("Exepaths","tshark_exepath")
    editcap_exepath = shared.config.get("Exepaths", "editcap_exepath")
    dumpcap_exepath = shared.config.get("Exepaths","dumpcap_exepath")
    stunnel_exepath = shared.config.get("Exepaths","stunnel_exepath")
    ssh_exepath = shared.config.get("Exepaths","ssh_exepath")
    bitcoind_exepath = shared.config.get("Exepaths","bitcoind_exepath") 
    squid3_exepath = shared.config.get("Exepaths","squid3_exepath")
    firefox_exepath = shared.config.get("Exepaths","firefox_exepath")
       
    #load paths of necessary capture files
    #At present these are overwriting defaults, we could
    #remove this probably
    buyer_dumpcap_capture_file = shared.config.get("Captures","buyer_dumpcap_capture_file")
    seller_dumpcap_capture_file = shared.config.get("Captures","seller_dumpcap_capture_file")
    tshark_capture_file = shared.config.get("Captures","tshark_capture_file")
    
    #Load details of escrow configuration
    escrow_host = shared.config.get("Escrow","escrow_host")
    escrow_port = shared.config.get("Escrow","escrow_port")
    escrow_sshuser = shared.config.get("Escrow","escrow_ssh_user")
    escrow_sshpass = shared.config.get("Escrow","escrow_ssh_pass")
    
    buyer_proxy_port=shared.config.get("Buyer","buyer_proxy_port")
    buyer_stunnel_port=shared.config.get("Buyer","buyer_stunnel_port")
    seller_stunnel_port=shared.config.get("Seller","seller_stunnel_port")
    seller_proxy_port=shared.config.get("Seller","seller_proxy_port")
    
    #Bitcoin specific config
    seller_addr_funded_multisig = shared.config.get("Escrow","seller_addr_funded_multisig")
    #=============================
   ''' 
