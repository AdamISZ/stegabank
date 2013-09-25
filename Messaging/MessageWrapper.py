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
#************************************


#++++++++GLOBALS++++++++++++++++++++
#for simplicity we utilise only one exchange with a fixed name
EXCN = 'ssllog_main'

#a temporary buffer for storing sets of messages received
#from the MQ server. Clients of this module should NOT
#rely on its contents!
response={}
#+++++++++++++++++++++++++++++++++++


#instantiate a connection to the host on startup
#since Python ensures only one import, this should be called once per process
try:
    conn = pika.BlockingConnection(pika.ConnectionParameters(\
                                        host=g("Escrow","escrow_host")))
except:
    #TODO handle connection failure gracefully
    shared.debug(0,["Critical error: cannot connect to host:",\
                    g("Escrow","escrow_host")])
    exit(1)
            
#interface: the arguments must be:
#messages - a dict of form {'topic':'message','topic':'message',..}
#recipientID - a unique ID representing one or more recipients - this will
#be used to choose the correct queue/binding in rabbit MQ. The format is
#specified in MessageRules.txt in this directory.
#server - the IP address of the host on which the rabbitMQ server is running
def sendMessages(messages={},recipientID='escrow',server=''):
        #todo: error handling in this function
        shared.debug(1,["Attempting to send message(s): \n",messages,\
                        " to recipient: ",recipientID,'\n'])
        
        chan = conn.channel()
        
        
        #the 'topic' exchange type is the most flexible; for basic idea see
        #https://www.rabbitmq.com/tutorials/tutorial-five-python.html
        chan.exchange_declare(exchange=EXCN,type='topic')
        
        #notice we don't need to declare a queue; we're letting the exchange
        #figure out the right queues to publish to based on the topic
        for hdr,msg in messages.iteritems():
            channel.basic_publish(exchange=EXCN,\
            routing_key=recipientID,body='|'.join(hdr,msg))
        #is this needed or possible?
        #conn.close()
        
        return True

#interface: the arguments must be:
#recipientID - the unique ID of the agent who receives all messages for them
#all messages will be returned in a dict for processing
def collectMessages(recipientID):
        
        #parse the argument into a set of routing keys
        #todo: understand the rule of this better - may need to change
        routing_keys = [recipientID+'.*']
        
        global response
        
        chan = conn.channel()
        
        #see equiv in sendMessages
        chan.exchange_declare(exchange=EXCN,type='topic')
        
        result = chan.queue_declare(exclusive=True)
        queue_name = result.method.queue
        for k in routing_keys:
            chan.queue_bind(exchange=EXCN,queue=queue_name,routing_key=k)
        
        #collect all messages due for the channel chan
        chan.basic_consume(collectMessagesCallback,queue=queue_name,no_ack=True)
        
        returned_msgs = response if response else None
        
        #clean the buffer for next time
        response = {}
        
        #note that a null return should just be interpreted as 'no messages';
        #although there may of course be errors under the hood that is nobody's
        #business!
        return returned_msgs
            
        
def collectMessagesCallback(ch, method,properties,body):
        global response
        shared.debug(2,["We received messages:",msg])
        #parse the messages into a dict structure
        if '|' not in body:
            shared.debug(0,["Format error in message:",body,";message ignored"])
            return None
        else:
            msg = body.split('|')
            response[msg[0]]=msg[1]
        
        
        