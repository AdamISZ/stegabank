import random, os, json, sys, ast, time
from pybitcointools import *
import electrumaccessor as ea
import shared
#this should be defined in a config - MultsigStorageDirectory
msd = '/some/directory/for/multisig/files'

#This should be set in set_escrow_pubkey before doing anything
escrow_pubkey='045e1a2a55ccf714e72b9ca51b89979575aad326ba21e15702bbf4e1000279dc72208abd3477921064323b0254c9ead6367ebce17da3ad6037f7a823d65e957b20'

def initialise(pubkey,d):
    global escrow_pubkey,msd
    escrow_pubkey = pubkey  
    shared.makedir([d])
    msd = d
    
#uniqueid is the unique transaction identifier allowing the user to correlate
#his keys with the transaction; calling modules are tasked with constructing it
def create_tmp_address_and_store_keypair(uniqueid=None,comp=False):
    #no brainwalleting; not safe (but RNG should be considered)
    priv = sha256(str(random.randrange(2**256)))
    pub = privtopub(priv)
    #for compressed pubkeys; default? TODO
    if comp:
        pub = compress(pub)
    addr = pubtoaddr(pub)
    #write data to file
    if not uniqueid:
        uniqueid=addr
    with open(os.path.join(msd,uniqueid+'.private'),'wb') as f:
        f.write('DO NOT LOSE, ALTER OR SHARE THIS FILE - WITHOUT THIS FILE, YOUR MONEY IS AT RISK. BACK UP! YOU HAVE BEEN WARNED!\r\n')
        f.write(addr+'\r\n')
        f.write(pub+'\r\n')
        f.write(priv+'\r\n')
    
    store_share(pub,uniqueid)
    #access to data at runtime for convenience
    return (addr,pub,priv)

#TODO: Gracefully handle error of non-existence of private key
def getKeysFromUniqueID(uniqueid):
    with open(os.path.join(msd,uniqueid+'.private')) as f:
        f.readline()
        f.readline()
        pub = f.readline().strip()
        priv = f.readline().strip()
    return pub,priv
    
def signText(uniqueid, text):
    pub,priv = getKeysFromUniqueID(uniqueid)
    sig = ecdsa_sign(text,priv)
    return (text, sig)

def verifyText(text,sig,pub):
    return ecdsa_verify(text,sig,pub)
    
def store_share(pubkey,uniqueid):
    global escrow_pubkey
    check_escrow_present()
    with open(os.path.join(msd,uniqueid+'.share'),'wb') as f:
        f.write("THIS FILE IS SAFE TO SHARE WITH OTHERS. SEND IT TO YOUR COUNTERPARTY TO ALLOW THEM TO DO ESCROW WITH YOU.\r\n")
        f.write(escrow_pubkey+'\r\n')
        f.write(pubkey+'\r\n')

def createMultisigRaw(M,N,pubs):
    pubs.sort()
    if len(pubs) != N:
        raise Exception("Cannot create multisig address, need ",N,\
                        "pubkeys, got",len(pubs),"pubkeys.")
    
    mscript = mk_multisig_script(pubs,M,N)
    msigaddr = scriptaddr(mscript.decode('hex'))
    return (msigaddr,mscript)
    
def createSigForRedemptionRaw(M,N,pubs,pub1,utxoHash,addrToBePaid,txFee=None):
    '''sign a payment out of the utxo specified by utxoHash
    to the address addrToBePaid
    with the fee txFee or the default
    from the M of N address on the list of pubkeys pubs
    by the signer specified by pub1'''
    
    shared.debug(0,["using utxo hash:"+utxoHash])
    shared.debug(0,["Using these pubkeys:",pubs])
    
    #full set of pubkeys are always sorted
    pubs.sort()
    mscript = mk_multisig_script(pubs,M,N)
    msigaddr = scriptaddr(mscript.decode('hex'))
    shared.debug(0,["Made multisig address:",msigaddr])
    if not txFee:
        txFee = shared.defaultBtcTxFee
    
    #construct inputs
    ins = history(msigaddr)
    print ins
    ins = [x for x in ins if 'spend' not in x.keys()]
    ins = [x for x in ins if x['output'].startswith(utxoHash)] 
    
    shared.debug(0,["Constructed inputs:",ins])
    
    if len(ins) == 0:
        shared.debug(0,["Error, there are no utxos to spend from:",msigaddr])
        return None
    
    #construct output
    #deduce payment value
    toPay = 0
    for x in ins:
        toPay += x['value']
    if not txFee:
        toPay -= shared.defaultBtcTxFee
    else:
        toPay -= txFee   
    outs = [{'value':toPay,'address':addrToBePaid}]
    
    tmptx = mktx(ins,outs)  
    shared.debug(0,["Made transaction:",deserialize(tmptx)])
    #find the private key in storage corresponding to pub1
    privfile = os.path.join(msd,pubtoaddr(pub1)+'.private')
    
    with open(privfile,'r') as f:
        f.readline() #todo - how to do 3 at once?
        f.readline()
        f.readline()
        priv = f.readline().strip()
    #in current version there will be only one input, but left here for easy extension later
    #sigs = []
    #for i,utxo in enumerate(ins): 
    #    sigs.append(multisign(tmptx.decode('hex'),i,mscript.decode('hex'),priv))
    shared.debug(4,["Extracted private key:",priv])
    
    shared.debug(0,[multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)])
    return multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)    

def broadcastToNetworkRaw(M,N,sigArray,pubs,utxoHash,addrToBePaid,txfee=None):
    '''arguments:
    sigArray is of the form [[[sig1,sig2],[pub1,pub2]],[[sig1,sig2],[pub1,pub2]],..]
    where each outer list element is associated with inputs 0,1,2.. etc
    and [sig1,sig2] correspond to [pub1,pub2]
    - sigs will be reordered if necessary based on pubkey alphanumeric order
    Amount is deduced as all coming from those outputs (no change)
    If set, txfee should be in satoshis
    utxoHashes is a list of all utxos to spend
    addrToBePaid is self explanatory
    '''
   
    #construct msig addr and script
    pubs.sort()
    mscript = mk_multisig_script(pubs,M,N)
    msigaddr = scriptaddr(mscript.decode('hex'))
    shared.debug(0,["Generated multisig address:",msigaddr])
    
    #construct inputs
    ins = history(msigaddr)
    ins = [x for x in ins if 'spend' not in x.keys()]
    ins = [x for x in ins if x['output'].startswith(utxoHash)]
    
    #error check
    if len(ins) != len(sigArray):
        shared.debug(0,[str(len(ins))," len ins"])
        shared.debug(0,[str(len(sigArray))+" len sigarray"])
        raise Exception("The appropriate number of signatures has not been provided")
    
    #order the signatures correctly
    amendedSigs = []
    for sA in sigArray:
        isigs,ipubs = sA
        shared.debug(0,["Got pubkeys:",ipubs])
        shared.debug(0,["Got sigs:",isigs])
        if not sorted(ipubs)==ipubs:
            amendedSigs.append(reversed(isigs))
        else:
            amendedSigs.append(isigs)
    shared.debug(0,["Got amended sigs:",amendedSigs])
    #construct output
    #deduce payment value
    toPay = 0
    for x in ins:
        toPay += x['value']
    if not txfee:
        toPay -= shared.defaultBtcTxFee
    else:
        toPay -= txfee
    
    if toPay <= shared.btcDustLimit:
        shared.debug(0,["Critical error, cannot broadcast transaction; output too small:",toPay])
        return None
    
    outs = [{'value':toPay,'address':addrToBePaid}]
    
    tmptx = mktx(ins,outs)
    
    #sign inputs
    for i,inp in enumerate(ins):
        tmptx = apply_multisignatures(tmptx,i,mscript,amendedSigs[i])
        
    #push tx
    print tmptx
    print deserialize(tmptx)
    rspns = ea.send_tx(tmptx)

#TODO    
#    if checkForBroadcastError(rspns):
#        return None
#    else:
    shared.debug(0,["Electrum server sent back:",rspns])
    return tx_hash(tmptx).encode('hex')    

def checkForBroadcastError(response):
    
    if 'TX rejected' in response[0]['result']:
        return True
    else:
        return False

def check_escrow_present():
    global escrow_pubkey
    if not escrow_pubkey:
        raise Exception("The escrow's pubkey should be set before depositing escrowed bitcoins!")
        

def spendUtxosDirect(addrOwner,addrOwnerID,payee,utxoList):
    """
    spend a set of utxos as returned from a call to getUtxos()
    to recipient payee from owner addrOwner
    """
    u,total= utxoList
    outs = [{'value':total-shared.defaultBtcTxFee,'address':payee}]
    shared.debug(5,["About to make a transaction with these ins:",u,"and these outs:",outs])
    tmptx = mktx(u,outs)
    pub,priv = getKeysFromUniqueID(addrOwnerID)
    for i,x in enumerate(u):
        tmptx = sign(tmptx,i,priv)        
    rspns = ea.send_tx(tmptx)
    shared.debug(2,["Electrum server sent back:",rspns])
    #in this case we return amount spent for convenience
    return (total,tx_hash(tmptx).encode('hex'))    

def spendUtxos(addrOwner,addrOwnerID,payee,payers,amt=None):
    """
    Two cases: either a FIXED amount from ONE payer
    or an UNSPECIFIED amount (means all) from MULTIPLE payers
    Spend to the address payee
    -any utxos received at addrOwner, owned by addrOwner id
    -received from 'payer' address
    -if amt is not defined, then pay everything available
    -if amt is defined, pay the amt in amt and
    send the rest back as change
    Use the transaction fee defined in shared.defaultBtcFee
    Finally, should return False if the amounts in the utxos
    are not sufficient to deliver amt, and returns the tx
    hash if the spend was successful
    """
    if not amt:
        utxoList=[]
        total = 0
        if not payers:
            #pay out everything from this address
            utxoList,total = getUtxos(addrOwner,None)
        else:
            for payer in payers:
                u,a = getUtxos(addrOwner,payer)
                utxoList.extend(u)
                total += a
        outs = [{'value':total-shared.defaultBtcTxFee,'address':payee}]
        tmptx = mktx(utxoList,outs)
        pub,priv = getKeysFromUniqueID(addrOwnerID)
        for i,x in enumerate(utxoList):
            tmptx = sign(tmptx,i,priv)        
        rspns = ea.send_tx(tmptx)
        shared.debug(2,["Electrum server sent back:",rspns])
        #in this case we return amount spent for convenience
        return (total,tx_hash(tmptx).encode('hex'))
    
    else:
        #some basic wallet-ish functionality required;
        #keep paying out the inputs until
        #the amount requirement is fulfilled; leave the rest
        #and pay change as necessary
        total = 0
        change = 0
        finalUtxos = []
        u,a = getUtxos(addrOwner,None,arr=True)
        for i,utxo in enumerate(u):
            total+=a[i]
            finalUtxos.append(utxo)
            if total > amt+shared.defaultBtcTxFee:
                change = total - amt - shared.defaultBtcTxFee
                if change > shared.btcDustLimit:
                    break
        if total < amt+shared.defaultBtcTxFee:
            shared.debug(0,[\
                "Error: attempted a spend but there wasn't enough btc \
                available,total available:",str(total),\
                ",amount required:",str(amt)])
            return False
        
        outs = [{'value':amt,'address':payee}]
        
        if change > 0:
            outs.append({'value':change,'address':addrOwner})
        shared.debug(2,["Here are the inputs:",finalUtxos,"here are the outputs:",outs])
        tmptx = mktx(finalUtxos,outs)
        pub,priv = getKeysFromUniqueID(addrOwnerID)
        for i,x in enumerate(finalUtxos):
            tmptx = sign(tmptx,i,priv)
        print tmptx
        print deserialize(tmptx)
        rspns = ea.send_tx(tmptx)
        shared.debug(2,["Electrum server sent back:",rspns])
        return tx_hash(tmptx).encode('hex')        
    
def getUtxos(payee,payer,arr=False):
    
    filteredUtxos=[]
    if arr:
        total = []
    else:
        total = 0
    h = history(payee)
    #for each transaction in the history, check if the input meets
    #the conditions of the filter
    unspent = [x for x in h if 'spend' not in x.keys()]
    #shared.debug(2,["unspent:",str(len(unspent)),unspent])
    
    x = ea.get_from_electrum([payee],t='a')[0]['result']
    shared.debug(8,["Got this from electrum:",x])
    #build list of heights - to get the raw transaction and deserialize,
    #we need to query the electrum server with a transaction_get, which needs
    #BOTH the height and the transaction hash
    heightsDict={}
    for d in x:
        heightsDict[d['tx_hash']]=d['height']
        
    for i in unspent:
        if payer:
            txh = i['output'].split(':')[0]
            if txh not in heightsDict.keys():
                continue
            rawtx = ea.get_from_electrum([[txh,heightsDict[txh]]],t='t')[0]['result']
            cookedtx = deserialize(rawtx) 
            
            #slightly hack-y but necessary:
            #payers are allowed to use more than one input
            #(so they can sweep up utxos)
            #but a transaction with two DIFFERENT input addresses is not allowed
            if len(cookedtx['ins'])>1:
                for j in cookedtx['ins']:
                    p,s,a = ea.get_address_from_input_script(cookedtx['ins'][0]['script'].decode('hex'))
                    p2,s2,a2 = ea.get_address_from_input_script(j['script'].decode('hex'))
                    if not a == a2:
                        raise Exception("Found an input transaction with more than one payer!")
            
            pubkeys,signatures, addr = \
            ea.get_address_from_input_script(cookedtx['ins'][0]['script'].decode('hex')) 
            if addr != payer:
                continue
            
        filteredUtxos.append(i)
        if arr:
            total.append(i['value'])
        else:
            total += i['value']
        
    return (filteredUtxos,total)

def get_balance_lspnr(addr_to_test):
    '''will accurately report the current confirmed and unconfirmed balance
    in the given address, and return (confirmed, unconfirmed).
    If the number of past transactions at the address is very large (>100), this
    function will take a LONG time - it is not fit for checking Satoshi Dice adds!
    Running time for normal addresses will usually be subsecond, but fairly
    commonly will take 5-20 seconds due to Electrum server timeouts.  '''  
    
    received_btc = 0
    unconf = 0
    #query electrum for a list of txs at this address
    txdetails = ea.get_from_electrum([addr_to_test],t='a')
    x = txdetails[0]
    #print x
    #need to build a list of requests to send on to electrum, asking it for
    #the raw transaction data
    args=[]
    
    for txdict in x['result']:
        args.append([txdict["tx_hash"],txdict["height"]])
    
    #place transactions in order of height for correct calculation of balance
    args.sort(key=lambda x: int(x[1]))
    #unconfirmed will now be at the beginning but need to be at the end
    unconf_args = [item for item in args if item[1]==0]
    conf_args = [item for item in args if item[1]!=0]
    args = conf_args +unconf_args
    
    txs= ea.get_from_electrum(args,t='t')
    
    #Before counting input and output bitcoins, we must first
    #loop through all transactions to find all previous outs used
    #as inputs; otherwise we would have to correctly establish chronological
    #order, which is impossible if more than one tx is in the same block
    #(in practice it would be possible given some arbitrary limit on the 
    #number of transactions in the same block, but that's messy).
    prev_outs={}
    for y in txs:
        rawtx=y['result']
        tx=deserialize(rawtx)
        txh = tx_hash(rawtx).encode('hex')
            
        for output in tx['outs']:
            ispubkey,addr = \
            ea.get_address_from_output_script(output['script'].decode('hex'))
            if not addr == addr_to_test: continue
            bitcoins =  output['value']
            prev_outs[txh]=bitcoins
    
    for i,y in enumerate(txs):
        rawtx = y['result']
        tx = deserialize(rawtx)
        #print tx
        txh = tx_hash(rawtx).encode('hex')
            
        for input in tx['ins']:
            pubkeys,signatures, addr = \
            ea.get_address_from_input_script(input['script'].decode('hex'))
            if not addr == addr_to_test: continue
            
            #we need to find which previous output is being spent - it must exist.
            try:
                bitcoins_being_spent = prev_outs[input['outpoint']['hash']]
            except:
                raise Exception("failed to find the reference to which\
                                 output's being spent!")
            if args[i][1]==0:
                unconf -= bitcoins_being_spent
            received_btc -= bitcoins_being_spent 
            #print "after spending, balance set to:", received_btc
        
        
        for output in tx['outs']:
            ispubkey,addr = \
            ea.get_address_from_output_script(output['script'].decode('hex'))
            #print "Got address: ",addr
            if not addr == addr_to_test: continue
            bitcoins =  output['value']
            if args[i][1]==0:
                unconf += bitcoins
            received_btc +=bitcoins
    
    unconfirmed = received_btc        
    confirmed = (received_btc-unconf)
    #print "Final unconfirmed balance: ", unconfirmed
    #print "Final confirmed balance: ", confirmed
    return confirmed,unconfirmed