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
def create_tmp_address_and_store_keypair(uniqueid=None):
    #no brainwalleting; not safe (but RNG should be considered)
    priv = sha256(str(random.randrange(2**256)))
    pub = privtopub(priv)
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
    
#when user has received pubkey from counterparty, can set up the multisig address
#payment INTO the multisig address, by seller, happens outside the application
#uniqueid1 is YOU, 2 is counterparty, in case this is called from web app
def create_multisig_address(uniqueid1,uniqueid2):
    
    pubs = get_ordered_pubkeys(uniqueid1, uniqueid2)
    if not pubs:
        return ('','')
    mscript = mk_multisig_script(pubs,2,3)
    msigaddr = scriptaddr(mscript.decode('hex'))
    return (msigaddr,mscript)

def createMultisigRaw(pubs):
    pubs.sort()
    mscript = mk_multisig_script(pubs,2,3)
    msigaddr = scriptaddr(mscript.decode('hex'))
    return msigaddr

def get_ordered_pubkeys(uniqueid1,uniqueid2):
    global escrow_pubkey
    check_escrow_present()
    pubs = [escrow_pubkey]
    try:
        for f in [os.path.join(msd,uniqueid1+'.share'),os.path.join(msd,uniqueid2+'.share')]:
            with open(f,'r') as fi:
                fi.readline()
                fi.readline()
                pubs.append(fi.readline().strip())
    except:
        return None
    #necessary for ensuring unique result for address
    pubs.sort()
    return pubs

#can be used by a counterparty to check whether money has been paid in
def check_balance_at_multisig(uniqueid1,uniqueid2,addr=''):
    if not addr:
        msigaddr, mscript = create_multisig_address(uniqueid1,uniqueid2)
    else:
        msigaddr = addr
    return get_balance_lspnr(msigaddr)
    
#called by both counterparties (and can be escrow) to generate a signature to apply
#will fail and return None if the multisig address has not been funded
def create_sig_for_redemption(uniqueid,uniqueid1,uniqueid2,amt,txfee,addr_to_be_paid):
    msigaddr,mscript = create_multisig_address(uniqueid1,uniqueid2)
    amt = int(amt*1e8)
    txfee = int(txfee*1e8)
    outs = [{'value':amt-txfee,'address':addr_to_be_paid}]
    if len(history(msigaddr))<1:
        print "sorry, the multisig address:",msigaddr,"doesn't seem to have any transactions yet. Wait until \'python multisig.py multi_check\' shows CONFIRMED balance."
        return None
    ins = history(msigaddr)[0]
    tmptx = mktx(history(msigaddr),outs)
    privfile = os.path.join(msd,uniqueid+'.private')
    with open(privfile,'r') as f:
        f.readline() #todo - how to do 3 at once?
        f.readline()
        f.readline()
        priv = f.readline().strip()
    sig =  multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)
    #now store the signature in a file
    with open(os.path.join(msd,uniqueid+'.sig'),'wb') as f:
        f.write(sig+'\r\n')
    #for convenience
    return sig

def createSigForRedemptionRaw(pub1,pub2,pub3,utxoHash,addrToBePaid,txFee=None):
    '''pub1 is the id being used to sign, pub2 and 3 the other 2 used
    to create the msig address
    utxoHash is the txHash to be spent'''
    
    print "using utxo hash:"+utxoHash
    shared.debug(2,["Using these pubkeys:",pub1,pub2,pub3])
    
    pubs = [pub1,pub2,pub3]
    pubs.sort()
    mscript = mk_multisig_script(pubs,2,3)
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
        shared.debug(0,["Error, there are no utxos to spend from):",msigaddr])
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
    shared.debug(0,["Extracted private key:",priv])
    
    print multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)
    return multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)

#we assume: exactly two signatures are applied, which can be any
#of buyer,seller and escrow. If the order in which they are provided is
#different to that used to create the multisig address, swap is needed so
#returns True
def need_swap(uniqueid1,uniqueid2,pubs):
    pos = {}
    for id in [uniqueid1,uniqueid2]:
        with open(os.path.join(msd,id+'.share'),'r') as fi:
            fi.readline()
            fi.readline()
            pub = fi.readline().strip()
            pos[id]=pubs.index(pub)
            
    if pos[uniqueid1]>pos[uniqueid2]:
        return True
    return False

def needSwapRaw(sig1,sig2,pubs):
    pubs.sort()
    for id in [uniqueid1,uniqueid2]:
        with open(os.path.join(msd,id+'.share'),'r') as fi:
            fi.readline()
            fi.readline()
            pub = fi.readline().strip()
            pos[id]=pubs.index(pub)
            
    if pos[uniqueid1]>pos[uniqueid2]:
        return True
    return False    

def broadcastToNetworkRaw(sigArray,pubs,utxoHash,addrToBePaid,txfee=None):
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
    mscript = mk_multisig_script(pubs,2,3)
    msigaddr = scriptaddr(mscript.decode('hex'))
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
        shared.debug(5,["Got pubkeys:",ipubs])
        shared.debug(5,["Got sigs:",isigs])
        if not sorted(ipubs)==ipubs:
            amendedSigs.append(reversed(isigs))
        else:
            amendedSigs.append(isigs)
    shared.debug(5,["Got amended sigs:",amendedSigs])
    #construct output
    #deduce payment value
    toPay = 0
    for x in ins:
        toPay += x['value']
    if not txfee:
        toPay -= shared.defaultBtcTxFee
    else:
        toPay -= txfee   
    outs = [{'value':toPay,'address':addrToBePaid}]
    
    tmptx = mktx(ins,outs)
    
    #sign inputs
    for i,inp in enumerate(ins):
        tmptx = apply_multisignatures(tmptx,i,mscript,amendedSigs[i])
        
    #push tx
    print tmptx
    print deserialize(tmptx)
    rspns = ea.send_tx(tmptx)
    print "Electrum server sent back:",rspns
    return tx_hash(tmptx).encode('hex')    

#any party in possession of two signatures can call this to broadcast
#the tx to the network
def broadcast_to_network(sigid1,sigid2,uniqueid1,uniqueid2,amt,txfee,addr_to_be_paid):
    sigs=[]
    for sigid in [sigid1,sigid2]:
        with open(os.path.join(msd,sigid+'.sig'),'r') as fi:
            sigs.append(fi.readline().strip())
    
    #sigfiles have to be applied in the same order as the pubkeys;
    #this is alphanumeric order of pubkeys:
    if need_swap(sigid1,sigid2,get_ordered_pubkeys(uniqueid1,uniqueid2)):
        sigs.reverse()
    
    msigaddr, mscript = create_multisig_address(uniqueid1,uniqueid2)
    amt = int(amt*1e8)
    txfee = int(txfee*1e8)
    outs = [{'value':amt-txfee,'address':addr_to_be_paid}]
    ins = history(msigaddr)[0]
    tmptx = mktx(history(msigaddr),outs)
    finaltx = apply_multisignatures(tmptx,0,mscript,sigs)
    rspns = ea.send_tx(finaltx)
    print "Electrum server sent back:",rspns
    return tx_hash(finaltx).encode('hex')


def check_escrow_present():
    global escrow_pubkey
    if not escrow_pubkey:
        raise Exception("The escrow's pubkey should be set before depositing escrowed bitcoins!")
        
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

if __name__ == "__main__":
    
    if not os.path.isdir(msd): os.mkdir(msd)
    
    if len(sys.argv)<2:
        print "Before you start, make sure to write an escrow's public key as a string in escrow_pubkey at the top of this file"
        print "If you have no escrow pubkey, you can pretend to be the escrow yourself and generate a pubkey with the command create, and then store it in this file"
        print "In real usage, the escrow is a third party who will store his own .private and give you a .share file with this pubkey."
        print "Also, the full path of the multisig storage directory should be set in the variable msd"
        print "===================================================================="
        print "To carry out the 2 of 3 escrow process, provide arguments as follows:"
        print "===================================================================="
        print "python multisig.py create unique_id (creates an address used only for signing, a .private file and a .share file)"
        print "python multisig.py multi_create uniqueid1 uniqueid2 (generates the multisig address to be used; will be the same for both counterparties)"
        print "python multisig.py multi_check uniqueid1 uniqueid2 (checks the balance of the new multisig address)"
        print "python multisig.py sign uniqueid_to_sign_with uniqueid1 uniqueid2 amount_incl_txfee txfee addr_to_pay [.private file] (creates a file with suffix .sig containing this party\'s signature to the transaction"
        print "python multisig.py redeem sigid1 sigid2 uniqueid1 uniqueid2 amount_incl_txfee txfee addr_to_pay"
        exit()
        
    if sys.argv[1]=='create': #second argument is transaction id
        addr, pub, priv = create_tmp_address_and_store_keypair(sys.argv[2])
        print "data stored in: ",os.path.join(msd,sys.argv[2]+'.private')
        print "shareable file stored in:",os.path.join(msd,sys.argv[2]+'.share')
    
    elif sys.argv[1]=='multi_create': #2nd and 3rd arguments are .share files
        print "Multisig address:",create_multisig_address(sys.argv[2],sys.argv[3])
        print "If you're the bitcoin SELLER, please pay the appropriate amount into the address now."
        print "If you're the bitcoin BUYER, check whether the appropriate amount has been paid into this address."

    elif sys.argv[1]=='multi_check': #second and third arguments are ...
        check_balance_at_multisig(sys.argv[2],sys.argv[3])
    
    elif sys.argv[1]=='sign': #arguments: ... amount to pay INCLUDING tx fee 6: tx fee 7:address to pay out to
        create_sig_for_redemption(sys.argv[2],sys.argv[3],sys.argv[4],float(sys.argv[5]),\
                                float(sys.argv[6]),sys.argv[7])
        print "Signature file was created in:",os.path.join(msd,sys.argv[2]+'.sig')
    
    elif sys.argv[1]=='redeem':
        #args: redeem  ...amt txfee address_to_pay
        sys.argv[6]=float(sys.argv[6])
        sys.argv[7]=float(sys.argv[7])
        print broadcast_to_network(*sys.argv[2:9])
    
    #for testing balance checking feature directly from an address
    elif sys.argv[1]=='adtest':
        get_balance_lspnr(sys.argv[2])
    
    else:
        print "incorrect first argument to script"
        
    
    
    
