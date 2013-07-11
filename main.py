import sys
import subprocess
import shutil
import os
import signal
import requests
import BaseHTTPServer
import threading
import time
from bitcoinrpc import authproxy

#receive HEAD HTTP requests and respond to them
class buyer_HandlerClass(BaseHTTPServer.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_HEAD(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header("response", "status")
            self.send_header("value", "pending")
            self.end_headers()
        elif self.path == '/tempdir':
            self.send_response(200)
            self.send_header("response", "tempdir")
            self.send_header("value", "/tmp/random1234")
            self.end_headers()
        elif self.path == '/finished':
            self.send_response(200)
            self.send_header("response", "finished")
            self.send_header("value", "ok")
            self.end_headers()
            

class seller_HandlerClass(BaseHTTPServer.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def do_HEAD(self):
        if self.path == '/certificate':
            message = seller_get_certificate_verify_message()
            self.send_response(200)
            self.send_header("response", "certificate")
            self.send_header("value", message)
            self.end_headers()
        elif self.path == '/tempdir':
            self.send_response(200)
            self.send_header("response", "tempdir")
            self.send_header("value", "/tmp/random1234")
            self.end_headers()
        elif self.path == '/finished':
            self.send_response(200)
            self.send_header("response", "finished")
            self.send_header("value", "ok")
            self.end_headers()
            
            

OS = ''
if !sys.platform.find('linux'):
    OS = 'linux'
else:
    OS = 'unknown'

role = 'buyer'    
ssllog_installdir = '/home/default/Desktop/sslxchange'
stunnel_exepath = '/home/default/Desktop/sslxchange/stunnel-4.56/src/stunnel'
sshclient_exepath = '/usr/bin/ssh'
firefox_exepath = ''
bitcoind_exepath = ''
tshark_exepath = ''
buyer_tshark_capture_file= '/tmp/buyer_tshark.pcap'
seller_tshark_capture_file= '/tmp/seller_tshark.pcap'
ssl_keylogfile_path = ''
#dir where firefox saves the pages for escrow
tempdir = ''
squid_exe_path = ''


#if OS == 'linux':
    #proc = subprocess.Popen(["which", "firefox"], stdout=subprocess.PIPE)
    #firefox_exepath = proc.stdout.read().rstrip()
    #if firefox_exepath == "":
        #raise Exception ("Could not find Firefox")

seller_addr_funded_multisig = "19CzQYZGiaENfypuNzMAf3Mg4vs5oE1hgV"
bitcoin_rpc = authproxy.AuthServiceProxy("http://ssllog_user:ssllog_pswd@127.0.0.1:8332")
escrow_host = '1.2.3.4'
escrow_port = 12345
#seller should pass the certificate_message via some external means, like the exchange website or Bitmessage
certificate_message = ''

if role=='buyer':
    start_bitcoind()
    pids = buyer_start_stunnel_ssh_tshark()
    buyer_get_and_verify_seller_cert()
    os.kill(pids['stunnel'], signal.SIGTERM)
    #let stunnel terminate properly before restarting it
    ttme.sleep(3)
    stunnel_pid = buyer_start_stunnel_with_certificate()
    pids = {'stunnel':stunnel_pid}
    thread = threading.Thread(target= buyer_start_minihttp_thread)
    thread.start()
    start_firefox()
    #wait for minihttp server shutdown. Means that user has finished the SSL session
    thread.join()
    #todo: inform the seller at this stage that we are finished with the SSL session
    os.kill(pids['tshark'], signal.SIGTERM)
    htmlhashes = buyer_get_htmlhashes(tempdir)
    sslhashes = buyer_get_sslhashes(htmlhashes)
    buyer_send_sslhashes(sslhashes)
    buyer_send_sslkeylogfile()
    os.kill(pids['ssh'], signal.SIGTERM)
    os.kill(pids['stunnel'], signal.SIGTERM)
    
if role = 'seller':
    pids = seller_start_stunnel_ssh_tshark_squid()
    #minihttp is responsible for sending the certificate and receiving ssl hashes
    thread = threading.Thread(target= seller_start_minihttp_thread)
    thread.start()
    thread.join()
    #wait for buyer to signal that he is ready
    seller_send_certificate()
    #receive STOP signal & stop tshark, receive sslhashes
    send_logs_to_escrow()
    
#send all the hashes in an HTTP HEAD request    
def buyer_send_sslhashes(sslhashes):
    hashes_string = ''
    for hash in sslhashes:
        hashes_string += ';'+hash
    message = requests.head("http://127.0.0.1:4444/hashes="+hashes_string, proxies={"http":"http://127.0.0.1:33309"})
    if message.status_code != 200:
       raise "Unable to send SSL hashes to seller"

#send sslkeylog to escrow. For testing purposes we can send it to seller.
#NB! There is probably a limit on header size in python
def buyer_send_sslkeylogfile():
    with open (ssl_keylogfile_path, "r") as file:
        data = file.read()
    keylogfile_ascii = data.__str__()
    message = requests.head("http://127.0.0.1:4444/sslkeylogfile="+keylogfile_ascii, proxies={"http":"http://127.0.0.1:33309"})
    if message.status_code != 200:
       raise "Unable to send SSL keylogfile to escrow"

    
    
def buyer_start_stunnel_with_certificate():
    try:
        stunnel_proc = subprocess.Popen([stunnel_exepath, os.path.join(ssllog_installdir, 'stunnel', 'buyer.conf')])
    except:
        'Exception starting stunnel'
        
    #make a test request to see if stunnel setup is working
    response = requests.get("http://example.org", proxies={"http":"http://127.0.0.1:33309"})
    if response.status_code != 200:
        raise "Unable to make a test connection through seller's proxy"
    return stunnel_proc.pid


def send_logs_to_escrow(sslhashes):
    assert len(ssl_hashes) > 0, 'zero hashes provided'
    frames_wanted = []
    #we're only concerned with 
    frames_str = subprocess.check_output([tshark_exepath, '-r', seller_tshark_capture_file, '-R', 'ssl.record.content_type == 23', '-T', 'fields', '-e', 'frame.number'])
    frames_str = frames_str.rstrip()
    ssl_frames = frames_str.split('\n')
    print 'need to process frames:', len(ssl_frames)
    for frame in sorted(ssl_frames, key=lambda x:int(x), reverse=True):
        print 'processing frame', frame
        frame_ssl_hex = subprocess.check_output(['tshark', '-r', '/home/default/Desktop/capture', '-R', 'frame.number==' + frame, '-T', 'fields', '-e', 'ssl.app_data'])
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
        frames_to_keep = sorted(frames_to_keep, key=lambda x:int(x))
        highest_frame = frames_to_keep[-1]
        #content type 23 - Application data, we don't want to touch handshake packets
        param = 'ssl.record.content_type == 23 and frame.number <=' + highest_frame
        frames_to_purge_str = subprocess.check_output(['tshark', '-r', '/home/default/Desktop/capture', '-R', param, '-T', 'fields', '-e', 'frame.number'])
        frames_to_purge_str = frames_to_purge_str.rstrip()
        frames_to_purge = frames_to_purge_str.split('\n')
        assert frames_to_purge >= frames_to_keep, 'too many frames to keep'
        #exclude the frames we want to keep from purging
        for frame in frames_to_keep:
            frames_to_purge.remove(frame)
                
        #cut the log to packets from 0 up to the topmost to_keep frame
        subprocess.check_output(['editcap', '/home/default/Desktop/capture', '/home/default/Desktop/capture_2', '-r', '0-'+highest_frame])
        #purge all ssl packets except for the frames_to_keep
        editcap_args = ['editcap', '/home/default/Desktop/capture_2', '/home/default/Desktop/capture_3']
        for frame in frames_to_purge:
            editcap_args.append(frame)
        subprocess.check_output(editcap_args)

    
    
    
    
    
    
def seller_get_certificate_verify_message():
    with open (os.path.join(ssllog_installdir, "stunnel", "seller.pem"), "r") as certfile:
        certdata = certfile.read()
    certificate = certdata.__str__()
    signature = bitcoin_rpc.signmessage(seller_addr_funded_multisig, certificate)
    return signature + ';' + certificate
    

def seller_start_stunnel_ssh_tshark_squid():
    pids = {}
    try:
        sshclient_proc = subprocess.Popen([sshclient_exepath, 'user@'+escrow_host, '-R', escrow_port+':localhost:33310'])
    except:
        'Exception connecting to sshd'
    pids = {'ssh':sshclient_proc.pid}
    
    try:
        stunnel_proc = subprocess.Popen([stunnel_exepath, os.path.join(ssllog_installdir, 'stunnel', 'seller.conf')])
    except:
        'Exception starting stunnel'
    pids = {'stunnel':stunnel_proc.pid}
    
    try:
        squid_proc = subprocess.Popen([squid_exe_exepath])
    except:
        'Exception starting squid'
    pids = {'squid':squid_proc.pid}
    
    try:
        #todo: don't assume that 'lo' is the loopback, query it
        #listen in-between stunnel and squid, filter out all the rest of loopback traffic
        tshark_proc = subprocess.Popen([tshark_exepath, '-i', 'lo', '-f', 'tcp port 33310', '-w', seller_tshark_capture_file ])
    except:
        'Exception starting tshark'
    pids = {'tshark':tshark_proc.pid}
    return pids
    
    
    
    
    
#start bitcoind in offline mode
def start_bitcoind():
    subprocess.Popen([bitcoind_exepath, '-datadir=' + os.path.join(ssllog_installdir, "empty_bitcoin_datadir"), '-maxconnections=0', '-server', '-rpcuser=ssllog_user', '-rpcpassword=ssllog_pswd'])

def buyer_get_and_verify_seller_cert():
    #receive signature and plain_cert as ";" delimited string
    message = requests.head("http://127.0.0.1;4444/certificate", proxies={"http":"http://127.0.0.1:33309"})
    if message.status_code != 200:
        raise "Unable to get seller's certificate"
    signature = message[:message.find(";")]
    certificate = message[message.find(";")+1:]
    if bitcoin_rpc.verifymessage(seller_addr_funded_multisig, signature, certificate) != True :
        raise Exception ("Failed to verify seller's message")
    with open (os.path.join(ssllog_installdir, "stunnel","verifiedcert.pem"), "w") as certfile:
        certfile.write(certificate)
    

#start processes and return their PIDs for later SIGTERMing
def buyer_start_stunnel_ssh_tshark():
    pids = {}
    try:
        sshclient_proc = subprocess.Popen([sshclient_exepath, 'user@'+escrow_host, '-L', '33309:localhost:'+escrow_port])
    except:
        'Exception connecting to sshd'
    pids = {'ssh':sshclient_proc.pid}
           
#1st invocation of stunnel serves only the purpose of getting the certifcate from the seller
#after receiving the certificate we termnate stunnel and restart it with the new certfcate
    try:
        stunnel_proc = subprocess.Popen([stunnel_exepath, os.path.join(ssllog_installdir, 'stunnel', 'buyer_pre.conf')])
    except:
        'Exception starting stunnel'
    pids = {'stunnel':stunnel_proc.pid}
        
    #make a test request to see if stunnel setup is working
    response = requests.get("http://example.org", proxies={"http":"http://127.0.0.1:33309"})
    if response.status_code != 200:
        raise "Unable to make a test connection through seller's proxy"
        
    try:
        #todo: don't assume that 'lo' is the loopback, query it
        #listen in-between Firefox and stunnel, filter out all the rest of loopback traffic
        tshark_proc = subprocess.Popen([tshark_exepath, '-i', 'lo', '-f', 'tcp port 33309', '-w', buyer_tshark_capture_file ])
    except:
        'Exception starting tshark'
    pids = {'tshark':tshark_proc.pid}
    return pids



#use miniHTTP server to receive commands from Firefox addon and respond to them
def buyer_start_minihttp_thread():
    httpd = BaseHTTPServer.HTTPServer(('127.0.0.1', 2222), buyer_HandlerClass)
    sa = httpd.socket.getsockname()
    print "Serving HTTP on", sa[0], "port", sa[1], "..."
    httpd.serve_forever()
    
#use miniHTTP server to send certificate and receive SSL hashes
def seller_start_minihttp_thread():
    httpd = BaseHTTPServer.HTTPServer(('127.0.0.1', 4444), seller_HandlerClass)
    sa = httpd.socket.getsockname()
    print "Serving HTTP on", sa[0], "port", sa[1], "..."
    httpd.serve_forever()
    
def start_firefox():
    #we could ask user to run Firefox with -ProfileManager and create a new profile themselves
    #but to be as user-friendly as possible, we add a new Firefox profile behind the scenes    
    homedir = os.path.expanduser("~")
    if homedir == "~":
        #couldn't find user's home directory
        raise Exception ("Couldn't find user's home directory")
    #todo allow user to specify firefox profile dir manually
    
    ff_user_dir = os.path.join(homedir, ".mozilla", "firefox")
    try:
        inifile = open(os.path.join(ff_user_dir, "profiles.ini"), "r+a")
    except: 
        'Could not open profiles.ini. Make sure it exists and you have sufficient read/write permissions"
    text = inifile.read()
    # make sure that "ssllog" profile doesn't exist"
    if !os.path.isdir(os.path.join(ff_user_dir, "ssllog_profile")):
        #get the last profile number and increase it by 1 for our profile
        our_profile_number = int(text[text.rfind("[Profile")+len("[Profile"):].split("]")[0]) +1
    
        try:
            inifile.write('[Profile' +str(our_profile_number) + ']\nName=ssllog\nIsRelative=1\nPath=ssllog_profile\n\n')
        except:
            'Could not write to profiles.ini. Make sure you have sufficient write permissions"
            inifile.close()
    
        #create an extension dir and copy the extension files
        #we are not distributing our extension as xpi, but rather as a directory with files
        ff_extensions_dir = os.path.join(ff_user_dir, "ssllog_profile", "extensions")
        os.mkdir(ff_extensions_dir)
        #todo handle mkdir exception
        try:
            mfile = open (os.path.join(ff_extensions_dir, "sample@example.net"), "w+"):
        except:
            'File open error'
        #todo print line number in error messages
        
        try:
            mfile.write(os.path.join(ff_extensions_dir, "ssllog_addon"))
        except:
            'File write error'
        
        try:    
            shutil.copytree(os.path.join(ssllog_installdir,"FF-addon"), os.path.join(ff_extensions_dir, "ssllog_addon"))
        except:
            'Error'
            
    #SSLKEYLOGFILE
    os.putenv("SSLKEYLOGFILE", sslkeylogfile_path)
    subprocess.Popen([firefox_exepath,'-new-instance', '-P', 'ssllog'])
    

#the tempdir contains html files as well as folders with js,png,css. Ignore the folders
def buyer_get_htmlhashes(tempdir):
    onlyfiles = [f for f in os.listdir(tempdir) if os.path.isfile(os.path.join(tempdir,f))]
    htmlhashes = []
    for file in onlyfiles:
        htmlhashes.append(hashlib.md5(open(file, 'r').read()).hexdigest())
    return htmlhashes

#Find the frame which contains the html hash and return the frame's SSL part hash
def buyer_get_sslhashes(htmlhashes):
    sslhashes = []
    for htmlhash in htmlhashes:
        assert htmlhashes != '', 'empty hash provided'
        #get frame numbers of all http responses that came from the bank
        frames_str = subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'http.response', '-T', 'fields', '-e', 'frame.number'])
        frames_str = frames_str.rstrip()
        frames = frames_str.split('\n')
        found_frame = 0
        for frame in frames:
            # "-x" dumps ascii info of the SSL frame, de-fragmenting SSL segments, decrypting them, ungzipping (if necessary) and showing plain HTML
            ascii_dump = subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'frame.number==' + frame, '-x'])
            md5hash = get_htmlhash_from_asciidump(ascii_dump)
            if htmlhash == md5hash:
                found_frame = frame
                print "found md5 match in frame No " + frame
                break
        if not found_frame:
            raise Exception("Couldn't find an SSL frame containing html hash provided")
        
        #collect other possible SSL segments which are part of HTML page 
        segments_str =  subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'frame.number==' + found_frame, '-T', 'fields', '-e', 'ssl.segment'])
        segments_str = segments_str.rstrip()
        segments = segments_str.split(',')
        assert len(segments) > 1, 'zero SSL segments, should be at least one'
        #there can be multiple SSL segments in the same frame, so remove duplicates
        segments = set(segments)
        
        for segment in segments:
            frame_ssl_hex = subprocess.check_output([tshark_exepath, '-r', tshark_capture_file, '-R', 'frame.number==' + segment, '-T', 'fields', '-e', 'ssl.app_data'])
            frame_ssl_hex = frame_ssl_hex.rstrip()
            #get rid of commas and colons
            #(ssl.app_data comma-delimits multiple SSL segments within the same frame)
            frame_ssl_hex = frame_ssl_hex.replace(',',' ')
            frame_ssl_hex = frame_ssl_hex.replace(':',' ')
            assert frame_ssl_hex != ' ', 'empty frame hex'
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