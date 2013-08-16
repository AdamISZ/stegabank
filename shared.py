softwareVersion = '0.0.1'
verbose = 1
import os
import ConfigParser
import subprocess

#instantiate globals before populating
#them from config
#==========================================


#ssllog_installdir is the dir from which main.py is run
'''installdir = os.path.dirname(os.path.realpath(__file__))

stunnel_exepath = ""
ssh_exepath = ""
sshpass_exepath = ""
squid3_exepath = ""
firefox_exepath = ""
bitcoind_exepath = ""
tshark_exepath = ""
editcap_exepath = ""
dumpcap_exepath = ""
tshark_capture_file=""
buyer_dumpcap_capture_file = ""
seller_dumpcap_capture_file = ""
buyer_proxy_port=""
buyer_stunnel_port=""
seller_stunnel_port=""
seller_proxy_port=""

#where buyer's dumpcap puts its traffic capture file
buyer_dumpcap_capture_file= os.path.join(installdir, 'capture', 'buyer_dumpcap.pcap')
#where seller's dumpcap puts its traffic capture file
seller_dumpcap_capture_file= os.path.join(installdir, 'capture', 'seller_dumpcap.pcap')
#where Firefox saves html files when user marks them
htmldir = os.path.join(installdir,'htmldir')

#bitcond user/pass are already in bitcoin.conf that comes with this installation
#these bitcond handlers can be initialized even before bitcoind starts
#buyer_bitcoin_rpc = authproxy.AuthServiceProxy("http://bitcoinrpc:EcwaeQpvjrfDCaEohCLKnR2kmvorWsSMSufUcsKPBwKH@127.0.0.1:8338")
#seller_bitcoin_rpc = authproxy.AuthServiceProxy("http://bitcoinrpc:EcwaeQpvjrfDCaEohCLKnR2kmvorWsSMSufUcsKPBwKH@127.0.0.1:8339")'''

config = ConfigParser.ConfigParser()
