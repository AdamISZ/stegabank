from Crypto.PublicKey import RSA
from Crypto.Util.number import getRandomRange, bytes_to_long, long_to_bytes
from Crypto.Util.number import size, inverse, GCD
from Crypto.Util.py3compat import *
import os
import base64
import struct
import binascii

local_privkey_store_dir = "C:/ssllog-master/keys"

#generates RSA keypair suitable for SSH, stores keypair in local keystore and
#returns public key in format suitable for sending to escrow
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
    #print keypair.n
    
    #public key output format is the 
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
    
    with open('C:/ssllog-master/keys/stuff.ppk','w') as f:
        for i in range(0,len(public_repr),64):
            f.write(public_repr[i:i+64])
            f.write('\r\n')
        f.write('\r\n')
        for i in range(0,len(priv_repr),64):
            f.write(priv_repr[i:i+64])
            f.write('\r\n')
        
#full format description from puttygen source, file sshpubk.c
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
    
    
    
    
    