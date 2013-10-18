from Crypto.PublicKey import RSA
from Crypto.Util.number import getRandomRange, bytes_to_long, long_to_bytes
from Crypto.Util.number import size, inverse, GCD
from Crypto.Util.py3compat import *
from Crypto.Hash import SHA
import os
import base64
import struct
import binascii
from hashlib import sha1
import hmac
import sha

#TODO: still in protean state...

local_privkey_store_dir = "C:/ssllog-master/keys"

#generates RSA keypair suitable for SSH
def generate_key_pair(hostname):
    
    #generation - takes a couple of seconds
    keypair = RSA.generate(2048,os.urandom)
    
    #persist keys to file
    with open(os.path.join(local_privkey_store_dir,hostname+"pub.txt"),"w")\
    as pubfile, open(os.path.join(local_privkey_store_dir,hostname+"priv.txt"),\
    "w") as privfile:
        privfile.write(keypair.exportKey())
        pubkey = keypair.publickey().exportKey('OpenSSH')
        pubfile.write(pubkey)
    privfile.close()
    pubfile.close()
    
    #hand back key for onward sending
    return keypair

      
if __name__ == "__main__":
    
    keypair = generate_key_pair('blahug')
    
    #public key output format is the same as for OpenSSH. (So it can basically
    #be copied direct to a host/server if needed).
    eb = long_to_bytes(keypair.e)
    nb = long_to_bytes(keypair.n)
    if bord(eb[0]) & 0x80: eb=bchr(0x00)+eb
    if bord(nb[0]) & 0x80: nb=bchr(0x00)+nb
    keyparts = [ 'ssh-rsa', eb, nb ]
    keystring = ''.join([ struct.pack(">I",len(kp))+kp for kp in keyparts]) 
    public_repr = binascii.b2a_base64(keystring)[:-1]
    
    #for private lines we need d,p,q,iqmp,padding
    #this is the ordering specified in the PuTTy source.
    #NOTA BENE: p is the LARGER of the two primes in PuTTy,
    #but in pycrypto it's the smaller!! (found by experimenting with generation)
    db = long_to_bytes(keypair.d)
    pb = long_to_bytes(keypair.p)
    qb = long_to_bytes(keypair.q)
    ub = long_to_bytes(keypair.u)
    
    if bord(db[0]) & 0x80: db=bchr(0x00)+db
    if bord(pb[0]) & 0x80: pb=bchr(0x00)+pb
    if bord(qb[0]) & 0x80: qb=bchr(0x00)+qb
    if bord(ub[0]) & 0x80: ub=bchr(0x00)+ub
    #see note above about ordering this list
    privkeyparts = [db,qb,pb,ub]
    privkeystring = ''.join([ struct.pack(">I",len(pkp))+pkp for pkp in privkeyparts])
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
    
    #TODO: not sure if should just remove line endings or what..
    with open('C:/ssllog-master/keys/stuff.ppk','w') as f:
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
    
    
    
    
    
