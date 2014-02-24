High level Protocol Specification.
==================================
==================================

(see https://docs.google.com/file/d/0B-fjs8k25mNAcEltbzNtWjJXdEU for some diagrams - although rough and imperfect).

Users
=====

All non-escrow participants are referred to as "users".
Users are identified purely by a single bitcoin address. Any user can discard/reuse bitcoin addresses as they wish.
Any users wishing to maintain total anonymity should use different bitcoin addresses for each transaction.
Any users wishing to maintain some form of reputation can, if they wish, reuse bitcoin addresses. Reputation systems may exist and be used off channel; the protocol will not address this and could not control it in any case.

Escrows
=======
All escrow participants must provide some form of persistent identity, such as a real name identity, a PGP key or similar.
It would be better if this identity had some significant community trust attached to it at the beginning of the process, but it is not essential. To register as an escrow, this identity must be provided along with a deposit of 2BTC (amount can be set by the pool, see below) which will be committed to a multisig address under majority control of the pool of escrows that this escrow joins (there can be more than one pool). This deposit will be redeemed in all cases when the escrow leaves the pool, except those cases where the escrow has violated the protocol, as proved by transactions on the bitcoin blockchain. In cases where suspicion is raised, the escrow may be forced to leave the pool, but would not lose the deposit. 

The identities and corresponding BTC addresses used by the escrows are recorded in a public record somewhere off-protocol, which is signed by one or many of the escrows themselves.

Escrows are rewarded with transaction fees which are set at a percentage of the size of each transaction. This transaction fee percentage will be set pool wide.

Escrows are required to maintain a reasonably high-availability server running the Stegabank escrow software. Excessive outages could cause serious problems and lead to ejection from the pool (again, subject to majority vote).

Escrows serve two distinct roles: contract negotation escrow (CNE) and random escrow (RE). More on these functions below. These two will be run concurrently on the server.

Contract Negotiation
====================
Any user may contact any other user on any CNE. Discovery may occur through any side channels off-protocol. Users may chat with each other to decide the terms of the contract, either on the CNE or off. Once a decision has been made, users will sign contracts, including pricing and timing details, and submit them to the CNE. Once the CNE receives two identical contracts from matching participants, it also signs it and requests deposits. These deposits are a small fixed fee, set pool wide, required for transaction set up and will be transferred to the RE, to be returned to the user later at the end of the contract.

If one user fails to submit the deposit in the required time, the other user's deposit is returned and the CNE takes no further action.

If both deposits are submitted, the protocol requires the CNE to take the following steps:

1. Source a publically verifiable random number (currently using: https://beacon.nist.gov/rest/record/last)
2. Derive from that number a choice of escrow from the public list of escrows (see above "Escrows") using the simple arithmetic algorithm defined in the source code (see AppLayer/EscrowAgent.py)
3. Publish the random number and escrow choice to the users and other escrows
4. Generate a multisig address for the chosen escrows (now called RE) combined with the two users and transfer the deposits from itself to that RE.
5. Instantiate a transaction object and pass it to the RE.
6. 
The steps 1-3 can be verified as fair by all participants, thus ensuring the chosen RE could never have been known in advance by any party.

At this point (strictly, after both deposits have been submitted), the users are not allowed to back out of the transaction without forfeiting their deposit.

If at this stage one user abandons the transaction (i.e. violates a timeout on their actions), their deposit will be transferred to the OTHER USER (not destroyed, not sent to charity, not given to the escrow). 

[It is particularly important that forfeited deposits are not given to the escrow, as this would enable a rogue escrow to Sybil-attack the system by generating lots of fake users and abandoning transactions when a favourable/colluding/hacked escrow was not chosen, cost free. Giving deposits to charity is problematic, requiring perfect trust in charities; destroying deposits may work but why not give the deposit to the party who has been troubled by the deceptive behaviour - the counterparty. This further incentivises honesty.]

If an escrow chose (foolishly) to simply steal deposits, this stealing would be entirely transparent on the blockchain, since the other escrows in the pool would see the contract, signed by the rogue escrow, showing what the deposits were for, and so this would lead to ejection from the pool and total loss of the very large deposit (much beigger than a few deposits). 

[Note here that it is important that the CNE signs the contract before the deposits are transferred. Users can always send these signed deposits to any other escrow in the pool to prove what happened.]

Transactions
============

Once the transaction has been initialised the two users now switch their connection to the new RE. The protocol then proceeds through the following steps:

1. RE waits for confirmed deposits transferred to appropriate multisig address (RE, buyer, seller).
2. RE requests bitcoin to be sold to be transferred to multisig by seller.
3. Seller funds the multisig address.
4. Transaction is now funded. RE waits for buyer.
5. Buyer issues request to start banking session. Request is passed to seller, who indicates readiness (proxy ready).
6. RE tells buyer that seller is ready. Buyer performs internet banking. At end of internet banking, buyer stores: a network trace, ssl keys and records of decrypted html using those keys. Buyer chooses which html pages (and which ssl keys) constitute proof of transfer, but does not send them yet. RE stores an encrypted record of the transfer only.
7. If internet banking fails in some way, steps 5 and 6 may be repeated.

Timing of 5-7 is limited by the terms of the contract (i.e. buyer is required to perform internet banking before time X). Also in the contract, seller promises to be available at a certain set of times (a "proxy service agreement"). If either side violates these conditions, they forfeit their right to the BTC funded in the multisig address (in the rare case where both violate, the escrow applies discretion - either end the transaction if internet banking hasn't taken place, or request agreement between the parties on new timing limits).

8. When internet banking is complete, RE waits for one of three cases: a) seller confirms transfer successful, b) time out without any response from seller or c)seller raises a dispute.

If a) occurs we get the following simple completion:

9. Seller sends confirmation message with transaction signature, RE appends own transaction signature and the BTC are transferred to the buyer (minus the transaction fee, which the escrow can transfer as they wish). The deposits are then transferred back to the buyer and seller.

If b) or c) occurs, we have the following steps:

9. Seller sends dispute message or sends no message before the timeout (in the latter case, the escrow can insist on a response before further action).
10 RE sends request for ssl keys to buyer.
11. Buyer chose SSL keys in step 6,now he sends them to RE.
12. RE extracts all html available using SSL keys transferred - and messages the owner of the escrow server.
13. Manual intervention - the owner of the server reviews the terms of the contract and the html provided and adjudicates whether the fiat transfer occurred or not.
13a. In rare cases where there is ambiguity, it is the escrow's prerogative to ask for a further internet banking session from either the buyer or the seller to give further evidence that a transfer did or did not occur.
14. Once escrow has completed adjudication, they request a signature for a spending transaction from the party who they have adjudicated in favour of, append their own signature, and pay out the BTC (minus transaction fees, as before). The deposits are then transferred to the buyer and seller (regardless of imputed guilt of one party).













