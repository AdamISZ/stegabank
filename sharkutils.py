
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
        return -1
    
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
            shared.debug(3,subprocess.check_output(tmpargs))
            start_window += MAX_FRAME_FILTER
        
        args.append(outfile+".tmp."+str(start_window))
        args.extend(frames[start_window:])
        shared.debug(3,subprocess.check_output(args))
        #Lastly, need to concatenate and delete all the temporary files
        args = [shared.config.get("Exepaths","mergecap_exepath"),'-w',outfile]
        args.extend(filenames)
        subprocess.check_output(args)
       
        for filename in filenames:
            os.remove(filename) 
            
       
    
    
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
        
    return list(set(ssl_hashes))

#single hash only from one string
def get_ssl_hash(s):
    s=s.rstrip().replace(',',' ').replace(':',' ')
    return hashlib.md5(bytearray.fromhex(s)).hexdigest()
    
#this function is only going to extract the hashes of the encrypted SSL data
#which has been reassembled, to avoid possible issues with segmentation
#of data being different between buyer and seller (i.e. try to ignore any
#TCP-and-above issues as they may differ between buyer and seller)
#
#Addition 2nd Sept 2013: in case user uses Windows, then the capture file
#will be polluted with retransmissions; to deal with this we collect all
#hashes before and after removal of retransmissions and take the union of
#the two sets. 
def get_all_ssl_hashes_from_capfile(capfile, handshake= False, port= -1,userOS='Windows'):
    if userOS=='Windows':
        hashes1 = get_ssl_hashes_from_capfile(capfile=capfile,port=port,fr=True)
        hashes2 = get_ssl_hashes_from_capfile(capfile=capfile,port=port,fr=False)
        return list(set(hashes1).union(set(hashes2)))
    elif userOS=='Linux':
        return get_ssl_hashes_from_capfile(capfile=capfile,port=port,fr=False)
    else:
        shared.debug(1,"Operating system not recognized")
        exit()
    
def get_ssl_hashes_from_capfile(capfile,port=-1,fr=False):
    
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
    ssl_app_data_list = ssl_app_data.replace(',','\n').split('\n')
    ssl_app_data_list = set(ssl_app_data_list)
    
    #for debug:
    shared.debug(1,["Length of list of ssl segments for file ",edited_file," was: " \
    ,str(len(ssl_app_data_list))])
    
    return get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    

def debug_find_mismatch_frames(capfile1, port1, capfile2, port2):
    
    frames_segments1 = debug_get_segments(capfile1, port1)
    frames_segments2 = debug_get_segments(capfile2, port2)

    #first find hashes which are different
    hashes1 = []
    hashes2 = []
    for hashes in frames_segments1.values():
        hashes1.extend(hashes)
    for hashes in frames_segments2.values():
        hashes2.extend(hashes)
    
    shared.debug(2,["Here are hashes1: ",hashes1])
    shared.debug(2,["Here are hashes2: ",hashes2])
       
    diff_hashes = set(hashes1).symmetric_difference(set(hashes2))
    shared.debug(1,["All hashes which didn't match: ",str(diff_hashes)])
    
    ok_frames_1 = []
    ok_frames_2 = []
    for frame1, hash1 in frames_segments1.iteritems():
        for frame2, hash2 in frames_segments2.iteritems():
            shared.debug(3,["frame1, frames 2 are now: " , frame1, " ", frame2])
            for hasha in hash1:
                for hashb in hash2:
                    shared.debug(3,["Trying hashes1,2: ",hasha," ",hashb])
                    if hasha == hashb:
                        shared.debug(3,["Found a match between frame1 and frame2: ", frame1, " ", frame2])
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
    
    #A special run of tshark: here we need the frames to be listed in the right
    #order
    
    app_data_str = tshark(capfile,field='ssl.app_data',frames=ssl_frames)
    app_data_str = app_data_str.rstrip()
    app_data_output = shared.pisp(app_data_str)
    shared.debug(3,app_data_output)
    #now app_data_output is a list, each element of which is the complete
    #output of ssl.app_data for each frame consecutively
    x=0
    for frame in ssl_frames:
        segments = app_data_output[x].split(',')
        for segment in segments:
            frames_segments[frame].append(get_ssl_hash(segment))
        
        shared.debug(3,["Frame: ", frame, frames_segments[frame]])
        x += 1
    
    return frames_segments

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
        
    
    