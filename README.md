<<<<<<< HEAD
stegabank
=========

See the ssllog repo for the history
=======
ssllog
======
For now this is mainly a placeholder. Watch this space.  

Dependencies
------------

*  [Wireshark](www.wireshark.org) - needed for all agents. Includes command line tools tshark, mergecap etc.
*  [stcppipe](http://aluigi.altervista.org/mytoolz.htm#stcppipe) - needed for all agents. Use at least 0.4.8a
*  [ssh tool plink for Windows](http://www.chiark.greenend.org.uk/~sgtatham/putty/download.html) - needed for buyer and seller if on Windows. On *nix just use existing ssh and sshd (if escrow).
*  [Squid](http://www.squid-cache.org/Download/) - needed for seller. There are some subtleties in getting this up and running on Windows, but it does work.
*  [Firefox](http://www.mozilla.org/en-US/firefox/new/) - needed for buyer. Unfortunately other browsers will not work (Chrome nearly works, but is not supported). v23 at least.
*  [Python 2.7.5](http://www.python.org/getit/) - need for all agents. Add package pika if using rabbitMQ.
*  [RabbitMQ](www.rabbitmq.com) - needed for escrow. Messaging architecture. This is not a critical dependency and can be swapped out for any other messaging server software fairly easily.

ALL of these are fully open source, which we consider a critical element of the design.

Platforms: We are developing on Linux(Debian, Ubuntu) and Windows 7 for now.

Notes
-----
This version of the project is based on the following architecture for transactions(apologies if it's a bit cryptic for now):
(Buyer)Firefox<-->stcppipe<-->ssh local port forwarding<-->(Escrow)stcppipe,sshd<-->(Seller)remote port forwarding<-->stcppipe<-->squid<-->internet

Wireshark is used post-transaction for network auditing functions.

Far more explanation to come. Obviously.
>>>>>>> 4d0f018f5a7957162daa0fc536f4c31d4a2f0c74
