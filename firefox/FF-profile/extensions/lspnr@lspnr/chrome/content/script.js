//var reqPageMarked;
//var reqCheckEscrowtrace;
//var isPageMarkedResponded = false;
//var isCheckEscrowtraceResponded = false;
//var is_accno_entered = false;
//var is_sum_entered = false;
var pressed_blue_once = false;
var consoleService;
var prefs;
var port;
var first_window;
var time_clicked;
var keySetCounter;

keySetCounter = 0;
consoleService = Components.classes["@mozilla.org/consoleservice;1"].getService(Components.interfaces.nsIConsoleService);
prefs = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService);
port = Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).get("FF_to_backend_port");
Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.").setBoolPref("start_new_session", false);
first_window = Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).get("FF_first_window");
//let all subsequent windows know that they are not the first window, so they could skip some initialization
Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).set("FF_first_window", "false");
//setting homepage should be done from here rather than defaults.js in order to have the desired effect. FF's quirk.
Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("browser.startup.").setCharPref("homepage", "chrome://lspnr/content/home.html");


if (first_window === "true" ) {
	setProxyPrefs();
}


//copied from https://developer.mozilla.org/en-US/docs/Code_snippets/Progress_Listeners
const STATE_STOP = Ci.nsIWebProgressListener.STATE_STOP;
const STATE_IS_WINDOW = Ci.nsIWebProgressListener.STATE_IS_WINDOW;

var loadListener = {
    QueryInterface: XPCOMUtils.generateQI(["nsIWebProgressListener",
                                           "nsISupportsWeakReference"]),

    onStateChange: function(aWebProgress, aRequest, aFlag, aStatus) {
    	//borrowed from http://stackoverflow.com/questions/6574681/accessing-every-document-that-a-user-currently-views-from-an-extension
        if ((aFlag & STATE_STOP) && (aFlag & STATE_IS_WINDOW) && (aWebProgress.DOMWindow == aWebProgress.DOMWindow.top)) {
            // This fires when the load finishes
			var wm = Components.classes["@mozilla.org/appshell/window-mediator;1"] .getService(Components.interfaces.nsIWindowMediator);
			wm.getMostRecentWindow("navigator:browser").gBrowser.removeProgressListener(this);
			
			//the user may want to log out, we don't want those pages in the escrow's trace
			clearSSLCache();
        }
    },
    onLocationChange: function(aProgress, aRequest, aURI) {},
    onProgressChange: function(aWebProgress, aRequest, curSelf, maxSelf, curTot, maxTot) {},
    onStatusChange: function(aWebProgress, aRequest, aStatus, aMessage) {},
    onSecurityChange: function(aWebProgress, aRequest, aState) {}
}

function pageMarked(){
	//the time is used to look only in those TCP streams which were created after ssl clear cache
	//var d = new Date();
	//var time_int = (d.getTime() / 1000) - 1;
	//time_clicked = time_int.toString().split(".")[0];
	clearSSLCache();

	//start analyzing trace when DOM is loaded (we don't need to wait for full page load, i.e. all CSS, images etc)
	//var wm = Components.classes["@mozilla.org/appshell/window-mediator;1"] .getService(Components.interfaces.nsIWindowMediator);
	//var mainWindow = wm.getMostRecentWindow("navigator:browser");
	//var tabbrowser = mainWindow.gBrowser;
	//tabbrowser.addProgressListener(loadListener);
	//tabbrowser.reload();
	//BrowserReloadSkipCache();

	//var button_blue = document.getElementById("button_blue");
	//var button_grey1 = document.getElementById("button_grey1");
	
	//button_blue.hidden = true;
	//button_grey1.hidden = false;

	//if (!pressed_blue_once) {
	//	pressed_blue_once=true;
	//}
	keySetCounter++;
	log("Recording on key set:"+keySetCounter);
	log_toolbar("Recording on key set:"+keySetCounter);
}

function setProxyPrefs(){
	var port = Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).get("FF_proxy_port");
	var port_int = parseInt(port);
	proxy_prefs = prefs.getBranch("network.proxy.");
	proxy_prefs.setIntPref("type", 1);
	proxy_prefs.setCharPref("http","127.0.0.1");
	proxy_prefs.setIntPref("http_port", port_int);
	proxy_prefs.setCharPref("ssl","127.0.0.1");
	proxy_prefs.setIntPref("ssl_port", port_int);
}


function clearSSLCache() {
	var sdr = Components.classes["@mozilla.org/security/sdr;1"].getService(Components.interfaces.nsISecretDecoderRing);
	sdr.logoutAndTeardown();
}


//Check if user wants to start a new banking session
/*checkNewSession()
function checkNewSession() {
    var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
    var value = branch.getBoolPref("start_new_session");
    if (value !== true){
        setTimeout(checkNewSession, 1000);
        return;
    }
   	var button_blue = document.getElementById("button_blue");
	var button_grey1 = document.getElementById("button_grey1");
	
	button_blue.hidden = true;
	button_grey1.hidden = false;

	pressed_blue_once=false;


    branch.setBoolPref("start_new_session", false);
    setTimeout(checkNewSession, 3000);
}
*/

function log_toolbar(string){
    var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
    branch.setCharPref("msg_toolbar", string);
}

function log(string){
	var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
	branch.setCharPref("msg_ipc", string);
}

//don't allow any new tabs for the space of 5 secs
//This is to prevent FF from opening a new home tab on launch 
function closeTabs(){
	for (var j = 0; j < 50; j++){
		setTimeout(function(){
			try{
				var tabs = gBrowser.tabs;
		    	for (var i=0; i < tabs.length; i++) {
		    		if (tabs[i].pinned === false) {
		    			tabs[i].collapsed = true;
		    		}
		    	}
		    }
			catch(err){
				return;
			}
		},j*100);
	}
}

var lspnr_prefs = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
if (lspnr_prefs.getBoolPref("first_run") === false){
	closeTabs()
}
else {
	//pin the addon tab on first run. It should remain pinned on subsequent runs
	setTimeout(function(){
	    lspnr_prefs.setBoolPref("first_run", false);
	    //load new tab in foreground
		var tab = gBrowser.loadOneTab("chrome://lspnr/content/home.html", null, null, null, false);
		gBrowser.pinTab(tab);
		closeTabs()
	}, 1000);
}	



setTimeout(getToolbarMsg, 3000);
function getToolbarMsg() {
    var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
    var msg = branch.getCharPref("msg_toolbar");
    var info = document.getElementById("label_info");
    var cur_msg = info.value;
    if (msg == cur_msg){
        setTimeout(getToolbarMsg, 10);
        return;
    }
    info.value = msg;
    setTimeout(getToolbarMsg, 10);
}
