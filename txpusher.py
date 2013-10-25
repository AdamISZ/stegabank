import random, re, errno, os
import sys, time, json 
import socks
import socket

DEFAULT_SERVERS = {
    'electrum.coinwallet.me': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.hachre.de': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.novit.ro': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.stepkrav.pw': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    #'ecdsa.org': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.no-ip.org': {'h': '80', 's': '50002', 't': '50001', 'g': '443'},
    'electrum.drollette.com': {'h': '5000', 's': '50002', 't': '50001', 'g': '8082'},
    'btc.it-zone.org': {'h': '80', 's': '110', 't': '50001', 'g': '443'},
    'btc.medoix.com': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'spv.nybex.com': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.pdmc.net': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'},
    'electrum.be': {'h': '8081', 's': '50002', 't': '50001', 'g': '8082'}
}

is_connected = False
#socket
s=None

def send_tx(raw_tx):
    #try sending out our tx at 11 locations
    global s
    for i in range(1,11):
        serveritem = random.choice(list(DEFAULT_SERVERS.keys()))#list for Py3 compat.
        host = serveritem
        port = DEFAULT_SERVERS[host]['t'] #t=tcp to avoid cert. issues with ssl
        
        #TCP socket setup
        s = socket.socket( socket.AF_INET, socket.SOCK_STREAM )
        s.settimeout(2)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        try:
            s.connect(( host.encode('ascii'), int(port)))
        except:
            print "failed to connect to:", host, str(port)
            continue #try the next server

        s.settimeout(60)
        is_connected = True
        print "connected to", host, str(port)
        if send_tcp([('blockchain.transaction.broadcast', [str(raw_tx)])]):
            return True
    print "Failed to send the transaction to any server"
    socketstop()
        
        
    

def send_tcp(messages):
    global s
    out = ''
    message_id=1
    unanswered_requests={}
    for m in messages:
        method, params = m 
        request = json.dumps( { 'id':message_id, 'method':method, 'params':params } )
        unanswered_requests[message_id] = method, params
        print "-->", request
        message_id += 1
        out += request + '\n'
        while out:
            try:
                sent = s.send( out )
                out = out[sent:]
            except socket.error,e:
                if e[0] in (errno.EWOULDBLOCK,errno.EAGAIN):
                    print_error( "EAGAIN: retrying")
                    time.sleep(0.1)
                    continue
                else:
                    # this happens when we get disconnected
                    print "Not connected, cannot send"
                    return False
    return True



def socketstop():
    if is_connected and s:
        s.shutdown(socket.SHUT_RDWR)
        s.close()
