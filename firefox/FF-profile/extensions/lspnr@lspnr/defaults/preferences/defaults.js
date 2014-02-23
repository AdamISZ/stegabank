pref("extensions.lspnr.default_escrow", "waxwing");
pref("extensions.lspnr.escrow_list", "waxwing");
pref("extensions.lspnr.snapshot_id", "snap-b9cbf8a7");
pref("extensions.lspnr.msg_ipc", "");
pref("extensions.lspnr.msg_chat","");
pref("extensions.lspnr.msg_toolbar", "");
pref("extensions.lspnr.first_run", true);
pref("extensions.lspnr.uid", "2134");
pref("extensions.lspnr.start_new_session", false);

pref("extensions.lspnr.escrow_waxwing.dnsname", "109.169.23.122");
pref("extensions.lspnr.escrow_waxwing.getuserurl", "https://iam.amazonaws.com/?AWSAccessKeyId=AKIAJXRKYPZ26KIDNWOQ&Action=GetUser&Expires=2015-01-01&SignatureMethod=HmacSHA256&SignatureVersion=2&Version=2010-05-08&Signature=SKCkfXVj7JW0mhmDyf%2BDEmcCG5e8kvn%2B%2F%2FBn3o%2Bzqrk%3D");
pref("extensions.lspnr.escrow_waxwing.listmetricsurl", "https://monitoring.eu-west-1.amazonaws.com/?AWSAccessKeyId=AKIAJXRKYPZ26KIDNWOQ&Action=ListMetrics&Expires=2015-01-01&SignatureMethod=HmacSHA256&SignatureVersion=2&Version=2010-08-01&Signature=F4gcfAm99u6k3VBNXKTRVi4moDLxqICb%2BaLJS4lnkxs%3D");
pref("extensions.lspnr.escrow_waxwing.describeinstancesurl", "https://ec2.eu-west-1.amazonaws.com/?AWSAccessKeyId=AKIAJXRKYPZ26KIDNWOQ&Action=DescribeInstances&Expires=2015-01-01&SignatureMethod=HmacSHA256&SignatureVersion=2&Version=2013-08-15&Signature=HNnS3ZScK4Fy7zxUOgi82xTVZh9qIv03ycc6Yh%2BrpLA%3D");
pref("extensions.lspnr.escrow_waxwing.describevolumesurl", "https://ec2.eu-west-1.amazonaws.com/?AWSAccessKeyId=AKIAJXRKYPZ26KIDNWOQ&Action=DescribeVolumes&Expires=2015-01-01&SignatureMethod=HmacSHA256&SignatureVersion=2&Version=2013-08-15&Signature=Faw8hoVgu7eDTFJ1IQh9fwfkNaZXqJMAhm8k3LNQjMU%3D");
pref("extensions.lspnr.escrow_waxwing.getconsoleoutputurl", "https://ec2.eu-west-1.amazonaws.com/?AWSAccessKeyId=AKIAJXRKYPZ26KIDNWOQ&Action=GetConsoleOutput&Expires=2015-01-01&InstanceId=i-d8023c94&SignatureMethod=HmacSHA256&SignatureVersion=2&Version=2013-08-15&Signature=c5EBy%2BZz59hXWPd6C7FC%2BFjvUYODtov4Qb5l0gBgXOc%3D");

pref("security.ssl3.dhe_dss_aes_128_sha", false);
pref("security.ssl3.dhe_dss_aes_256_sha",false);
pref("security.ssl3.dhe_dss_camellia_128_sha",false);
pref("security.ssl3.dhe_dss_camellia_256_sha",false);
pref("security.ssl3.dhe_dss_des_ede3_sha",false);
pref("security.ssl3.dhe_rsa_aes_128_sha",false);
pref("security.ssl3.dhe_rsa_aes_256_sha",false);
pref("security.ssl3.dhe_rsa_camellia_128_sha",false);
pref("security.ssl3.dhe_rsa_camellia_256_sha",false);
pref("security.ssl3.dhe_rsa_des_ede3_sha",false);
pref("security.ssl3.ecdh_ecdsa_aes_128_sha",false);
pref("security.ssl3.ecdh_ecdsa_aes_256_sha",false);
pref("security.ssl3.ecdh_ecdsa_des_ede3_sha",false);
pref("security.ssl3.ecdh_ecdsa_rc4_128_sha",false);
pref("security.ssl3.ecdh_rsa_aes_128_sha",false);
pref("security.ssl3.ecdh_rsa_aes_256_sha",false);
pref("security.ssl3.ecdh_rsa_des_ede3_sha",false);
pref("security.ssl3.ecdh_rsa_rc4_128_sha",false);
pref("security.ssl3.ecdhe_ecdsa_aes_128_sha",false);
pref("security.ssl3.ecdhe_ecdsa_aes_256_sha",false);
pref("security.ssl3.ecdhe_ecdsa_des_ede3_sha",false);
pref("security.ssl3.ecdhe_ecdsa_rc4_128_sha",false);
pref("security.ssl3.ecdhe_rsa_aes_128_sha",false);
pref("security.ssl3.ecdhe_rsa_aes_256_sha",false);
pref("security.ssl3.ecdhe_rsa_des_ede3_sha",false);
pref("security.ssl3.ecdhe_rsa_rc4_128_sha",false);

//Although a non-DH cipher, wireshark wouldn'r decrypt bitcointalk.org which uses a camellia cipher
pref("security.ssl3.rsa_camellia_128_sha",false);
pref("security.ssl3.rsa_camellia_256_sha",false);

pref("security.enable_tls_session_tickets",false);

//tshark can't dissect spdy
pref("network.http.spdy.enabled",false);
pref("network.http.spdy.enabled.v2",false);
pref("network.http.spdy.enabled.v3",false);

pref("network.websocket.enabled",false);
pref("browser.cache.disk.enable", false);
pref("browser.cache.memory.enable", false);
pref("browser.cache.disk_cache_ssl", false);
pref("network.http.use-cache", false);

pref("browser.shell.checkDefaultBrowser", false);
pref("startup.homepage_welcome_url", "");
pref("browser.rights.3.shown", true)
pref("extensions.checkCompatibility", false); 
// The last version of the browser to successfully load extensions. 
//Used to determine whether or not to disable extensions due to possible incompatibilities. 
pref("extensions.lastAppVersion", "100.0.0");
pref("extensions.update.autoUpdate", false); 
pref("extensions.update.enabled", false);
pref("datareporting.policy.dataSubmissionEnabled", false)