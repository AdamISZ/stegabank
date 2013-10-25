import random, os, json, sys
from electrum import Network
from pybitcointools import *
import txpusher

#elementary implementation:
#stage 1: create three temp addresses
#stage 2: build multisig address based on them
#stage 3: <done externally>: pay in 1 mBTC to multisig
#stage 4: create partially signed tx with 1 sig
#stage 5: create fully signed tx and send back to external address from <3>
#notes: sending via electrum; not robust yet; just repeat for now
#notes 2: initially import all electrum stuff; later  will pare down
#notes 3: split into two scripts: one for address creation, one for redemption
if (sys.argv[1]=='c'):
    privs = [sha256(sys.argv[2]),sha256(sys.argv[3]),sha256(sys.argv[4])]
    print "Here are the private keys: ",privs
    #in future version, 2 of these 3 pubs will be IMPORTED for addr creation
    pubs = [privtopub(priv) for priv in privs]
    print "Here are the public keys: ", pubs
    addresses = [pubtoaddr(pub) for pub in pubs]
    print "Here are the addresses generated: ",addresses

    #we make a multisig address
    mscript = mk_multisig_script(pubs,2,3)
    msigaddr = scriptaddr(mscript.decode('hex'))
    print "Multisig address created: " , msigaddr
    print "Script created: ", mscript

elif (sys.argv[1]=='r'):
    msigaddr = sys.argv[2]
    addr_to_pay = sys.argv[3]
    tx_fee = sys.argv[4] #could conceivably give change but that is not the use case of multisig
    mscript = sys.argv[5]
    priv1 = sys.argv[6]
    priv2=sys.argv[7]
    #TODO: code will ACCEPT a raw, partially signed tx and then sign it with ONE key
    #in first version of test, all keys are here
    #first CREATE a transaction FROM the multisig to the to-pay
    #address, then SIGN that transaction with 2 of the 3 keys. Then push.
    outs = [{'value':100000-int(tx_fee),'address':addr_to_pay}]
    print history(msigaddr)
    temptx = mktx(history(msigaddr),outs)
    #print tx3
    #print deserialize(tx3)
    sig1 = multisign(temptx.decode('hex'),0,mscript.decode('hex'),priv1)
    sig2 = multisign(temptx.decode('hex'),0,mscript.decode('hex'),priv2)
    finaltx = apply_multisignatures(temptx,0,mscript,[sig1,sig2])
    #as of 25 October: blockchain.info is not accepting multisig redeems
    #so we cannot call this superior method; instead we must use electrum
    #pushtx(tx4)

    #send to electrum server
    txpusher.send_tx(finaltx)
    '''
    n = Network()
    n.start(wait=True)
    n.interface.send([('blockchain.transaction.broadcast', [str(finaltx)])], None)
    '''
    print  Transaction(finaltx).hash()
