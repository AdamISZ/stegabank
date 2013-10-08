#MessageWrapper.py
#this will provide a public interface to low level messaging functionality
#which can therefore be swapped in/out

#*********LIBRARY IMPORTS************
#current implementation: pika/rabbitMQ/AMQP
#this may be seen as overkill but it is flexible and performant
#and open source
import pika
import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import time

#************************************


#++++++++GLOBALS++++++++++++++++++++
#for simplicity we utilise only one exchange with a fixed name
EXCN = 'ssllog_main'

#a temporary buffer for storing sets of messages received
#from the MQ server. Clients of this module should NOT
#rely on its contents!
response={}

chan = None
#+++++++++++++++++++++++++++++++++++

def instantiateConnection(un='guest',pw='guest'):
    global chan
    try:
        pp = 'amqp://'+un+':'+pw+'@'+\
        g("Escrow","escrow_host")+':'+g("Escrow","rabbitmq_port")+'/%2f'
        shared.debug(0,["Set parameter string to:",pp])
        parameters = pika.URLParameters(pp)
        conn = pika.BlockingConnection(parameters)
        chan = conn.channel()
    except:
        #TODO handle connection failure gracefully
        shared.debug(0,["Critical error: cannot connect to host:",\
                    g("Escrow","escrow_host")])
        exit(1)

        
#interface: the arguments must be:
#messages - a dict of form {'topic':'message','topic':'message',..}
#recipientID - a unique ID representing one or more recipients - this will
#be used to choose the correct queue/binding in rabbit MQ. The message format is
#specified in MessageRules.txt in this directory.
#server - the IP address of the host on which the rabbitMQ server is running
def sendMessages(messages={},recipientID='escrow'):
    global chan    
    #todo: error handling in this function
    shared.debug(1,["Attempting to send message(s): \n",messages,\
                        " to recipient: ",recipientID,'\n'])
    
    #26 Sep 2013: the model which best fits simple message seems
    #to be declaration of static queues for each route (see 1st tutorial on 
    #rabbitmq python tutorials),
    #rather than dynamic routing with topic type exchange; the problem
    #with the latter is that queues are ephemeral and if we publish to 
    #a routing key with no current consumers, the message just drops into
    #the void.
    chan.queue_declare(recipientID)
    
    for hdr,msg in messages.iteritems():
        shared.debug(0,["about to send a message:"])
        chan.basic_publish(exchange='',\
        routing_key=recipientID,body='|'.join([hdr,msg]))
        
    return True

def getSingleMessage(recipientID,timeout=1):
    global chan 
    chan.queue_declare(queue=recipientID)
    for i in range(1,timeout+1):
        if timeout>1:
            time.sleep(1)
        method_frame,header_frame,body = chan.basic_get(queue=recipientID,\
                                                        no_ack=True)
        if not method_frame:
            continue
        else:
            if '|' not in body:
                shared.debug(0,["Format error in message:",body,";message ignored"])
                return None
            else:
                msg = body.split('|')
                #bugfix 8 Oct 2013: there can be a | in the message!!
                return {msg[0]:'|'.join(msg[1:])}
        
    
#interface: the arguments must be:
#recipientID - the unique ID of the agent who receives all messages for them
#all messages will be returned in a dict for processing
def collectMessages(recipientID):
    global chan
           
    #parse the argument into a set of routing keys
    #todo: understand the rule of this better - may need to change
    routing_keys = [recipientID]
        
    global response
        
    #see equiv in sendMessages
    chan.queue_declare(recipientID)
        
    for k in routing_keys:
        #collect all messages due for the channel chan
        chan.basic_consume(collectMessagesCallback,queue=recipientID,no_ack=True)
    
    returned_msgs = response if response else None
        
    #clean the buffer for next time
    response = {}
        
    #note that a null return should just be interpreted as 'no messages';
    #although there may of course be errors under the hood that is nobody's
    #business!
    return returned_msgs
            
        
def collectMessagesCallback(ch, method,properties,body):
    global response
    shared.debug(2,["We received messages:",body])
    #shared.debg(2,["Properties were: ",properties])
    #parse the messages into a dict structure
    if '|' not in body:
        shared.debug(0,["Format error in message:",body,";message ignored"])
        return None
    else:
        msg = body.split('|')
        response[msg[0]]=msg[1]
        
        
        