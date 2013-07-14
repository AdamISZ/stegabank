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


def send_logs_to_escrow(sslhashes):
    print "Findind SSL segments in captured traffic"
    assert len(ssl_hashes) > 0, 'zero hashes provided'
    frames_wanted = []
    #we're only concerned with 
    try:
        frames_str = subprocess.check_output([tshark_exepath, '-r', seller_dumpcap_capture_file, '-R', 'ssl.record.content_type == 23', '-T', 'fields', '-e', 'frame.number'])
    except:
        print 'Exception in tshark'
        cleanup_and_exit()
    frames_str = frames_str.rstrip()
    ssl_frames = frames_str.split('\n')
    print 'need to process frames:', len(ssl_frames)
    for frame in sorted(ssl_frames, key=lambda x:int(x), reverse=True):
        print 'processing frame', frame
        try:
            frame_ssl_hex = subprocess.check_output(['tshark', '-r', seller_dumpcap_capture_file, '-R', 'frame.number==' + frame, '-T', 'fields', '-e', 'ssl.app_data'])
        except:
            print 'Exception in tshark'
            cleanup_and_exit()
        frame_ssl_hex = frame_ssl_hex.rstrip()
        #get rid of commas and colons
        #(ssl.app_data comma-delimits multiple SSL segments within the same frame)
        frame_ssl_hex = frame_ssl_hex.replace(',',' ')
        frame_ssl_hex = frame_ssl_hex.replace(':',' ')
        ssl_md5 = hashlib.md5(bytearray.fromhex(frame_ssl_hex)).hexdigest()
        if ssl_md5 in ssl_hashes:
            print "found hash", ssl_md5
            frames_wanted.append(frame)
            if len(frames_wanted) == len(ssl_hashes):
                break
    if len (frames_wanted) < 1:
        raise Exception("Couldn't find all SSL frames with given hashes")
    else:
        #prepare the cap file to be sent from gateway user to escrow. Leave only frames wanted, purge the rest.          
        assert frames_to_keep > 0, 'zero frames to keep'
        print "All SSL segments found, removing all confidential information from the captured traffic"
        frames_to_keep = sorted(frames_to_keep, key=lambda x:int(x))
        highest_frame = frames_to_keep[-1]
        #content type 23 - Application data, we don't want to touch handshake packets
        param = 'ssl.record.content_type == 23 and frame.number <=' + highest_frame
        try:
            frames_to_purge_str = subprocess.check_output(['tshark', '-r', seller_dumpcap_capture_file, '-R', param, '-T', 'fields', '-e', 'frame.number'])
        except:
            print 'Exception in tshark'
            cleanup_and_exit()
        frames_to_purge_str = frames_to_purge_str.rstrip()
        frames_to_purge = frames_to_purge_str.split('\n')
        assert frames_to_purge >= frames_to_keep, 'too many frames to keep'
        #exclude the frames we want to keep from purging
        for frame in frames_to_keep:
            frames_to_purge.remove(frame)
                
        #cut the log to packets from 0 up to the topmost to_keep frame
        try:
            subprocess.Popen(['editcap', seller_dumpcap_capture_file, seller_dumpcap_capture_file+'2', '-r', '0-'+highest_frame])
        except:
            print 'Exception in editcap'
            cleanup_and_exit()
        #purge all ssl packets except for the frames_to_keep
        editcap_args = ['editcap', seller_dumpcap_capture_file+'2', seller_dumpcap_capture_file+'3']
        for frame in frames_to_purge:
            editcap_args.append(frame)
        try:
            subprocess.Popen(editcap_args)
        except:
            print 'Exception in editcap'
            cleanup_and_exit()
        #at this point, send the capture to escrow. For testing, save it locally.
        shutil.copy(seller_dumpcap_capture_file+'3', os.path,join(installdir,'escrow','escrow.pcap'))
        

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
    

#the tempdir contains html files as well as folders with js,png,css. Ignore the folders
def buyer_get_htmlhashes():
    print "Getting hashes of saved html files"
    onlyfiles = [f for f in os.listdir(htmldir) if os.path.isfile(os.path.join(htmldir,f))]
    htmlhashes = []
    for file in onlyfiles:
        htmlhashes.append(hashlib.md5(open(file, 'r').read()).hexdigest())
    return htmlhashes

#Find the frame which contains the html hash and return the frame's SSL part hash
def buyer_get_sslhashes(htmlhashes):
    print "Finding SSL segments corresponding to the saved html files"
    sslhashes = []
    for htmlhash in htmlhashes:
        if htmlhashes != '':
            print 'empty hash provided. Please investigate'
            cleanup_and_exit()
        #get frame numbers of all http responses that came from the bank
        try:
            frames_str = subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'http.response', '-T', 'fields', '-e', 'frame.number'])
        except:
            print 'Error starting tshark'
            cleanup_and_exit()
        frames_str = frames_str.rstrip()
        frames = frames_str.split('\n')
        found_frame = 0
        for frame in frames:
            # "-x" dumps ascii info of the SSL frame, de-fragmenting SSL segments, decrypting them, ungzipping (if necessary) and showing plain HTML
            try:
                ascii_dump = subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'frame.number==' + frame, '-x'])
            except:
                print 'Error starting tshark'
                cleanup_and_exit()
            md5hash = get_htmlhash_from_asciidump(ascii_dump)
            if htmlhash == md5hash:
                found_frame = frame
                print "found matching SSL segment in frame No " + frame
                break
        if not found_frame:
            print("Couldn't find an SSL segment containing html hash provided")
            cleanup_and_exit()
            
        #collect other possible SSL segments which are part of HTML page 
        try:
            segments_str =  subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'frame.number==' + found_frame, '-T', 'fields', '-e', 'ssl.segment'])
        except:
            print 'Error starting tshark'
            cleanup_and_exit()
        segments_str = segments_str.rstrip()
        segments = segments_str.split(',')
        if len(segments) > 1:
            print 'zero SSL segments, should be at least one. Please investigate'
            cleanup_and_exit()
        #there can be multiple SSL segments in the same frame, so remove duplicates
        segments = set(segments)
        
        for segment in segments:
            try:
                frame_ssl_hex = subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'frame.number==' + segment, '-T', 'fields', '-e', 'ssl.app_data'])
            except:
                print 'Error starting tshark'
                cleanup_and_exit()
            frame_ssl_hex = frame_ssl_hex.rstrip()
            #get rid of commas and colons
            #(ssl.app_data comma-delimits multiple SSL segments within the same frame)
            frame_ssl_hex = frame_ssl_hex.replace(',',' ')
            frame_ssl_hex = frame_ssl_hex.replace(':',' ')
            if frame_ssl_hex != ' ':
                print 'empty frame hex. Please investigate'
                cleanup_and_exit()
            sslhashes.append(hashlib.md5(bytearray.fromhex(frame_ssl_hex)).hexdigest())
    return sslhashes

#look at tshark's ascii dump to better understand the parsing taking place
def get_htmlhash_from_asciidump(ascii_dump):
    hexdigits = set('0123456789abcdefABCDEF')
    assert asci_dump != '', 'empty frame dump'
    html_found = False
    binary_html = bytearray()
    for line in asci_dump.split('\n'):
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
        raise Exception('Could not find Uncompressed entity body in the frame')
    
def cleanup_and_exit():
    global pids
    for pid in [item[1] for item in pids.items()]:
        os.kill(pid, signal.SIGTERM)
    os._exit(1) # <--- a hackish way to kill process from a thread
    #os.kill(os.getpid(), signal.SIGINT) <-- didn't work
    #sys.exit(1)
    #sys.exit doesn't work if this function is invoked from a thread - only the thread stops, not the main process

def sighandler(signal, frame):
    cleanup_and_exit()

pids = dict()
ppid = 0
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print 'Please provide one of the arguments: "buyer" or "seller"'
        exit()
    role = sys.argv[1]
    if role != 'buyer' and role != 'seller':
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
    
#OS = ''
#if !sys.platform.find('linux'):
    #OS = 'linux'
#else:
    #OS = 'unknown'

        
#if OS == 'linux':
    #proc = subprocess.Popen(["which", "firefox"], stdout=subprocess.PIPE)
    #firefox_exepath = proc.stdout.read().rstrip()
    #if firefox_exepath == "":
        #raise Exception ("Could not find Firefox")
