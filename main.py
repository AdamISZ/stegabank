import sys
import subprocess
import shutil
import os
import signal
import requests
import BaseHTTPServer, SimpleHTTPServer
import threading
import time
import signal
import re
from bitcoinrpc import authproxy

#--------------------Begin customizable variables-------------------------------------

#THIS MUST BE CHANGED to point to a escrow's server IP which is running sshd. You can use localhost for testing
escrow_host = 'localhost' #e.g. '1.2.3.4'  NB! '127.0.0.1' may not work, use localhost instead
#the port is an arbtrary port on the escrow's server. Unless there is a port conflict, no need to change it.
escrow_port = 12345
#an existing username and password used to connect to sshd on escrow's server. For testing you can give your username if sshd ir run locally
escrow_ssh_user = 'default' #e.g. 'ssllog_user' 
escrow_ssh_pass = 'VqQ7ccyKcZCRq'
#THIS ADDRESS MUST BE in the seller's bitcond wallet
seller_addr_funded_multisig = '19e49upbF9JN7PqkTWpbaj3ijVJmb96rTJ' #e.g. '19CzQYZGiaENfypuNzMAf3Mg4vs5oE1hgV'

#ssllog_installdir is the dir from which main.py is run
installdir = os.path.dirname(os.path.realpath(__file__))

#---------------------You can modify these paths if some programs are not in your $PATH------------------
#DONT USE the version of stunnel that comes with Ubuntu - it is a ridiculously old incompatible version
stunnel_exepath = '/home/default/Desktop/sslxchange/stunnel-4.56/src/stunnel'
ssh_exepath = '/usr/bin/ssh'
sshpass_exepath = '/usr/bin/sshpass'
squid3_exepath = '/usr/sbin/squid3'
firefox_exepath = '/home/default/Desktop/firefox20/firefox'
#BITCOIND IS USUALLY NOT IN YOUR PATH
bitcoind_exepath = '/home/default/Desktop/bitcoin-qt/bitcoin-0.8.2-linux/bin/64/bitcoind'
tshark_exepath = '/usr/bin/tshark'
#editcap,dumpcap come together with wireshark package
editcap_exepath = '/usr/bin/editcap'
# NB!! dumpcap has to be given certain capabilities on Linux
# run --> sudo setcap 'CAP_NET_RAW+eip CAP_NET_ADMIN+eip' /usr/bin/dumpcap
dumpcap_exepath = '/usr/bin/dumpcap'

#Overwrites for windows testing
#This needs to be in a config file! 
tshark_exepath="C:/Program Files/Wireshark/tshark.exe"
dumpcap_exepath="C:/Program Files/Wireshark/dumpcap.exe"
editcap_exepath="C:/Program Files/Wireshark/editcap.exe"
tshark_capture_file="dumpout2.pcap"
buyer_dumpcap_capture_file = "dumpout2.pcap"
seller_dumpcap_capture_file = "dumpfromseller.pcap"

#where buyer's dumpcap puts its traffic capture file
buyer_dumpcap_capture_file= os.path.join(installdir, 'capture', 'buyer_dumpcap.pcap')
#where seller's dumpcap puts its traffic capture file
seller_dumpcap_capture_file= os.path.join(installdir, 'capture', 'seller_dumpcap.pcap')
#where Firefox saves html files when user marks them
htmldir = os.path.join(installdir,'htmldir')

#bitcond user/pass are already in bitcon.conf that comes with this installation
#these bitcond handlers can be initialized even before bitcoind starts
buyer_bitcoin_rpc = authproxy.AuthServiceProxy("http://ssllog_user:ssllog_pswd@127.0.0.1:8338")
seller_bitcoin_rpc = authproxy.AuthServiceProxy("http://ssllog_user:ssllog_pswd@127.0.0.1:8339")

#--------------End of customizable variables------------------------------------------------

#handle only paths we are interested and let python handle the response headers
#class "object" in needed to access super()
class buyer_HandlerClass(SimpleHTTPServer.SimpleHTTPRequestHandler, object):
    protocol_version = "HTTP/1.1"
    #Firefox addon speaks with HEAD
    def do_HEAD(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header("response", "status")
            self.send_header("value", "pending")
            super(buyer_HandlerClass, self).do_HEAD()
        elif self.path == '/tempdir':
            self.send_response(200)
            self.send_header("response", "tempdir")
            self.send_header("value", htmldir)
            super(buyer_HandlerClass, self).do_HEAD()
        elif self.path == '/finished':
            self.send_response(200)
            self.send_header("response", "finished")
            self.send_header("value", "ok")
            super(buyer_HandlerClass, self).do_HEAD()
            self.server.stop = True
    #logging messes up the terminal, disabling
    def log_message(self, format, *args):
        return
    
            
#handle only paths we are interested and let python handle the response headers
#class "object" in needed to access super()
class seller_HandlerClass(SimpleHTTPServer.SimpleHTTPRequestHandler, object):
    protocol_version = "HTTP/1.1"
    def do_HEAD(self):
        sys.stdout.write ('http server: receiver request '+self.path+' ')
        sys.stdout.write( 'test1')
        sys.stdout.write ('test2')
        if self.path == '/certificate':
            print "Buyer has requested the stunnel certificate"
            message = seller_get_certificate_verify_message()
            self.send_response(200)
            self.send_header("response", "certificate")
            self.send_header("value", message)
            super(seller_HandlerClass, self).do_HEAD()            
        if self.path == '/sslkeylogfile=':
            print "Received SSL keys from the buyer"
            sslkeylog_str = self.path[len('/sslkeylogfile='):]
            with open (os.join.path(installdir,'escrow','sslkeylogfile')) as file:
                file.write(sslkeylog_str)
            self.send_response(200)
            self.send_header("response", "sslkeylogfile")
            self.send_header("value", "ok")
            super(seller_HandlerClass, self).do_HEAD()
        if self.path == '/hashes=':
            print "Received hashes of SSL segments from the buyer"
            self.server.retval = self.path[len('/hashes='):]
            self.send_response(200)
            self.send_header("response", "hashes")
            self.send_header("value", "ok")
            super(seller_HandlerClass, self).do_HEAD()
            #receiving "hashes=" message is a signal to stop this server and continue in the man thread with parsing the hashes
            self.server.stop = True
    #logging messes up the terminal, disabling
    def log_message(self, format, *args):
        return
                
class StoppableHttpServer (BaseHTTPServer.HTTPServer):
    """http server that reacts to self.stop flag"""
    retval = ''
    def serve_forever (self):
        """Handle one request at a time until stopped. Optionally return a value"""
        self.stop = False
        while not self.stop:
            self.handle_request()
        return self.retval;
    
class ThreadWithRetval(threading.Thread):
    retval = ''

def listdir_fullpath(d):
    return [os.path.join(d, f) for f in os.listdir(d)]
    
def sighandler(signal, frame):
    cleanup_and_exit()
    
def cleanup_and_exit():
    global pids
    for pid in [item[1] for item in pids.items()]:
        os.kill(pid, signal.SIGTERM)
    os._exit(1) # <--- a hackish way to kill process from a thread

#AG wrapper for running tshark to extract data
#using the syntax -T fields
#output is filtered by a list of frame numbers
#and/or any other filter in Wireshark's -R syntax
def tshark(field, infile,filter='', frames=[]):
    #exepath is hard coded global (or config file eventually)
    args_stub = tshark_exepath + ' -r ' + infile 
    if (not filter and not frames):
        args = args_stub
    elif (not filter):
        args = args_stub + ' -R "frame.number ==' + \
        " or frame.number==".join(frames)
    elif (not frames):
        args = args_stub + ' -R "' + filter
    else:
        args = args_stub + ' -R "frame.number ==' + \
        " or frame.number==".join(frames) + ' and ' + filter
    
    args = args + '" -T fields -e ' + field
    
    try:
        tshark_out =  subprocess.check_output(args)
    except:
        print 'Error starting tshark'
        cleanup_and_exit()
    return tshark_out   

#send all the hashes in an HTTP HEAD request    
def buyer_send_sslhashes(sslhashes):
    print "Sending hashes of SSL segments to the seller"
    hashes_string = ''
    for hash in sslhashes:
        hashes_string += ';'+hash
    message = requests.head("http://127.0.0.1:4444/hashes="+hashes_string, proxies={"http":"http://127.0.0.1:33308"})
    if message.status_code != 200:
       print "Unable to send SSL hashes to seller"
       cleanup_and_exit()

#send sslkeylog to escrow. For testing purposes we can send it to seller.
#NB! There is probably a limit on header size in python
def buyer_send_sslkeylogfile():
    print "Sending SSL keys to the escrow"
    with open (ssl_keylogfile_path, "r") as file:
        data = file.read()
    keylogfile_ascii = data.__str__()
    message = requests.head("http://127.0.0.1:4444/sslkeylogfile="+keylogfile_ascii, proxies={"http":"http://127.0.0.1:33308"})
    if message.status_code != 200:
       print  "Unable to send SSL keylogfile to escrow"
       cleanup_and_exit()
    
    
def buyer_start_stunnel_with_certificate():
    global pids
    print 'Restarting stunnel with the new certificate'
    try:
        stunnel_proc = subprocess.Popen([stunnel_exepath, os.path.join(installdir, 'stunnel', 'buyer.conf')])
    except:
        print 'Error starting stunnel'
        cleanup_and_exit()
        
    print 'Making a test connection to example.org using the new certificate'
    #make a test request to see if stunnel setup is working
    response = requests.get("http://example.org", proxies={"http":"http://127.0.0.1:33308"})
    if response.status_code != 200:
        print ("Unable to make a test connection through seller's proxy")
        cleanup_and_exit()
    pids['stunnel'] = stunnel_pid

        
#AG optimized 4 Aug
def send_logs_to_escrow(sslhashes):
    print "Findind SSL segments in captured traffic"
    assert len(sslhashes) > 0, 'zero hashes provided'
    frames_wanted = []
    segments_hashes = {}
    
    #Run tshark once to get a list of frames with ssl app data in them
    try:
        frames_str = tshark('frame.number', seller_dumpcap_capture_file, \
                            'ssl.app_data')
    except:
        print 'Exception in tshark'
        cleanup_and_exit()
    frames_str = frames_str.rstrip()
    ssl_frames = frames_str.split('\r\n')
    print 'need to process this many frames:', len(ssl_frames)
    
    #Run tshark a second time to get the ssl.segment frames
    #from the full list of frames that matched content type 23
    try:
        segments_str = tshark('ssl.segment',seller_dumpcap_capture_file, \
                              filter='',frames=ssl_frames)
        #segments_str =  subprocess.check_output(tshark_args)
    except:
        print 'Error starting tshark'
        cleanup_and_exit()
    
    segments_str = segments_str.rstrip()    
    segments = re.findall('\w+',segments_str) #entries separated by , \r \n

    if len(segments) < 1:
        print 'zero SSL segments, should be at least one. Please investigate'
        cleanup_and_exit()
    #there can be multiple SSL segments in the same frame, so remove duplicates
    segments = set(segments)
    print "Need to process this many segments: ", len(segments)
    
    #the frame numbers are keys for the dictionary
    #so we initialise them:
    for segment in segments:
        segments_hashes[segment] = ''

    #Run tshark a third time to store all the app data
    #in memory. The frames have to be in the right order in the request
    #so we sort the keys from the dict
    frame_filter_string = ''
    for key in sorted(segments_hashes.iterkeys()):
        frame_filter_string = frame_filter_string + key + " or frame.number=="
    frame_filter_string = frame_filter_string[:-18]
    
    tshark_args_seller_stub = tshark_exepath + ' -r ' + \
    seller_dumpcap_capture_file + ' -R "frame.number ==' + \
    frame_filter_string
    tshark_args = tshark_args_seller_stub + '" -T fields -e ssl.app_data'
    try:
        ssl_app_data = subprocess.check_output(tshark_args)
    except:
        print 'Exception in tshark'
        cleanup_and_exit()
    ssl_app_data_list = ssl_app_data.split('\n')
    seller_sslhashes = get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    
    i = 0
    for key in sorted(segments_hashes.iterkeys()):
        segments_hashes[key] = seller_sslhashes[i]
        i = i + 1 #how do you iterate over a list?
    
    #Having compiled all ssl hashes on seller side and matched them with
    #their frame number in the dict, can isolate the frames which contain
    #the valid ssl
    
    for buyer_provided_hash in sslhashes:
        for segment in segments:
            if buyer_provided_hash == segments_hashes[segment]:
                print "found hash", segments_hashes[segment]
                frames_wanted.append(segment)
                
    if len(frames_wanted) != 2*len(sslhashes): #AG 3 August: best would be to filter out one
                                                #half of the proxy's traffic for 1-1 match
            raise Exception("Couldn't find all SSL frames with given hashes")
    else:
        #prepare the cap file to be sent from gateway user to escrow. Leave only frames wanted, purge the rest.          
        assert frames_wanted > 0, 'zero frames to keep'
        print "All SSL segments found, removing all confidential information from the captured traffic"
        frames_to_keep = sorted(frames_wanted, key=lambda x:int(x))
        highest_frame = frames_to_keep[-1]
        #content type 23 - Application data, we don't want to touch handshake packets
        param = 'ssl.record.content_type == 23 and frame.number <=' + highest_frame
        
        try:
            frames_to_purge_str = tshark('frame.number',seller_dumpcap_capture_file, \
                                         param)
        except:
            print 'Exception in tshark'
            cleanup_and_exit()
        frames_to_purge_str = frames_to_purge_str.rstrip()
        frames_to_purge = frames_to_purge_str.split('\r\n')
        print "Here is frames to purge: "
        print frames_to_purge
        #assert frames_to_purge >= frames_to_keep, 'too many frames to keep'
        #exclude the frames we want to keep from purging
        for frame in frames_to_keep:
            frames_to_purge.remove(frame)
                
        #cut the log to packets from 0 up to the topmost to_keep frame
        
        print "Here is frames to purge after removing frames to keep: "
        print frames_to_purge
        
        try:
            subprocess.Popen([editcap_exepath, seller_dumpcap_capture_file, \
            seller_dumpcap_capture_file+'2', '-r', '0-'+highest_frame])
        except:
            print 'Exception in editcap'
            cleanup_and_exit()
        #purge all ssl packets except for the frames_to_keep
        editcap_args = [editcap_exepath, seller_dumpcap_capture_file+'2', \
                        seller_dumpcap_capture_file+'3']
        for frame in frames_to_purge:
            editcap_args.append(frame)
            
        print "Here is the call to editcap: "
        print editcap_args
        try:
            subprocess.Popen(editcap_args)
        except:
            print 'Exception in editcap'
            cleanup_and_exit()
        #at this point, send the capture to escrow. For testing, save it locally.
        installdir = os.path.dirname(os.path.realpath(__file__))
        shutil.copy(seller_dumpcap_capture_file+'2', os.path.join(installdir,'escrow','escrow.pcap'))
            

#the return value will be placed into HTTP header and sent to buyer. Python has a 64K limit on header size
def seller_get_certificate_verify_message():
    print "Preparing and sending the certificate together with a signature to the buyer"
    with open (os.path.join(installdir, "stunnel", "seller.pem"), "r") as certfile:
        certdata = certfile.read()
    certificate = certdata.__str__()
    #bitcond needs about 10 sec to initialize an empty dir when launched for the first time
    #check if it is finished initializing and is ready for queries. Try 4 times with an interval of 5 sec
    for i in range(4):
        try:
            buyer_bitcoin_rpc.getinfo()
        except:
            if i == 3:
                print "Aborting.Couldn't connect to bitcoind"
                cleanup_and_exit()
            else:
                print 'Failed to connect to bitcoind on try '+ (i+1) +'of4. Sleeping 5 sec.'
                time.sleep(5)
    try:
        signature = seller_bitcoin_rpc.signmessage(seller_addr_funded_multisig, certificate)
    except Exception, e:
        print "Error while invoking signmessage. Did you indicate a valid BTC address?"
        print e
        cleanup_and_exit()
    return signature + ';' + certificate

def seller_start_bitcoind_stunnel_sshpass_dumpcap_squid():
    global pids
    print "Starting bitcoind in offline mode. No part of blockchain will be downloaded"
    try:
       #start bitcoind in offline mode
       bitcoind_proc = subprocess.Popen([bitcoind_exepath, '-datadir=' + os.path.join(installdir, "empty_bitcoin_datadir_seller"), '-maxconnections=0', '-server', '-listen=0', '-rpcuser=ssllog_user', '-rpcpassword=ssllog_pswd', '-rpcport=8339'], stdout=open(os.devnull,'w'), stderr=open(os.devnull,'w'))
    except:
        print 'Exception starting bitcoind'
        cleanup_and_exit()
    pids['bitcoind']  = bitcoind_proc.pid
    
    print "Starting ssh connection to escrow's server"
    try:
        sshpass_proc = subprocess.Popen([sshpass_exepath, '-p', escrow_ssh_pass, ssh_exepath, escrow_ssh_user+'@'+escrow_host, '-R', str(escrow_port)+':localhost:33310'], stdout=open(os.devnull,'w'), stderr=open(os.devnull,'w'))
    except:
        print 'Exception connecting to sshd'
        cleanup_and_exit()
    pids['sshpass']  = sshpass_proc.pid
    
    print "Starting stunnel"
    #stunnel finds paths in .conf relative to working dir
    os.chdir(os.path.join(installdir,'stunnel'))
    try:
        stunnel_proc = subprocess.Popen([stunnel_exepath, os.path.join(installdir, 'stunnel', 'seller.conf')], stdout=open(os.devnull,'w'), stderr=open(os.devnull,'w'))
    except:
        print 'Exception starting stunnel'
        cleanup_and_exit()
    pids['stunnel'] = stunnel_proc.pid
    
    print "Starting squid3"
    try:
        squid3_proc = subprocess.Popen([squid3_exepath], stdout=open(os.devnull,'w'), stderr=open(os.devnull,'w'))
    except:
        print 'Exception starting squid'
        cleanup_and_exit()
    pids['squid3'] = squid3_proc.pid
    
    print "Starting dumpcap capture of loopback traffic"
    try:
        #todo: don't assume that 'lo' is the loopback, query it
        #listen in-between stunnel and squid, filter out all the rest of loopback traffic
        dumpcap_proc = subprocess.Popen([dumpcap_exepath, '-i', 'lo', '-f', 'tcp port 33310', '-w', seller_dumpcap_capture_file ], stdout=open(os.devnull,'w'), stderr=open(os.devnull,'w'))
    except:
        print 'Exception dumpcap tshark'
        cleanup_and_exit()
    pids['dumpcap'] = dumpcap_proc.pid    
    
def buyer_get_and_verify_seller_cert():
    #receive signature and plain_cert as ";" delimited string
    print 'Requesting the certificate from the seller'
    response = requests.head("http://127.0.0.1:4444/certificate", proxies={"http":"http://127.0.0.1:33308"})
    if response.status_code != 200:
        print ("Unable to get seller's certificate")
        cleanup_and_exit()
    message = response.headers['value']
    signature = message[:message.find(";")]
    certificate = message[message.find(";")+1:]
    
    print "Verifying seller's certificate with bitcoind"
    #bitcond needs about 10 sec to initialize an empty dir when launched for the first time
    #check if it is finished initializing and is ready for queries. Try 4 times with an interval of 5 sec
    for i in range(4):
        try:
            buyer_bitcoin_rpc.getinfo()
        except:
            if i == 3:
                print "Aborting.Couldn't connect to bitcoind"
                cleanup_and_exit()
            else:
                print 'Failed to connect to bitcoind on try '+ (i+1) +'of4. Sleeping 5 sec.'
                time.sleep(5)
        
                
    print "Verifying seller's certificate for stunnel"
    try:
        if buyer_bitcoin_rpc.verifymessage(seller_addr_funded_multisig, signature, certificate) != True :
            print ("Failed to verify seller's certificate")
            cleanup_and_exit()
    except Exception,e:
        print 'Exception while calling verifymessage',e
        cleanup_and_exit()
    
    print 'Successfully verified sellers certificate, writing it to disk'
    with open (os.path.join(installdir, "stunnel","verifiedcert.pem"), "w") as certfile:
        certfile.write(certificate)
        

#the tempdir contains html files as well as folders with js,png,css. Ignore the folders
def buyer_get_htmlhashes():
    
    print "Getting hashes of saved html files"
    onlyfiles = [f for f in listdir_fullpath(htmldir) if os.path.isfile(os.path.join(htmldir,f))]
    print onlyfiles
    htmlhashes = []
    for file in onlyfiles:
        htmlhashes.append(hashlib.md5(open(file, 'rb').read()).hexdigest())
    return htmlhashes


#AG: New version 30 July. Minimise the number of tshark calls
#whilst still preserving correct functionality.
#It appears that the hex/ascii dump (-x) is the ONLY way to get the full,
#decrypted data out of the pcap. None of the -e flags work, including -e text
#which seems to produce truncated data. This is annoying, as it means we need to 
#manually read the contents of at least a subset of the frames. 
def buyer_get_sslhashes(htmlhashes):
    print "Finding SSL segments corresponding to the saved html files"
    sslhashes = []
    found_frames = []
    #dict for storing the text corresponding to each frame for
    #searching in memory rather than from tshark:
    frame_data = {} 
    
    #First run of tshark:
    #get frame numbers of all http responses that came from the bank
    try:
        frames_str = subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', \
        'http.response and ssl.app_data', '-T', 'fields', '-e', 'frame.number'])
    except:
        print 'Error starting tshark'
        cleanup_and_exit()
    frames_str = frames_str.rstrip()
    frames = frames_str.split('\r\n')
    
    #second run of tshark is to dump all DATA in the responses (in decrypted form)
    #so as to be able to match htmlhashes, and then record the numbers of the frames
    #in which these occurred
    #Wireshark display filter has no concept of "in" a list, so an ugly concantenated
    #"or" appears to be necessary.
    tshark_args_frames_stub = tshark_exepath + ' -r ' + tshark_capture_file + \
    ' -R "frame.number==' + " or frame.number==".join(frames)
    #for hex-ascii
    tshark_args = tshark_args_frames_stub + '" -x'
        
    try:
        ascii_dump = subprocess.check_output(tshark_args)
    except:
        print 'Error starting tshark'
        cleanup_and_exit()
    
    #split the contents of ascii_dump into one block per frame:
    i=1
    lines = ascii_dump.split('\n')
    for frame in frames:
        frame_data[frame] = '' #need to instantiate the key/val pairs
    
    for frame in frames: 
        while not (i >= len(lines) or lines[i].startswith('Frame')):
            frame_data[frame] += lines[i] + '\n'
            i=i+1
        i=i+1

    for htmlhash in htmlhashes:
        if htmlhash == '':
            print 'empty hash provided. Please investigate'
            cleanup_and_exit()
    
            
        found_frame = False
        for frame in frames:            
            # "-x" dumps ascii info of the SSL frame, de-fragmenting SSL segments,
            # decrypting them, ungzipping (if necessary) and showing plain HTML
            #algorithm: read ascii_dump until see "Frame" at beginning of line
            #the chunk up to that point is output for frame 'frame'
            #search for uncompressed entity body: if found, calc the html hash
            #if it matches, store frame as one of the matched frames for the next
            # step
            md5hash = get_htmlhash_from_asciidump(frame_data[frame])
            if htmlhash == md5hash:
                found_frames.append(frame)
                found_frame = True
                print "found matching SSL segment in frame No " + frame
                break
        if not found_frame:
            print("Couldn't find an SSL segment containing html hash provided")
            cleanup_and_exit()
            
    #collect other possible SSL segments which are part of HTML pages
    #to do this, we run tshark for a third time and collecting a list
    #of frame numbers which contain relevant ssl segments, then we prune
    #it to remove duplicates before the final tshark run. 
    try:
        segments_str = tshark('ssl.segment',tshark_capture_file, filter = '', \
                              frames=found_frames)
    except:
        print 'Error starting tshark'
        cleanup_and_exit()
    segments_str = segments_str.rstrip()
    segments = re.findall('\w+',segments_str) #entries separated by , \r \n
    if len(segments) < 1:
        print 'zero SSL segments, should be at least one. Please investigate'
        cleanup_and_exit()
    #there can be multiple SSL segments in the same frame, so remove duplicates
    segments = set(segments)
    
    try:
        ssl_app_data = tshark('ssl.app_data',tshark_capture_file,filter='', \
                              frames = segments)
    except:
        print 'Error starting tshark'
        cleanup_and_exit()

    ssl_app_data_list = re.findall('\S+',ssl_app_data)
    return get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    

def get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list):
    ssl_hashes = []
    for s in ssl_app_data_list:
        #get rid of commas and colons
        #(ssl.app_data comma-delimits multiple SSL segments within the same frame)
        s = s.rstrip()
        s = s.replace(',',' ')
        s = s.replace(':',' ')
        if s == ' ':
            print 'empty frame hex. Please investigate'
            cleanup_and_exit()
        ssl_hashes.append(hashlib.md5(bytearray.fromhex(s)).hexdigest()) 
        #print "NUmber of hashes is now: ", len(ssl_hashes)
    #print ssl_hashes
    return ssl_hashes

#look at tshark's ascii dump to better understand the parsing taking place
def get_htmlhash_from_asciidump(ascii_dump):
    hexdigits = set('0123456789abcdefABCDEF')
    assert ascii_dump != '', 'empty frame dump'
    html_found = False
    binary_html = bytearray()
    for line in ascii_dump.split('\n'):
        if 'Uncompressed entity body' in line:
            html_found = True
            continue
        if not html_found:
            continue
        if html_found:
            if line == '\n' or line == '':
                continue
            #convert ascii representation of hex into binary
            elif all(c in hexdigits for c in line [:4]):
                m_array = bytearray.fromhex(line[6:54])
                binary_html += m_array
            else:
                break          
    if html_found:
        assert len(binary_html) != 0, 'empty binary array'
        return hashlib.md5(binary_html).hexdigest()
    else:
        print 'Could not find Uncompressed entity body in the frame'

#helper fn for debug/testing
def write_hashes_to_file(hashes):
    print "Writing hashes"
    hashes_string = ""
    for hash in hashes:
        hashes_string += hash+';'
        installdir = os.path.dirname(os.path.realpath(__file__))
        with open (os.path.join(installdir,'output'),"w") as file:
                file.write(hashes_string)

#helper fn for debug/testing
def read_hashes_from_file():
    line = open('output', 'r').read()
    hashes = line.rstrip(';').split(';')
    return hashes

#start processes and return their PIDs for later SIGTERMing
def buyer_start_bitcoind_stunnel_sshpass_dumpcap():
    global pids
    global ppid
    print 'Starting bitcoind'
    try:
        #start bitcoind in offline mode
        bitcoind_proc = subprocess.Popen([bitcoind_exepath, '-datadir=' + os.path.join(installdir, "empty_bitcoin_datadir_buyer"), '-maxconnections=0', '-server', '-listen=0', '-rpcuser=ssllog_user', '-rpcpassword=ssllog_pswd', '-rpcport=8338'])
    except:
        print 'Exception starting bitcoind'
        cleanup_and_exit()
    pids['bitcoind'] = bitcoind_proc.pid
    
    print 'Starting ssh connection'
    try:
        sshpass_proc = subprocess.Popen([sshpass_exepath, '-p', escrow_ssh_pass, ssh_exepath, escrow_ssh_user+'@'+escrow_host, '-L', '33309:localhost:'+str(escrow_port)], stdout=open(os.devnull,'w'))
    except:
        print 'Exception connecting to sshd'
        cleanup_and_exit()
    pids['sshpass'] = sshpass_proc.pid
                   
    print 'Starting stunnel'
#1st invocation of stunnel serves only the purpose of getting the certifcate from the seller
#after receiving the certificate, stunnel is terminated and restarted with the new certfcate
#stunnel finds paths in .conf relative to working dir
    os.chdir(os.path.join(installdir,'stunnel'))
    #try:
        #stunnel_proc = subprocess.Popen([stunnel_exepath, os.path.join(installdir, 'stunnel', 'buyer_pre.conf')])
    #except:
        #print 'Exception starting stunnel'
        #cleanup_and_exit()
    #pids['stunnel'] = stunnel_proc.pid
        
    print 'Making a test connection to example.org through the tunnel'
    #make a test request to see if stunnel setup is working
    try:
        response = requests.get("http://example.org", proxies={"http":"http://127.0.0.1:33308"}, timeout=10)
    except Exception,e:
        print "Error while making a test connection",e
        cleanup_and_exit()
    if response.status_code != 200:
        print ("Seller returned an invalid response")
        print response.text
        cleanup_and_exit()
     
    print 'Starting dumpcap in capture mode'   
    try:
        #todo: don't assume that 'lo' is the loopback, query it
        #listen in-between Firefox and stunnel, filter out all the rest of loopback traffic
        dumpcap_proc = subprocess.Popen([dumpcap_exepath, '-i', 'lo', '-f', 'tcp port 33309', '-w', buyer_dumpcap_capture_file ], stdout=open(os.devnull,'w'), stderr=open(os.devnull,'w'))
    except:
        'Exception starting dumpcap'
        cleanup_and_exit()
    pids['dumpcap'] = dumpcap_proc.pid

#use miniHTTP server to receive commands from Firefox addon and respond to them
def buyer_start_minihttp_thread():
    print 'Starting mini http server to communicate with Firefox plugin'
    try:
        httpd = StoppableHttpServer(('127.0.0.1', 2222), buyer_HandlerClass)
    except Exception, e:
        print 'Error starting mini http server', e
        cleanup_and_exit()
    sa = httpd.socket.getsockname()
    print "Serving HTTP on", sa[0], "port", sa[1], "..."
    httpd.serve_forever()
    
#use miniHTTP server to send certificate and receive SSL hashes
def seller_start_minihttp_thread():
    print "Starting mini http server and waiting for buyer's queries"
    try:
        httpd = StoppableHttpServer(('127.0.0.1', 4444), seller_HandlerClass)
    except Exception, e:
        print 'Error starting mini http server', e
        cleanup_and_exit()
    sa = httpd.socket.getsockname()
    print "Serving HTTP on", sa[0], "port", sa[1], "..."
    sslhashes = httpd.serve_forever()

    #pass retval down to the thread instance
    threading.currentThread.retval = sslhashes
    
def start_firefox():
    #we could ask user to run Firefox with -ProfileManager and create a new profile themselves
    #but to be as user-friendly as possible, we add a new Firefox profile behind the scenes    
    ff_user_dir = os.path.join(homedir, ".mozilla", "firefox")    
    # skip this step if "ssllog" profile already exists
    if (not os.path.isdir(os.path.join(ff_user_dir, "ssllog_profile"))):
        print "Copying plugin files into Firefox's plugin directory"
        homedir = os.path.expanduser("~")
        if homedir == "~":
            #couldn't find user's home directory
            print ("Couldn't find user's home directory")
            cleanup_and_exit()
        #todo allow user to specify firefox profile dir manually
    
        try:
            inifile = open(os.path.join(ff_user_dir, "profiles.ini"), "r+a")
        except: 
            print ('Could not open profiles.ini. Make sure it exists and you have sufficient read/write permissions')
            cleanup_and_exit()
        text = inifile.read()
   
        #get the last profile number and increase it by 1 for our profile
        our_profile_number = int(text[text.rfind("[Profile")+len("[Profile"):].split("]")[0]) +1
    
        try:
            inifile.write('[Profile' +str(our_profile_number) + ']\nName=ssllog\nIsRelative=1\nPath=ssllog_profile\n\n')
        except:
            print ('Could not write to profiles.ini. Make sure you have sufficient write permissions')
            cleanup_and_exit()
        inifile.close()
    
        #create an extension dir and copy the extension files
        #we are not distributing our extension as xpi, but rather as a directory with files
        ff_extensions_dir = os.path.join(ff_user_dir, "ssllog_profile", "extensions")
        os.mkdir(ff_extensions_dir)
        #todo handle mkdir exception
        
        try:
            mfile = open (os.path.join(ff_extensions_dir, "sample@example.net"), "w+")
        except:
            print 'File open error'
            cleanup_and_exit()
        #todo print line number in error messages
        
        #write the path into the file
        try:
            mfile.write(os.path.join(ff_extensions_dir, "ssllog_addon"))
        except:
            print 'File write error'
            cleanup_and_exit()
        
        try:    
            shutil.copytree(os.path.join(installdir,"FF-addon"), os.path.join(ff_extensions_dir, "ssllog_addon"))
        except:
            print 'Error copying addon from installdir'
            cleanup_and_exit()
    
    #empty html files from previous session
    for the_file in os.listdir(htmldir):
        file_path = os.path.join(htmldir, the_file)
        try:
                os.unlink(file_path)
        except Exception, e:
            print 'Error while removing html files from previous session',e
            cleanup_and_exit()
    #todo delete resource directories as well
        
    #SSLKEYLOGFILE
    os.putenv("SSLKEYLOGFILE", sslkeylogfile_path)
    print "Starting a new instance of Firefox with a new profile"
    try:
        subprocess.Popen([firefox_exepath,'-new-instance', '-P', 'ssllog'])
    except:
        print "Error starting Firefox"
        cleanup_and_exit()

#this is just a hex digest of the html
def get_htmlhash_from_html(h):
        return hashlib.md5(h).hexdigest()


pids = dict()
ppid = 0
    
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print 'Please provide one of the arguments: "buyer" or "seller"'
        exit()
    role = sys.argv[1]
    
    #f = open(os.devnull, 'w')
    #sys.stdout = f
    #sys.stderr = f
    
    if role != 'buyer' and role != 'tester' and role != 'seller':
        print 'Unknown argument. Please provide one of the arguments: "buyer" or "seller"'
        exit()
    
    #making this process a leader of the process group
    print '----------------------------MY PID IS ', os.getpid(), '----------------------------'
    print 'Terminate me and my children with "kill -s SIGKILL -"'+str(os.getpid())+' --> (notice the minus) sends to all members of process group'
    signal.signal(signal.SIGTERM, sighandler)
    
       if role=='buyer':
        #global pids
        buyer_start_bitcoind_stunnel_sshpass_dumpcap()
        buyer_get_and_verify_seller_cert()
        os.kill(pids['bitcoind'], signal.SIGTERM)
        pids.pop('bitcoind')
        os.kill(pids['stunnel'], signal.SIGTERM)
        pids.pop('stunnel')
        #let stunnel terminate properly before restarting it
        ttme.sleep(2)
        buyer_start_stunnel_with_certificate()
        thread = threading.Thread(target= buyer_start_minihttp_thread)
        thread.start()
        start_firefox()
        #wait for minihttp server shutdown. Means that user has finished the SSL session
        thread.join()
        print "User has finished the SSL session"
        #todo: inform the seller at this stage that we are finished with the SSL session
        print "Terminating dumpcap"
        os.kill(pids['dumpcap'], signal.SIGTERM)
        pids.pop('dumpcap')
        htmlhashes = buyer_get_htmlhashes()
        sslhashes = buyer_get_sslhashes(htmlhashes)
        buyer_send_sslhashes(sslhashes)
        buyer_send_sslkeylogfile()
        print "Terminating sshpass and stunnel"
        os.kill(pids['sshpass'], signal.SIGTERM)
        os.kill(pids['stunnel'], signal.SIGTERM)
        pids.pop('sshpass')
        pids.pop('stunnel')
        
        
    elif role == 'seller':
        #global pids
        seller_start_bitcoind_stunnel_sshpass_dumpcap_squid()
        #minihttp is responsible for sending the certificate and receiving ssl hashes
        thread = ThreadWithRetval(target= seller_start_minihttp_thread)
        thread.start()
        thread.join()
        #sslhashes have been received, minihttp server stopped. sslhahses are returned through thread's retval
        #stop tshark,ssh,stunnel,squid (if active) and process hashes
        print "Terminating bitcoind, dumpcap, squid, sshpass, and stunnel"
        for pid in [item for item in pids.items() if item[0] in ['bitcoind','dumpcap','squid3','sshpass','stunnel']]:
            os.kill(pid[1], signal.SIGTERM)
            pids.pop(pid[0])
        hashes = [hash for hash in thread.retval.split(';') if len(hash)>0]
        send_logs_to_escrow(hashes)
        
       

                             
