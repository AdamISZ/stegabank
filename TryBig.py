import multisig_lspnr.multisig as m
import helper_startup
import sys
import os
import shared


helper_startup.loadconfig(sys.argv[4])

'''Test plan:
Set M and N as parameters
Create N new identities in the multisig store
create msig address.
Third parameter is address we already own.
amount to pay in is (0.0002+0.0001 fee)
Make a transaction paying 0.0001 back to same address.
Fourth parameter is ssllog.ini file
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
    keypairs.append(m.create_tmp_address_and_store_keypair(comp=True))

keypairs.sort(key=lambda x:x[1])

pubs = [x[1] for x in keypairs]


msigaddr,mscript = m.createMultisigRaw(M, N, pubs)
print "Got this multisig address:",msigaddr

#NB: the payer has to be in the multisig store (need its private key)
payinHash =  m.spendUtxos(payer, payer, msigaddr, None,amt=30000)
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
    sigs.append(m.createSigForRedemptionRaw(M,N,pubs, pubs[i], payinHash, payer))
sigArray = [[sigs,pubs[0:M]]]

txh = m.broadcastToNetworkRaw(M, N, sigArray, pubs, payinHash, payer)
if not txh:
    shared.debug(0,["Broadcast failed"])
else:
    shared.debug(0,["Transaction was broadcast:",txh])


