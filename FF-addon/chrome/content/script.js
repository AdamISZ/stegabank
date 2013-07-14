var consoleService = Components.classes["@mozilla.org/consoleservice;1"]
                                 .getService(Components.interfaces.nsIConsoleService);
consoleService.logStringMessage("hello");
var prefs = Components.classes["@mozilla.org/preferences-service;1"]
                    .getService(Components.interfaces.nsIPrefService);

var tempdir = "";
var is_tempdir_received = false;
var reqTempDir;

function startSSLSession(){
  getTempDir();
  waitForResponse(0);
//After backend responds, continue_after_tempdir_received() is called from within waitForResponse()
}

//Simply send a HEAD request to the python backend to localhost:2222/blabla. Backend treats "/blabla" not as a path but as an API call
//Backend responds with HTTP headers "response":"blabla" and "value":<value from backend>
function getTempDir () {
  is_tempdir_received = false;
  reqTempDir = new XMLHttpRequest();
  reqTempDir.onload = reqTempDirListener;
  reqTempDir.open("HEAD", "http://localhost:2222/tempdir", true);
  consoleService.logStringMessage(reqTempDir);
  consoleService.logStringMessage("sending TEMPDIR request");
  reqTempDir.send()
}

function reqTempDirListener () {
  consoleService.logStringMessage("got TEMPDIR response");
  var query = reqTempDir.getResponseHeader("response");
  var value = reqTempDir.getResponseHeader("value");
  if (query != "tempdir") throw "expected TEMPDIR response";
  if (value.length == 0) throw "TEMPDIR value is zero"
  tempdir = value;
  is_tempdir_received = true;
//TODO close this listener
}

//Give backend 5 seconds to respond before giving up
//JS doesn't have a sleep() function.
function waitForResponse(iteration) {
	consoleService.logStringMessage("waitForResponse hit");
	if (is_tempdir_received == true) continue_after_tempdir_received();
	else {		  
		if (iteration == 5) throw "no TEMPDIR response";
		iteration++;
  		consoleService.logStringMessage("iteration No");
  		consoleService.logStringMessage(iteration);
		//non-standard setTimeout invocation, FF-specific
		setTimeout(waitForResponse,1000,iteration);
	}
}

function continue_after_tempdir_received() {
	download_prefs = prefs.getBranch("browser.download.");
	var pref_dir = "";
	var pref_folderList;
	try {
		pref_dir = download_prefs.getCharPref("dir");
		pref_folderList = download_prefs.getIntPref("folderList");
	}
	//getCharPref("dir") throws a benign exception if it's never been used and dir.length == 0
	catch (e){
	  if (pref_dir.length != 0) throw "Unknown exception on get*Pref"
	}
	download_prefs.setIntPref("folderList", 2); //folderList==2 => use custom folder for downloads
	download_prefs.setCharPref("dir",tempdir);  // custom folder to use	
}

function stopSSLSession(){
  reqStop = new XMLHttpRequest();
  reqStop.onload = reqStopListener;
  reqStop.open("HEAD", "http://localhost:2222/finished", true);
  consoleService.logStringMessage(reqTempDir);
  consoleService.logStringMessage("sending FINISHED request");
  reqStop.send()
}

function reqStopListener () {
  consoleService.logStringMessage("got FINISHED response");
  var query = reqTempDir.getResponseHeader("response");
  var value = reqTempDir.getResponseHeader("value");
  if (query != "finished") throw "expected FINISHED response";
  if (value != "ok") throw "incorrect FINISHED value"
//TODO close this listener
}



//sendStatus() not in use yet
function sendStatus () {
  var oReqPost = new XMLHttpRequest();
  oReqPost.onload = reqListener2;
  oReqPost.open("HEAD", "http://localhost:2222/status", true);
  consoleService.logStringMessage(oReqPost);
  consoleService.logStringMessage("sending STATUS request");
  oReqPost.send()
}

ssl_prefs = prefs.getBranch("security.ssl3.");
ssl_prefs.setBoolPref("dhe_dss_aes_128_sha",false);
ssl_prefs.setBoolPref("dhe_dss_aes_256_sha",false);
ssl_prefs.setBoolPref("dhe_dss_camellia_128_sha",false);
ssl_prefs.setBoolPref("dhe_dss_camellia_256_sha",false);
ssl_prefs.setBoolPref("dhe_dss_des_ede3_sha",false);
ssl_prefs.setBoolPref("dhe_rsa_aes_128_sha",false);
ssl_prefs.setBoolPref("dhe_rsa_aes_256_sha",false);
ssl_prefs.setBoolPref("dhe_rsa_camellia_128_sha",false);
ssl_prefs.setBoolPref("dhe_rsa_camellia_256_sha",false);
ssl_prefs.setBoolPref("dhe_rsa_des_ede3_sha",false);
ssl_prefs.setBoolPref("ecdh_ecdsa_aes_128_sha",false);
ssl_prefs.setBoolPref("ecdh_ecdsa_aes_256_sha",false);
ssl_prefs.setBoolPref("ecdh_ecdsa_des_ede3_sha",false);
ssl_prefs.setBoolPref("ecdh_ecdsa_rc4_128_sha",false);
ssl_prefs.setBoolPref("ecdh_rsa_aes_128_sha",false);
ssl_prefs.setBoolPref("ecdh_rsa_aes_256_sha",false);
ssl_prefs.setBoolPref("ecdh_rsa_des_ede3_sha",false);
ssl_prefs.setBoolPref("ecdh_rsa_rc4_128_sha",false);
ssl_prefs.setBoolPref("ecdhe_ecdsa_aes_128_sha",false);
ssl_prefs.setBoolPref("ecdhe_ecdsa_aes_256_sha",false);
ssl_prefs.setBoolPref("ecdhe_ecdsa_des_ede3_sha",false);
ssl_prefs.setBoolPref("ecdhe_ecdsa_rc4_128_sha",false);
ssl_prefs.setBoolPref("ecdhe_rsa_aes_128_sha",false);
ssl_prefs.setBoolPref("ecdhe_rsa_aes_256_sha",false);
ssl_prefs.setBoolPref("ecdhe_rsa_des_ede3_sha",false);
ssl_prefs.setBoolPref("ecdhe_rsa_rc4_128_sha",false);

security_prefs = prefs.getBranch("security.");
security_prefs.setBoolPref("security.enable_tls_session_tickets",false);

