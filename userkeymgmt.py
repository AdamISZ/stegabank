#Module to generate RSA key pairs, store the private key file
#with an intelligible name in the local directory for keys,
#and to return an OpenSSH formatted public key for transferring.
#Using Python only, although bear in mind that the time taken for key 
#generation can be appreciable.
#Private keys are stored in PuTTY format on Windows, and PEM format on Linux

import os
import base64
import struct
import binascii
from hashlib import sha1
import hmac
import rsa
import platform
import multiprocessing

testing_conversion=False

#taken and simplified from pycrypto package: Crypto.Util.number
def long_to_bytes(n):
    s = ''
    n = long(n)
    while n > 0:
        s = struct.pack('>I', n & 0xffffffffL) + s
        n = n >> 32
    # strip off leading zeros
    for i in range(len(s)):
        if s[i] != '\000'[0]:
            break
    else:
        # only happens when n == 0
        s = '\000'
        i = 0
    s = s[i:]
    return s

#args txID (could be userID?), escrowID and oracleID serve to 
#uniquely specify the login being created.
#Return value is public key as a OpenSSH compatible string.
def generate_keypair(txID,escrowID,oracleID,local_privkey_store_dir='.'):
    if not (txID and escrowID and oracleID):
        return False
    
    #key generation can take several seconds in pure Python
    #see http://stuvel.eu/files/python-rsa-doc/usage.html#time-to-generate-a-key
    #poolsize refers to number of cores running in parallel -
    #seems reasonable to ask the multiprocessing how many cores are available.
    #NB I haven't checked this in multiple environments..
    pubkey,privkey = rsa.newkeys(2048,poolsize=multiprocessing.cpu_count())
    
    #construct the filename prefix we'll be writing to for both public
    #and private
    fnprefix = os.path.join(local_privkey_store_dir,'_'.join([txID,escrowID,\
                                                            oracleID]))
    #public key output format is the same as for OpenSSH.
    eb = long_to_bytes(pubkey.e)
    nb = long_to_bytes(pubkey.n)
    if ord(eb[0]) & 0x80: eb=chr(0x00)+eb
    if ord(nb[0]) & 0x80: nb=chr(0x00)+nb
    keyparts = [ 'ssh-rsa', eb, nb ]
    keystring = ''.join([ struct.pack(">I",len(kp))+kp for kp in keyparts]) 
    public_repr = binascii.b2a_base64(keystring)[:-1]
    
    #having constructed the public key representation in the format used
    #by BOTH putty AND openssh, we can make a public key file with a single
    #line to be uploaded to the oracle:
    with open(fnprefix+'.pub','w') as f:
        #todo: automatically add things like 'command=' here?
        f.write('ssh-rsa '+public_repr+'\n')
        
    
    #PRIVATE KEY FORMATTING
    if (platform.system()=='Windows'):
        #here we must create PuTTY format private key file (.ppk)
        #see documentation comments at the bottom of this file
        
        #for private key construction, we need d,p,q,iqmp,padding
        #this is the ordering specified in the PuTTy source.
        #NOTA BENE: p is the LARGER of the two primes in PuTTy,
        #but in pycrypto it's the smaller!! (found by experimenting with generation)
        #Update 19 Oct 2013: using rsa instead of pycrypto; has some convention
        #as PuTTY, so confusion removed. 'coef' is the inverse of q mod p.
        pkps=[]
        for a in [privkey.d,privkey.p,privkey.q,privkey.coef]:
            ab = long_to_bytes(a)
            if ord(ab[0]) & 0x80: ab=chr(0x00)+ab
            pkps.append(ab)
        
        privkeystring = ''.join([struct.pack(">I",len(pkp))+pkp for pkp in pkps])
        priv_repr = binascii.b2a_base64(privkeystring)[:-1]
        
        #if we were password protecting, we'd need a SHA for padding here, 
        #but we're not
        
        #see the PuTTy source comments below for details of how the HMAC is
        #generated; it's quite complex. Note that this comment:
        
        #string  private-plaintext (the plaintext version of the
        #                            private part, including the final
        #                             padding)
        #is inaccurate. It's actually the binary representation of the private
        #key data (here called "privkeystring"), not the ascii base64 encoded
        #version, and if encryption is used it's the ENCRYPTED version that's added
        #here; but for us, there's no encryption, and there's no padding because 
        # we don't password protect (otherwise it would be padded with however much
        # is needed of the SHA of the ENCRYPTED private key data).
        
        #first construct the message to be HMAC-ed.
        macdata = ''
        for s in ['ssh-rsa','none','imported-openssh-key',keystring,privkeystring]:
            macdata += (struct.pack(">I",len(s)) + s)
        
        #construct a SHA1 hash of the given magic string; this will be used as
        #key for hmac.
        #no passphrase included here because no encryption used
        HMAC_key = 'putty-private-key-file-mac-key'
        HMAC_key2 = sha1(HMAC_key).digest()
        HMAC2 = hmac.new(HMAC_key2,macdata,sha1)
        
        with open(fnprefix+'.ppk','wb') as f:
            f.write('PuTTY-User-Key-File-2: ssh-rsa\r\n')
            f.write('Encryption: none\r\n')
            f.write('Comment: imported-openssh-key\r\n')
            
            #public key section
            f.write('Public-Lines: '+str(int((len(public_repr)+63)/64))+'\r\n')
            for i in range(0,len(public_repr),64):
                f.write(public_repr[i:i+64])
                f.write('\r\n')
            
            #private key section
            f.write('Private-Lines: '+str(int((len(priv_repr)+63)/64))+'\r\n')
            for i in range(0,len(priv_repr),64):
                f.write(priv_repr[i:i+64])
                f.write('\r\n')
                
            #add private mac
            f.write('Private-MAC: ')
            f.write(HMAC2.hexdigest())
            f.write('\r\n')
            
            if testing_conversion:
                #for comparing output of this script with output of puttygen
                with open(fnprefix,'wb') as f:
                    f.write(privkey.save_pkcs1())
                
    else:
        #working on Linux, the priv key is kept in PEM format
        with open(fnprefix,'wb') as f:
            f.write(privkey.save_pkcs1())
    
    return 'ssh-rsa '+public_repr+'\n'
 
#================DOCUMENTATION OF .ppk FORMAT==================================
#full format description from puttygen source, file sshpubk.c
#(minor gotchas/inaccuracies noted above)
'''   
/* ----------------------------------------------------------------------
 * SSH-2 private key load/store functions.
 */

/*
 * PuTTY's own format for SSH-2 keys is as follows:
 *
 * The file is text. Lines are terminated by CRLF, although CR-only
 * and LF-only are tolerated on input.
 *
 * The first line says "PuTTY-User-Key-File-2: " plus the name of the
 * algorithm ("ssh-dss", "ssh-rsa" etc).
 *
 * The next line says "Encryption: " plus an encryption type.
 * Currently the only supported encryption types are "aes256-cbc"
 * and "none".
 *
 * The next line says "Comment: " plus the comment string.
 *
 * Next there is a line saying "Public-Lines: " plus a number N.
 * The following N lines contain a base64 encoding of the public
 * part of the key. This is encoded as the standard SSH-2 public key
 * blob (with no initial length): so for RSA, for example, it will
 * read
 *
 *    string "ssh-rsa"
 *    mpint  exponent
 *    mpint  modulus
 *
 * Next, there is a line saying "Private-Lines: " plus a number N,
 * and then N lines containing the (potentially encrypted) private
 * part of the key. For the key type "ssh-rsa", this will be
 * composed of
 *
 *    mpint  private_exponent
 *    mpint  p                  (the larger of the two primes)
 *    mpint  q                  (the smaller prime)
 *    mpint  iqmp               (the inverse of q modulo p)
 *    data   padding            (to reach a multiple of the cipher block size)
 *
 * And for "ssh-dss", it will be composed of
 *
 *    mpint  x                  (the private key parameter)
 *  [ string hash   20-byte hash of mpints p || q || g   only in old format ]
 * 
 * Finally, there is a line saying "Private-MAC: " plus a hex
 * representation of a HMAC-SHA-1 of:
 *
 *    string  name of algorithm ("ssh-dss", "ssh-rsa")
 *    string  encryption type
 *    string  comment
 *    string  public-blob
 *    string  private-plaintext (the plaintext version of the
 *                               private part, including the final
 *                               padding)
 * 
 * The key to the MAC is itself a SHA-1 hash of:
 * 
 *    data    "putty-private-key-file-mac-key"
 *    data    passphrase
 *
 * (An empty passphrase is used for unencrypted keys.)
 *
 * If the key is encrypted, the encryption key is derived from the
 * passphrase by means of a succession of SHA-1 hashes. Each hash
 * is the hash of:
 *
 *    uint32  sequence-number
 *    data    passphrase
 *
 * where the sequence-number increases from zero. As many of these
 * hashes are used as necessary.
 *
 * For backwards compatibility with snapshots between 0.51 and
 * 0.52, we also support the older key file format, which begins
 * with "PuTTY-User-Key-File-1" (version number differs). In this
 * format the Private-MAC: field only covers the private-plaintext
 * field and nothing else (and without the 4-byte string length on
 * the front too). Moreover, the Private-MAC: field can be replaced
 * with a Private-Hash: field which is a plain SHA-1 hash instead of
 * an HMAC (this was generated for unencrypted keys).
 */
    
'''    
    
    
    
    
    