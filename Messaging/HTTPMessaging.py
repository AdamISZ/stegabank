import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import base64
import requests
import BaseHTTPServer, SimpleHTTPServer
import threading
import time
import signal
import inspect
import traceback


class AgentHandler(SimpleHTTPServer.SimpleHTTPRequestHandler, object):
    protocol_version = "HTTP/1.1"
    #Firefox addon speaks with HEAD
    def do_HEAD(self):
        print ('minihttp received ' + self.path + ' request',end='\r\n')
        if self.path == '/status':
            self.send_response(200)
            self.send_header("response", "status")
            self.send_header("value", "pending")
            super(AgentHandler, self).do_HEAD()
        elif self.path == '/tempdir':
            self.send_response(200)
            self.send_header("response", "tempdir")
            self.send_header("value",g("Directories","escrow_base_dir"))
            super(AgentHandler, self).do_HEAD()
        elif self.path == '/finished':
            self.send_response(200)
            self.send_header("response", "finished")
            self.send_header("value", "ok")
            super(AgentHandler, self).do_HEAD()
            self.server.stop = True
                
class StoppableHttpServer (BaseHTTPServer.HTTPServer):
    """http server that reacts to self.stop flag"""
    retval = ''
    def serve_forever (self):
        """Handle one request at a time until stopped. Optionally return a value"""
        self.stop = False
        while not self.stop:
                self.handle_request()
        return self.retval
 
class HTTPFinishedException(Exception):
    pass

class MessagingHTTPServerThread(object):
    def __init__(self,retval,host='127.0.0.1',port=-1):
        try:
            self.httpd = StoppableHttpServer((host, port), AgentHandler)
        except Exception, e:
        print ('Error starting mini http server', e,end='\r\n')
    
    def run():
        sa = httpd.socket.getsockname()
        print ("Serving HTTP on", sa[0], "port", sa[1], "...",end='\r\n')
        return httpd.serve_forever()