ssllog
======
For now this is mainly a placeholder. Watch this space.  

Dependencies
------------

*  [Wireshark](www.wireshark.org) - includes command line tools tshark, mergecap etc.
*  [stcppipe](http://aluigi.altervista.org/mytoolz.htm#stcppipe) - use at least 0.4.8a
*  [Squid](http://www.squid-cache.org/Download/) - there may be some subtleties in getting this up and running on Windows, but it does work.
*  [Firefox](http://www.mozilla.org/en-US/firefox/new/) - unfortunately other browsers will not work (Chrome nearly works, but is not supported). v23 at least.
*  [Python 2.7.5](http://www.python.org/getit/)

ALL of these are fully open source, which we consider a critical element of the design.

Platforms: We are developing on Linux(Debian, Ubuntu) and Windows 7 for now.

Notes
-----
This version of the project is based on the following architecture (apologies if it's a bit cryptic for now):
(Buyer)Firefox<-->stcppipe<-->ssh local port forwarding<-->(Escrow)stcppipe,sshd<-->(Seller)remote port forwarding<-->stcppipe<-->squid<-->internet

Far more explanation to come. Obviously.
