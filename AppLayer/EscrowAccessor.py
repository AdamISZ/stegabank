import shared
import Messaging
from AppLayer.Agent import Agent
from AppLayer.Transaction import Transaction
from AppLayer.UserAgent import UserAgent
#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class EscrowAccessor(Agent):
    #note that certain information will have to be retrieved to access escrow
    def __init__(self,host='',username='',password='',port='',escrowID):
        print "instantiating a remote escrow accessor"
        self.agent = agent #this is the user agent who is using this accessor
        self.transactions = [] 
        self.host = host
        #TODO:need to consider how to securely transfers logins to 
        #people who need it
        self.userName=username
        self.password=password
        self.accessPort=port
        self.uniqID = escrowID
        
        self.messagingConnection = \
        pika.BlockingConnection(pika.ConnectionParameters(host=self.host,\
                                                        port=self.accessPort))
        #at start up of connection with escrow, our message buffer 
        #will be empty
        self.messageBuffer=''
        
    def sendMessages(self,messages=[],recipient=None,transaction=None):
        recipientID = self.uniqID if recipient = None else recipient.uniqID
        shared.debug(1,["Want to send message(s): \n",messages," to agent: ",\
                        recipientID,'\n'])
        #use pika to send
        channel = self.messagingConnection.channel()
        #customarily declare the queue whether it already exists or not
        #the communication channel is uniquely defined by a combination of the
        #sending and receiving party
        queue_name = self.agent.uniqID+','+recipientID+','
        if (transaction): queue_name += transaction.uniqID
        channel.queue_declare(queue=queue_name)
        for message in messages:
            channel.basic_publish(exchange='',routing_key=queue_name,body=message)
        #is this needed or possible?
        #self.MessagingConnection.close()
    
    #other application logic will decide when to collect messages on
    #different topics; here is the low level call to get all unread
    #messages on either: <me, escrow>,<me,counterparty> or those + tx   
    def collectMessages(self,queue_name):
        channel = self.messagingConnection.channel()
        channel.basic_consume(self.collectMessagesCallback,queue=queue_name,\
                              no_ack=True)
        
    def collectMessagesCallback(self, ch, method,properties,body):
        #store the messages we got from a call to collectMessages
        #in a temporary buffer; note that we lose all previous messages
        #todo: can set up buffers for each possible queue if it helps
        self.messageBuffer = body
    
    def getLogin(self):
        return [self.host,self.userName,self.password,self.accessPort]