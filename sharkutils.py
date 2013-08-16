import re
import ConfigParser
import shared
import subprocess
import hashlib

#AG wrapper for running tshark to extract data
#using the syntax -T fields
#output is filtered by a list of frame numbers
#and/or any other filter in Wireshark's -R syntax
def tshark(infile, field='', filter='', frames=[]):
    tshark_exepath =  shared.config.get("Exepaths","tshark_exepath")
    
    args_stub = tshark_exepath + ' -r ' + infile 
    
    if (not frames and not field):
        args = args_stub + " " + filter
    elif (not filter and not frames):
        args = args_stub
    elif (not filter):
        args = args_stub + ' -Y "frame.number ==' + \
        " or frame.number==".join(frames)
    elif (not frames):
        args = args_stub + ' -Y "' + filter
    else:
        args = args_stub + ' -Y "frame.number ==' + \
        " or frame.number==".join(frames) + ' and ' + filter
    if field:
        args = args + '" -T fields -e ' + field
    print args
    try:
        tshark_out =  subprocess.check_output(args)
    except:
        print 'Error starting tshark'
        return -1
    return tshark_out   

def get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list):
    
    ssl_hashes = []
    for s in ssl_app_data_list:
        #get rid of commas and colons
        #(ssl.app_data comma-delimits multiple SSL segments within the same frame)
        s = s.rstrip()
        s = s.replace(',',' ')
        s = s.replace(':',' ')
        if s == ' ':
            print 'empty frame hex. Please investigate'
            cleanup_and_exit()
        ssl_hashes.append(hashlib.md5(bytearray.fromhex(s)).hexdigest()) 
        #print "NUmber of hashes is now: ", len(ssl_hashes)
    print ssl_hashes
    return ssl_hashes


#this function is only going to extract the encrypted SSL data
#which has been reassembled, to avoid possible issues with segmentation
#of data being different between buyer and seller (i.e. try to ignore any
#TCP-and-above issues as they may differ between buyer and seller)
def verify_ssl_hashes_from_capfile(capfile, handshake= False, port= -1):
    
    frames_wanted = []
    frames_hashes = {}
    #Run tshark once to get a list of frames with ssl app data in them
    filterstr = 'ssl.reassembled.data'
    if (port > 0):
        filterstr = filterstr + ' and tcp.port=='+str(port)
    try:
        frames_str = tshark(capfile,field='frame.number', \
                            filter= filterstr)
    except:
        print 'Exception in tshark'
        return -1
    frames_str = frames_str.rstrip()
    ssl_frames = frames_str.split('\r\n')
    print 'need to process this many frames:', len(ssl_frames)
    
    #the frame numbers are keys for the dictionary
    #so we initialise them:
    for frame in ssl_frames:
        frames_hashes[frame] = ''

    #Run tshark a third time to store all the app data
    #in memory. The frames have to be in the right order in the request
    #so we sort the keys from the dict
    #TODO: this should be a call to the generic tshark caller function,
    #but I'm worried about the key point that the filter
    #string must be in the right order.
    frame_filter_string = ''
    for key in sorted(frames_hashes.iterkeys()):
        frame_filter_string = frame_filter_string + key + " or frame.number=="
    frame_filter_string = frame_filter_string[:-18]
    
    tshark_args_seller_stub = shared.config.get("Exepaths","tshark_exepath") \
        + ' -r ' + capfile + ' -Y "frame.number ==' + \
        frame_filter_string
        
    tshark_args = tshark_args_seller_stub + '" -T fields -e ssl.reassembled.data'
    
    try:
        ssl_app_data = subprocess.check_output(tshark_args)
    except:
        print 'Exception in tshark'
        return -1
    
    ssl_app_data_list = ssl_app_data.split('\n')
    return get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    
    
#L2D resolution key functionality:
#match up the ssl segments already found in one capture file with another
#return true if and only if ALL ssl segments are found
#(seems a bit harsh/brittle eh?)
def check_ssl_hashes_are_all_in_capfile(escrow_hashes, scf):
    seller_hashes = verify_ssl_hashes_from_capfile(scf)
    #open question: is it ok to require perfect equality here?
    #current opinion: no, should only request subset
    if set(escrow_hashes).issubset(set(seller_hashes)): 
        return True
    else:
        return False

def filter_cap_file(file, port,ssl=False):
    
    #Build the filter string based on the port
    if ssl:
        filter_string = "tcp.port==" + str(port) + " and ssl"
    







#This function is intended to get hashes of ALL ssl data
#for now it's not known if this can be used;
#TODO : remove this if it isn't needed or can't work    
#pull the hashes of all ssl app data out of a capture file,
#optionally including handshake/non-23 data (not implemented yet)
def get_all_ssl_hashes_from_capfile(capfile, handshake= False, port= -1):
    
    frames_wanted = []
    segments_hashes = {}
    #Run tshark once to get a list of frames with ssl app data in them
    filterstr = 'ssl.reassembled.data'
    if (port > 0):
        filterstr = filterstr + ' and tcp.port=='+str(port)
    try:
        frames_str = tshark(capfile,field='frame.number', \
                            filter= filterstr)
    except:
        print 'Exception in tshark'
        return -1
    frames_str = frames_str.rstrip()
    ssl_frames = frames_str.split('\r\n')
    print 'need to process this many frames:', len(ssl_frames)
    
    #Run tshark a second time to get the ssl.segment frames
    #from the full list of frames
    try:
        segments_str = tshark(capfile,field='ssl.segment', \
                              frames=ssl_frames)
    except:
        print 'Error starting tshark'
        return -1
    
    segments_str = segments_str.rstrip()    
    segments = re.findall('\w+',segments_str) #entries separated by , \r \n

    if len(segments) < 1:
        print 'zero SSL segments, should be at least one. Please investigate'
        cleanup_and_exit()
    #there can be multiple SSL segments in the same frame, so remove duplicates
    segments = set(segments)
    print "Need to process this many segments: ", len(segments)
    
    #the frame numbers are keys for the dictionary
    #so we initialise them:
    for segment in segments:
        segments_hashes[segment] = ''

    #Run tshark a third time to store all the app data
    #in memory. The frames have to be in the right order in the request
    #so we sort the keys from the dict
    #TODO: this should be a call to the generic tshark caller function,
    #but I'm worried about the key point that the filter
    #string must be in the right order.
    frame_filter_string = ''
    for key in sorted(segments_hashes.iterkeys()):
        frame_filter_string = frame_filter_string + key + " or frame.number=="
    frame_filter_string = frame_filter_string[:-18]
    
    tshark_args_seller_stub = shared.config.get("Exepaths","tshark_exepath") \
        + ' -r ' + capfile + ' -Y "frame.number ==' + \
        frame_filter_string
        
    tshark_args = tshark_args_seller_stub + '" -T fields -e ssl.app_data'
    
    try:
        ssl_app_data = subprocess.check_output(tshark_args)
    except:
        print 'Exception in tshark'
        return -1
    
    ssl_app_data_list = ssl_app_data.split('\n')
    return get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    