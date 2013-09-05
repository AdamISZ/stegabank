
#====LIBRARY IMPORTS====
import re
import os
import platform
import ConfigParser
import shared
import subprocess
import hashlib
import shutil
#======================

#====GLOBALS===========
#required to address limit on length of filter string for tshark
MAX_FRAME_FILTER = 500
OS = platform.system()
#======================

#wrapper for running tshark to extract data
#using the syntax -T fields
#output is filtered by a list of frame numbers
#and/or any other filter in Wireshark's -R syntax
def tshark(infile, field='', filter='', frames=[]):
    tshark_out = ''
    if (frames and len(frames)>MAX_FRAME_FILTER):
        #we will need to get our output in chunks to avoid
        #issues with going over the hard limit on filter strings
        #in *shark
        start_window = 0
        while (start_window+MAX_FRAME_FILTER < len(frames)):
            print "starting a tshark run with start_window: " + str(start_window)
            tshark_out += tshark_inner(infile,field=field,filter=filter, \
            frames=frames[start_window:start_window+MAX_FRAME_FILTER])
            start_window += MAX_FRAME_FILTER

        tshark_out += tshark_inner(infile,field=field,filter=filter, \
            frames=frames[start_window:])
    else:
        tshark_out += tshark_inner(infile,field=field,filter=filter, \
        frames=frames)
    #print "Final tshark output: \n" + tshark_out
    return tshark_out   


def tshark_inner(infile, field='', filter='', frames=[]):
    tshark_exepath =  shared.config.get("Exepaths","tshark_exepath")
    args = [tshark_exepath,'-r',infile] 
    
    #this clunky structure is unfortunately necessary due to the vagaries
    #of passing double quotes in argument lists
    if (frames and not filter): 
        args.extend(['-Y', 'frame.number==' + ' or frame.number=='.join(frames)])
    elif (frames and filter):
        args.extend(['-Y', 'frame.number==' + ' or frame.number=='.join(frames),' and ',filter])
    else: #means - not frames
        if (filter):
            args.extend(['-Y',filter])
            
    if (field):
        args.extend(['-T','fields','-e',field])
    else:
        args.append('-x')
    
    #command line is now built.
    shared.debug(2,args)
    try:
        tshark_out =  subprocess.check_output(args)
    except:
        print 'Error starting tshark'
        exit()
    
    return tshark_out

# wrapper for running editcap; -r is used
#to include rather than remove frames, filter
#is used to generate a list of frame numbers to include
def editcap(infile, outfile, reverse_flag = 0, filter='', frames=[]):
    editcap_exepath =  shared.config.get("Exepaths","editcap_exepath")
    frame_list=[]
    if reverse_flag:
        args = [editcap_exepath, '-r', infile]
    else:
        args = [editcap_exepath,infile]
    
    if (frames):
        frame_list = frames
    else:
        tshark_out = tshark(infile,field = 'frame.number',filter = filter)
        frame_list = shared.pisp(tshark_out)
    
    shared.debug(3,["Frames are: ", frame_list]) 
    
    #TODO: This won't work if -r flag not used;
    #may need some reconsideration
    if (len(frame_list)>MAX_FRAME_FILTER):
        editcap_inner(args,frame_list,outfile)
    else:
        args.append(outfile)    
        args.extend(frame_list)
        shared.debug(1,"Calling editcap with these arguments: ")
        shared.debug(1,args)
        subprocess.check_output(args)
    

def editcap_inner(args,frames,outfile):
        start_window = 0
        filenames = []
       
        while (start_window+MAX_FRAME_FILTER < len(frames)):
            tmpargs = []
            tmpargs.extend(args)
            shared.debug(1,["starting an editcap run with start_window: " \
                        ,str(start_window)])
            filename = outfile+".tmp."+str(start_window)
            filenames.append(filename)
            tmpargs.append(filename)
            tmpargs.extend(frames[start_window:start_window+MAX_FRAME_FILTER])
            #shared.debug(1,["Here is the call to editcap: ", tmpargs])
            shared.debug(4,subprocess.check_output(tmpargs))
            start_window += MAX_FRAME_FILTER
        
        args.append(outfile+".tmp."+str(start_window))
        args.extend(frames[start_window:])
        shared.debug(4,subprocess.check_output(args))
        #Lastly, need to concatenate and delete all the temporary files
        args = [shared.config.get("Exepaths","mergecap_exepath"),'-w',outfile]
        args.extend(filenames)
        subprocess.check_output(args)
       
        for filename in filenames:
            os.remove(filename) 
            
       

def mergecap(outfile,infiles):
    args = [shared.config.get("Exepaths","mergecap_exepath"),'-w',outfile]
    args.extend(infiles)
    try:
        subprocess.check_output(args)
    except:
        shared.debug(0,["Error in mergecap execution, quitting!"])
        exit()
    
#for merging individual stream files created by stcppipe
#noted 5th September: merged file from stcppipe doesn't seem to
#assemble itself correctly; ignored for now
def merge_stcppipe_streams(filename, bad_files=[]):
    stcp_files=[]
    location = shared.config.get("Directories","stcppipe_logdir")
    for capfile in os.listdir(location):
        if capfile not in bad_files:
            stcp_files.append(os.path.join(location, capfile))
            #shared.debug(1,["Processing stcppipe file:", full_capfile])
        mergecap(os.path.join(location,"merged.pcap"),stcp_files)
            
            
def get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list):
    
    ssl_hashes = []
    for s in ssl_app_data_list:
        #get rid of commas and colons
        #(ssl.app_data comma-delimits multiple SSL segments within the same frame)
        s = s.rstrip()
        s = s.replace(',',' ')
        s = s.replace(':',' ')
        
        #possible bug identified 3rd Sept 2013; 
        #should this be checking for ' ' or '' or both?
        if s == '':
            shared.debug(1,["Error; empty ssl app data string passed for hashing!"])
            exit()
        ssl_hashes.append(hashlib.md5(bytearray.fromhex(s)).hexdigest()) 
        
    return list(set(ssl_hashes))

#single hash only from one string
def get_ssl_hash(s):
    s=s.rstrip().replace(',',' ').replace(':',' ')
    return hashlib.md5(bytearray.fromhex(s)).hexdigest()
    
#this function is only going to extract the hashes of the encrypted SSL data
#which has been reassembled, to avoid possible issues with segmentation
#of data being different between buyer and seller (i.e. try to ignore any
#TCP-and-above issues as they may differ between buyer and seller)
#4 Sep 2013 rewrite to use stcppipe instead of gateway bouncing
#The first argument CAPFILE can take one of two possible forms:
#either the full path of a single pcap file (if captured using dumpcap)
#or a full path to a directory containing a set of acp files collected by stcppipe
def get_all_ssl_hashes_from_capfile(capfile, handshake= False, port= -1,stcp_flag=False):
    if stcp_flag:
        hashes = []
        #here "capfile" is not actually a file, it's the directory
        #containing all the per-stream captures.
        #(stcppipe logs multiple capfiles, one per stream)
        for each_file in os.listdir(capfile):
            full_capfile = os.path.join(capfile, each_file)
            shared.debug(1,["Processing stcppipe file:", full_capfile])
            stream_hashes = get_ssl_hashes_from_capfile(capfile=full_capfile, \
                                                        port=port)
            if (stream_hashes):
                shared.debug(1,["Got hashes:",stream_hashes])
                hashes.extend(stream_hashes)
        return hashes
    else:
        return get_ssl_hashes_from_capfile(capfile=capfile,port=port)
        
        
        
def get_ssl_hashes_from_capfile(capfile,port=-1):

    #Run tshark to get a list of frames with ssl app data in them
    filterstr = 'ssl.record.content_type == 23'
    frames_str=''
    if (port > 0):
        filterstr = filterstr + ' and tcp.port=='+str(port)
    try:
        frames_str = tshark(capfile,field='frame.number', \
                            filter= filterstr)
    except:
        #this could be caused by a corrupt file from stcppipe
        #or by a malformed query string,etc. - but in the former
        #case we should NOT exit, hence this approach
        shared.debug(0,["tshark failed - see stderr for message"])
        shared.debug(0,["return code from tshark: ",frames_str])
        return None
    frames_str = frames_str.rstrip()
    ssl_frames = shared.pisp(frames_str)
    #gracefully handle null result (i.e. blank tshark output):
    ssl_frames = filter(None,ssl_frames)
    if not ssl_frames:
        return None
    
    #Now we definitely have ssl frames in this capture file
    shared.debug(1,['need to process this many frames:', len(ssl_frames)])
    ssl_app_data = tshark(capfile,field='ssl.app_data',frames=ssl_frames)
    #ssl.app_data will return all encrypted segments separated by commas
    #but also, lists of segments from different frames will be separated by
    #newlines
    ssl_app_data_list = ssl_app_data.rstrip().replace(',','\n').split('\n')
    #remove any blank OR duplicate entries in the ssl app data list
    ssl_app_data_list = filter(None,list(set(ssl_app_data_list)))
    
    shared.debug(1,["Length of list of ssl segments for file ",capfile," was: " \
    ,str(len(ssl_app_data_list))])
    
    return get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    

#detailed analysis of frame numbers:
#first capfile is buyer, second is seller
#if buyer is windows, we abandon finding frames there
#as it is split into streams)
def debug_find_mismatch_frames(capfile1, port1, capfile2, port2,buyerOS=''):
    
    if (buyerOS == "Windows"):
        frames_segments1={1:get_all_ssl_hashes_from_capfile(capfile1, port1,userOS='Windows')}
    else:
        frames_segments1 = debug_get_segments(capfile1, port1)
        
    frames_segments2 = debug_get_segments(capfile2, port2)

    #first find hashes which are different
    hashes1 = []
    hashes2 = []
    for hashes in frames_segments1.values():
        hashes1.extend(hashes)
    for hashes in frames_segments2.values():
        hashes2.extend(hashes)
        
    #3rd Sept 2013: correction of bug
    #these hash lists included repeats
    hashes1 = list(set(hashes1))
    hashes2 = list(set(hashes2))
    
    shared.debug(1,["Length of hashes1 is: ", len(hashes1)])
    shared.debug(1,["Length of hashes2 is: ", len(hashes2)])
    shared.debug(2,[" and Here are hashes1: ",hashes1])
    shared.debug(2,[" and Here are hashes2: ",hashes2])
     
    #mismatches are (union-intersection) of two sets:   
    diff_hashes = set(hashes1).symmetric_difference(set(hashes2))
    
    shared.debug(1,["All hashes which didn't match: ",str(diff_hashes)])
    
    ok_frames_1 = []
    ok_frames_2 = []
    for frame1, hash1 in frames_segments1.iteritems():
        for frame2, hash2 in frames_segments2.iteritems():
            shared.debug(4,["frame1, frames 2 are now: " , frame1, " ", frame2])
            for hasha in hash1:
                for hashb in hash2:
                    shared.debug(4,["Trying hashes1,2: ",hasha," ",hashb])
                    if hasha == hashb:
                        shared.debug(3,["Found a match between frame1 and frame2: ", frame1,hasha, " ", frame2,hashb])
                        ok_frames_1.append(frame1)
                        ok_frames_2.append(frame2)
                
    shared.debug(2,["OKFrames1: ",list(set(ok_frames_1))])
    shared.debug(2,["OKFrames2: ",list(set(ok_frames_2))])
    shared.debug(1,["Number of frames OK in first file: ", str(len(set(ok_frames_1)))])
    shared.debug(1,["Number of frames OK in second file: " + str(len(set(ok_frames_2)))])
    
    for frame in [val for val in frames_segments1.iterkeys() if val not in ok_frames_1]:
        print "Hash of segment in frame " + str(frame) + " in " + capfile1 \
            + " was not found in any frame in " + capfile2 
            
    for frame in [val for val in frames_segments2.iterkeys() if val not in ok_frames_2]:
        print "Hash of segment in frame " + str(frame) + " in " + capfile2 \
            + " was not found in any frame in " + capfile1




def debug_get_segments(capfile,port,stream=''):    
    frames_segments = {}
    #Run tshark once to get a list of frames with ssl app data in them
    filterstr = 'ssl.record.content_type==23 and tcp.port=='+str(port)
    if (stream):
        filterstr += (' and tcp.stream==' + stream)
    try:
        frames_str = tshark(capfile,field='frame.number', \
                            filter= filterstr)
    except:
        print 'Exception in tshark'
        return -1
    
    #print frames_str
    frames_str = frames_str.rstrip()
    ssl_frames = shared.pisp(frames_str)
    print 'need to process this many frames:', len(ssl_frames)
    for frame in ssl_frames:
        frames_segments[frame]= [] #array will contain all hashes for that frame
    
    app_data_str = tshark(capfile,field='ssl.app_data',frames=ssl_frames)
    app_data_str = app_data_str.rstrip()
    app_data_output = shared.pisp(app_data_str)
    shared.debug(4,app_data_output)
    #now app_data_output is a list, each element of which is the complete
    #output of ssl.app_data for each frame consecutively
    x=0
    for frame in ssl_frames:
        segments = app_data_output[x].split(',')
        segments = filter(None,segments) # make sure that segments is empty if there's no data!
        for segment in segments:
            frames_segments[frame].append(get_ssl_hash(segment))
        
        shared.debug(3,["Frame: ", frame, frames_segments[frame]])
        x += 1
    
    return frames_segments



#===========================================================================
#defunct below
#===========================================================================
#see get_all_ssl_hashes_from_capfile
#
#Addition 2nd Sept 2013: in case user uses Windows, then the capture file
#will be polluted with retransmissions; to deal with this we collect all
#hashes before and after removal of retransmissions and take the union of
#the two sets. 
#4 SEP 2013 as of now defunct since bouncing no longer necessary (stcppipe)
def gwbounce_get_all_ssl_hashes_from_capfile(capfile, handshake= False, port= -1,userOS='Undefined'):
    if userOS=='Windows':
        hashes1 = get_ssl_hashes_from_capfile(capfile=capfile,port=port,fr=True)
        hashes2 = get_ssl_hashes_from_capfile(capfile=capfile,port=port,fr=False)
       
        return list(set(hashes1).union(set(hashes2)))
    elif userOS=='Linux':
        return get_ssl_hashes_from_capfile(capfile=capfile,port=port,fr=False)
    else:
        shared.debug(1,"Operating system not recognized")
        exit()

#4 Sep 2013 as of now defunct since bouncing no longer necessary (stcppipe)
def gwbounce_get_ssl_hashes_from_capfile(capfile,port=-1,fr=False):
    
    if (fr):
        #we need to use editcap to get rid of all frames marked retransmission
        #in order to build in steps, we'll need frames to KEEP, hence filterstr
        filterstr = 'not tcp.analysis.retransmission'
        frames_str = tshark(capfile,field='frame.number',filter=filterstr)
        frames_str = frames_str.rstrip()
        non_retransmission_frames = shared.pisp(frames_str)
        shared.debug(2,["These are the non retransmission frames: " \
                        ,non_retransmission_frames])
        #get rid of any null values
        non_retransmission_frames = filter(None,non_retransmission_frames)
        #now we have a list of all the frames to keep
        
        if (non_retransmission_frames):
            edited_file = capfile + ".tmp"
            editcap_message = editcap(capfile,edited_file,reverse_flag=1, \
                                      frames=non_retransmission_frames)
            shared.debug(2,[editcap_message])
        else:
            shared.debug(1,["All frames were retransmissions. Cannot get hashes."])
            exit()
    else:
        edited_file=capfile
            
    #Run tshark to get a list of frames with ssl app data in them
    filterstr = 'ssl.record.content_type == 23'
    if (port > 0):
        filterstr = filterstr + ' and tcp.port=='+str(port)
    try:
        frames_str = tshark(edited_file,field='frame.number', \
                            filter= filterstr)
    except:
        print 'Exception in tshark'
        return -1
    frames_str = frames_str.rstrip()
    ssl_frames = shared.pisp(frames_str)

    shared.debug(1,['need to process this many frames:', len(ssl_frames)])
    ssl_app_data = tshark(edited_file,field='ssl.app_data',frames=ssl_frames)
    #ssl.app_data will return all encrypted segments separated by commas
    #but also, lists of segments from different frames will be separated by
    #newlines
    ssl_app_data_list = ssl_app_data.rstrip().replace(',','\n').split('\n')
    #remove any blank OR duplicate entries in the ssl app data list
    ssl_app_data_list = filter(None,list(set(ssl_app_data_list)))
    
    shared.debug(1,["Length of list of ssl segments for file ",edited_file," was: " \
    ,str(len(ssl_app_data_list))])
    
    return get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    
    
def debug_get_streams(capfile):
    streams_output = tshark(capfile,field='tcp.stream')
    streams_output = streams_output.rstrip()
    streams = shared.pisp(streams_output)
    return list(set(streams))
    
def debug_find_mismatch_frames_stream_filter(capfile1,port1,capfile2,port2):
    
    #get list of all streams
    streams = debug_get_streams(capfile1)
    shared.debug(1,["Here are the streams: ",streams])
    for stream in streams:
        shared.debug(1,["Starting work on stream: ", stream])
        #get list of frames to remove
        filterstr = 'tcp.stream==' + stream + ' and tcp.analysis.retransmission'
        frames_str = tshark(capfile1,field='frame.number',filter=filterstr)
        frames_str = frames_str.rstrip()
        retransmission_frames = shared.pisp(frames_str)
        shared.debug(1,retransmission_frames)
        retransmission_frames = filter(None,retransmission_frames)
        #now we have a list of all the frames to remove, pass it to editcap:
        if (retransmission_frames):
            outfile = capfile1 + stream
            editcap_message = editcap(capfile1,outfile,0,frames=retransmission_frames)
            shared.debug(2,[editcap_message])
            shared.debug(1,["About to start a debug run for stream: ",stream])
            debug_find_mismatch_frames(outfile,port1,capfile2,port2)

    