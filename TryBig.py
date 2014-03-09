import multisig_lspnr.multisig as m
import helper_startup
import sys
import os
import shared


helper_startup.loadconfig(sys.argv[4])

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
    mscript = m.mk_multisig_script(pubs,M,N)
    msigaddr = m.scriptaddr(mscript.decode('hex'))
    shared.debug(0,["Generated multisig address:",msigaddr])
    #construct inputs
    ins = m.history(msigaddr)
    shared.debug(0,["Ins before filtering:",ins])
    
    ins = [x for x in ins if 'spend' not in x.keys()]
    ins = [x for x in ins if x['output'].startswith(utxoHash)]
    
    shared.debug(0,["Ins after filtering:",ins])
    
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
    outs = [{'value':toPay,'address':addrToBePaid}]
    
    tmptx = m.mktx(ins,outs)
    
    #sign inputs
    for i,inp in enumerate(ins):
        tmptx = m.apply_multisignatures(tmptx,i,mscript,amendedSigs[i])
        
    #push tx
    print tmptx
    print m.deserialize(tmptx)
    rspns = m.ea.send_tx(tmptx)
    print "Electrum server sent back:",rspns
    return tx_hash(tmptx).encode('hex')    

def createSigForRedemptionRaw(M,N,pubs,pub1,utxoHash,addrToBePaid,txFee=None):
    
    print "using utxo hash:"+utxoHash
    #shared.debug(2,["Using these pubkeys:",pub1,pub2,pub3])
    
   
    mscript = m.mk_multisig_script(pubs,M,N)
    msigaddr = m.scriptaddr(mscript.decode('hex'))
    shared.debug(0,["Made multisig address:",msigaddr])
    if not txFee:
        txFee = shared.defaultBtcTxFee
    
    #construct inputs
    ins = m.history(msigaddr)
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
    
    tmptx = m.mktx(ins,outs)  
    shared.debug(0,["Made transaction:",m.deserialize(tmptx)])
    #find the private key in storage corresponding to pub1
    privfile = os.path.join(m.msd,m.pubtoaddr(pub1)+'.private')
    
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
    
    print m.multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)
    return m.multisign(tmptx.decode('hex'),0,mscript.decode('hex'),priv)





'''Test plan:
Set M and N as parameters
Create N new identities in the multisig store
create msig address.
Third parameter is address we already own.
amount to pay in is (0.0002+0.0001 fee)
Make a transaction paying 0.0001 back to same address.
Fourth parameter is number of signatures to choose.
Choose the elements randomly (keeping order)
Sign and broadcast.
'''

#set the location of the multisig storage directory
m.msd='/home/adam/DevRepos/stegabank/ddirescrow2/multisig_store'

M,N,payer = sys.argv[1:4]
M = int(M)
N = int(N)

#this variable is a list of tuples (addr,pub,priv) for identities
keypairs=[]

for i in range(1,N+1):
    keypairs.append(m.create_tmp_address_and_store_keypair())

keypairs.sort(key=lambda x:x[1])

pubs = [x[1] for x in keypairs]


msigaddr,mscript = m.createMultisigRaw2(M, N, pubs)
print "Got this multisig address:",msigaddr

#NB: the payer has to be in the multisig store (need its private key)
payinHash =  m.spendUtxos(payer, payer, msigaddr, None,amt=20000)
if not payinHash:
    print "Failed to fund the multisig; quitting"
    exit(1)

r = shared.get_binary_user_input("Enter y/Y when ready",'y','y','n','n')
if r != 'y':
    exit(1)
    

#choose a set of signers (M out of N randomly)
#cheat TODO just choose the first M
signers=keypairs[0:M]

#construct signatures
sigs=[]
for i,signer in enumerate(signers):
    sigs.append(createSigForRedemptionRaw(M,N,pubs, pubs[i], payinHash, payer))
sigArray = [[sigs,pubs[0:M]]]

broadcastToNetworkRaw(M, N, sigArray, pubs, payinHash, payer)


#kept for reference from original test
'''
d='/home/adam/DevRepos/stegabank/ddirescrow2/multisig_store'
epk='045e1a2a55ccf714e72b9ca51b89979575aad326ba21e15702bbf4e1000279dc72208abd3477921064323b0254c9ead6367ebce17da3ad6037f7a823d65e957b20'
m.initialise(epk, d)

ad1 = '15hnXLUv9gYsLUMm5ADY4YHRt5Guj7C84s'
ad2 = '17twcKYAcHsGrtRSwp3vCzrmAUQV72xErS'
ad3 = '1D6hyupcXurE7fuyRSW4cH68kioGDgNAPd'
ad4 = '1HGX6nECJ3aq3X7mxkTAKNgCChzeEt4wcj'

pu1,pr1 = m.getKeysFromUniqueID(ad1)
pu2,pr2 = m.getKeysFromUniqueID(ad2)
pu3,pr3 = m.getKeysFromUniqueID(ad3)
pu4,pr4 = m.getKeysFromUniqueID(ad4)

pubs = [pu1,pu2,pu3,pu4]
pubs.sort()

privs = [pr1,pr2,pr3,pr4]
keypairs = [[pu1,pr1],[pu2,pr2],[pu3,pr3],[pu4,pr4]]
sorted_keypairs = keypairs.sort(key=lambda x:x[0])

#pubs.sort()
mscript = m.mk_multisig_script(pubs,3,4)
msigaddr = m.scriptaddr(mscript.decode('hex'))

print mscript
print msigaddr

utxoHash='097f4fec4d3104d3fa388652f62f0fc90afb54ab699ed1b30059725e0810144e'
addrToBePaid='1HGX6nECJ3aq3X7mxkTAKNgCChzeEt4wcj'

#m.spendUtxos(ad4, ad4, msigaddr, ad4, amt=20000)
sig1 = createSigForRedemptionRaw(pubs, pubs[0], utxoHash, addrToBePaid, 
                                txFee=None)
sig3 = createSigForRedemptionRaw(pubs, pubs[2], utxoHash, addrToBePaid, 
                                txFee=None)
sig4 = createSigForRedemptionRaw(pubs, pubs[3], utxoHash, addrToBePaid, 
                                txFee=None)

sigArray = [[[sig1,sig3,sig4],[pubs[0],pubs[2],pubs[3]]]]

broadcastToNetworkRaw(3, 4, sigArray, pubs,utxoHash,addrToBePaid)

'''