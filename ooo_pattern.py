# Usage:
#python ooo_pattern.py capturefile.pcapng [cut]
#By default it does a dry-run and doesn't produce a corrected capture file. Run with "cut" argument for produce the corrected capture.

#This script analyzes a wireshark capture searching for a pattern of out-of-order frames
#and reports whether it was able to put the frames in-order
#The corrected capture file with the prefix "new_" will be placed in the same dir as the original capture file
#The script assumes that editcap,mergecap,tshark,capinfos are in your path

#Looking for a pattern in a wireshark capture:
#1. some packet != [TCP Previous segment not captured]
#2. some packet
#3. [TCP Previous segment not captured]
#4. some packet
#5. [TCP out-of-order]
#6. some packet
#7. some packet != [TCP out-of-order] and != [TCP Retransmission]

#if 1st packet is [TCP Prev...] then frames 1-5 need to be rearranged, likewise
#if 7th packet is [TCP ...] then frames 3-7 need to be rearranged
#This script ignores such patterns. It only aims at rearranging frames 3-5

import subprocess
import os
import platform
import sys
import shutil

#FINACK,SYN,SYNACK - the recepient must add 1 to TCP ack upon receipt of special flags
special_flags = ["0x0011","0x0002","0x0012"]

OS = platform.system()
if OS == 'Linux':
    capinfos_exe = 'capinfos'
    tshark_exe = 'tshark'
    editcap_exe = 'editcap'
    mergecap_exe = 'mergecap'
elif OS == 'Windows':
    capinfos_exe = 'C:\\Program Files\\Wireshark\\capinfos.exe'
    tshark_exe = 'C:\\Program Files\\Wireshark\\tshark.exe'
    editcap_exe = 'C:\\Program Files\\Wireshark\\editcap.exe'
    mergecap_exe = 'C:\\Program Files\\Wireshark\\mergecap.exe'

#Try to rearrange but don't actually split and merge the pcap file
#for the purposes of testing, starting_index allows to skip the given number of ooo frames
def rearrange(cut=False, starting_index = 0):
    # -M is needed to prevent displaying rounded frame count like 24k instead of 24350
    last_frame_no = subprocess.check_output([capinfos_exe,'-c', '-M', capture_file]).strip().split()[-1]

    ooo_frames_str = subprocess.check_output([tshark_exe, '-r', capture_file, '-Y', 'tcp.analysis.out_of_order', '-T', 'fields', '-e', 'frame.number'])
    ooo_frames_str = ooo_frames_str.strip()
    if OS == 'Linux':
        ooo_frames = ooo_frames_str.split('\n')
    if OS == 'Windows':
        ooo_frames = ooo_frames_str.split('\r\n')
        
    lost_frames_str = subprocess.check_output([tshark_exe, '-r', capture_file, '-Y', 'tcp.analysis.lost_segment', '-T', 'fields', '-e', 'frame.number'])
    lost_frames_str = lost_frames_str.strip()
    if OS == 'Linux':
        lost_frames = lost_frames_str.split('\n')
    if OS == 'Windows':
        lost_frames = lost_frames_str.split('\r\n')
        
    retr_frames_str = subprocess.check_output([tshark_exe, '-r', capture_file, '-Y', 'tcp.analysis.retransmission', '-T', 'fields', '-e', 'frame.number'])
    retr_frames_str = retr_frames_str.strip()
    if OS == 'Linux':
        retr_frames = retr_frames_str.split('\n')
    if OS == 'Windows':
        retr_frames = retr_frames_str.split('\r\n')

    print 'Total ooo frames '+ str(len(ooo_frames))
    rearrange_unknown_error_count = 0
    rearrange_expected_error_count = 0
    rearrange_success_count = 0
    
    for index1,frame in enumerate(ooo_frames[starting_index:]):
        print 'Processing frame '+ str(starting_index+index1)
        if not (str(int(frame)-2) in lost_frames and str(int(frame)-4) not in lost_frames and str(int(frame)+2) not in ooo_frames and str(int(frame)+2) not in retr_frames):
            continue
        
        #make sure that all the 7 packets belong to the same stream, ie they are not two streams intermingled
        #get the frame's tcp.stream
        stream = subprocess.check_output([tshark_exe, '-r', capture_file, '-Y', 'frame.number=='+frame, '-T', 'fields', '-e', 'tcp.stream'])
        stream = stream.strip()
        #get all frames of the stream
        frames_str = subprocess.check_output([tshark_exe, '-r', capture_file, '-Y', 'tcp.stream=='+stream, '-T', 'fields', '-e', 'frame.number'])
        frames_str = frames_str.strip()
        if OS == 'Linux':
            frames_in_stream = frames_str.split('\n')
        if OS == 'Windows':
            frames_in_stream = frames_str.split('\r\n')

        #get the ooo frame's index
        ooo_index = frames_in_stream.index(frame)
        
        #make sure there are at least 4 packets before and 2 after the ooo frame
        if ooo_index < 4 or ooo_index > len(frames_in_stream)-3:
            print 'Expected error! Not enough frames before or after '+ frame
            rearrange_expected_error_count += 1
            continue
            
        #make sure that the 3 frames to be rearranged and the 2 encompassing frames are consecutive, ie there are no other frames between them. This is needed to simplify cutting/merging later.
        #It is possible in theory that some other frames may end up in between the 5 frames, but since wireshark is logging only a single SSL banking session, that is unlikely enough not be considered
        if not (int(frames_in_stream[ooo_index+1])-1 == int(frames_in_stream[ooo_index]) and int(frames_in_stream[ooo_index])-1 == int(frames_in_stream[ooo_index-1]) and int(frames_in_stream[ooo_index-1])-1 == int(frames_in_stream[ooo_index-2]) and int(frames_in_stream[ooo_index-2])-1 == int(frames_in_stream[ooo_index-3])):
            print 'Expected error! The frames to be rearranged are not sequential around frame '+ frame
            rearrange_expected_error_count += 1
            continue
            
        #make sure that the order of the stream matches the pattern being looked for
        if not (frames_in_stream[ooo_index-2] in lost_frames and frames_in_stream[ooo_index-4] not in lost_frames and frames_in_stream[ooo_index+2] not in ooo_frames and frames_in_stream[ooo_index+2] not in retr_frames):
            print 'Expected error! Our TCP stream appears to be intermingled with another one around frame '+ frame
            rearrange_expected_error_count += 1
            continue
            
        #now do the actual rearranging
        
        #query useful data for the 3 frames that need to be rearranged plus the two encompassing frames
        return_string = subprocess.check_output([tshark_exe, '-r', capture_file, '-Y', 'frame.number=='+frames_in_stream[ooo_index-3]+' or frame.number=='+frames_in_stream[ooo_index-2]+' or frame.number=='+frames_in_stream[ooo_index-1]+' or frame.number=='+frames_in_stream[ooo_index]+' or frame.number=='+frames_in_stream[ooo_index+1], '-T', 'fields', '-e', 'frame.number', '-e', 'tcp.flags', '-e', 'ip.src', '-e', 'tcp.ack', '-e', 'tcp.seq', '-e', 'tcp.len'])
        return_string = return_string.rstrip()
        if OS == 'Linux':
            frames = return_string.split('\n')
        if OS == 'Windows':
            frames = return_string.split('\r\n')

        five_frames = []
        for frame in frames:
            frame_number, tcp_flags, ip_src, tcp_ack, tcp_seq, tcp_len = frame.split('\t')
            #make sure we put 0 where there is an empty string
            five_frames.append({'frame_number':frame_number, 'flag': 1 if tcp_flags in special_flags else 0, 'ip.src':ip_src, 'tcp.ack':int(tcp_ack) if tcp_ack != '' else 0, 'tcp.seq':int(tcp_seq) if tcp_seq != '' else 0, 'tcp.len':int(tcp_len) if tcp_len != '' else 0})
        
        #work from the highest frame to the lowest one
        nextframe = five_frames[-1]
        found_frames = []
        three_frames = five_frames[1:-1]
        #we only rearrange 3 frames out of 5
        rearrange_failure = False
        expected_failure = False
        while len(found_frames) < 3:
            success = False
            for index2,frame in enumerate(three_frames):
                if frame['ip.src'] == nextframe['ip.src']:
                    if frame['tcp.ack'] == nextframe['tcp.ack'] and frame['tcp.seq']+frame['tcp.len'] == nextframe['tcp.seq']:
                        nextframe = three_frames.pop(index2)
                        found_frames.insert(0, nextframe)
                        success = True
                        break
                else:
                    if frame['tcp.ack'] == nextframe['tcp.seq'] and frame['tcp.seq']+frame['tcp.len']+frame['flag'] == nextframe['tcp.ack']:
                        nextframe = three_frames.pop(index2)
                        found_frames.insert(0, nextframe)
                        success = True
                        break
            if success == False:
                retval = subprocess.check_output([tshark_exe, '-r', capture_file, '-Y', 'frame.number=='+five_frames[-1]['frame_number'], '-T', 'fields', '-e', 'tcp.analysis.duplicate_ack'])
                retval = retval.strip()
                if retval == '1':
                    #expected behaviour, don't treat as an error
                    #TODO:in theory we should just skip this dup_ack and start checking against the higher frame
                    #for now, just skip this frame and continue onto the next one
                    expected_failure = True
                    break
                else:
                    print "Couldn't fine the previous frame while rearranging"
                    print 'Failed to rearrange around frame '+ five_frames[1]['frame_number']
                    rearrange_failure = True
                    break
        if rearrange_failure == True:
            rearrange_unknown_error_count += 1
            continue
        elif expected_failure == True:
            rearrange_expected_error_count += 1
            continue
                       
        #make sure that frame 1 of 5 has correct tcp seq/ack
        frame = five_frames[0]
        nextframe = found_frames[0]
        #this is a one-liner for what was done above in a while loop
        if not (frame['ip.src'] == nextframe['ip.src'] and frame['tcp.ack'] == nextframe['tcp.ack'] and frame['tcp.seq']+frame['tcp.len'] == nextframe['tcp.seq']) and not (frame['ip.src'] != nextframe['ip.src'] and frame['tcp.ack'] == nextframe['tcp.seq'] and frame['tcp.seq']+frame['tcp.len']+frame['flag'] == nextframe['tcp.ack']):
            retval = subprocess.check_output(['tshark', '-r', capture_file, '-Y', 'frame.number=='+frame['frame_number'], '-T', 'fields', '-e', 'tcp.analysis.duplicate_ack'])
            retval = retval.strip()
            if retval == '1':
                #expected behaviour, don't treat as an error
                #TODO:in theory we should just skip dup_ack and check against the preceding frame
                rearrange_expected_error_count += 1
                continue
            else:
                print 'Wrong TCP SEQ/ACK between frames 0/5 and 1/5'
                print 'Failed to rearrange around frame '+ five_frames[1]['frame_number']
                rearrange_failure_count += 1
                continue
        
        rearrange_success_count += 1
   
        if cut==True:
            #split and merge
        
            #save all out-of-order frames for future merging (the name of file corresponds to frame number)
            for frame in found_frames:
                subprocess.call([editcap_exe, new_capture_file, os.path.join(workdir,frame['frame_number']), '-r', frame['frame_number']], stdout=open(os.devnull,'w'))
                
            #split into 2 large parts omitting the ooo frames
            subprocess.call([editcap_exe, new_capture_file, os.path.join(workdir,'part1'), '-r', '0-'+five_frames[0]['frame_number']], stdout=open(os.devnull,'w'))
            subprocess.call([editcap_exe, new_capture_file, os.path.join(workdir,'part2'), '-r', five_frames[4]['frame_number']+'-'+last_frame_no], stdout=open(os.devnull,'w'))
            #merge in the correct order
            subprocess.call([mergecap_exe, '-a', '-w', new_capture_file, os.path.join(workdir,'part1'), os.path.join(workdir,found_frames[0]['frame_number']), os.path.join(workdir,found_frames[1]['frame_number']), os.path.join(workdir,found_frames[2]['frame_number']), os.path.join(workdir,'part2')], stdout=open(os.devnull,'w'))
            for frame in found_frames:
                os.remove(frame['frame_number'])
            #for debugging
            new_last_frame_no = subprocess.check_output([capinfos_exe,'-c', '-M', new_capture_file]).strip().split()[-1]
            if int(new_last_frame_no) != int(last_frame_no):
                raise ('Frame number mismatch')
            os.remove(os.path.join(workdir,'part1'))
            os.remove(os.path.join(workdir,'part2'))
        
    
    print 'Out of total ' + str(len(ooo_frames)) + ' out-of-order frames'
    print str(rearrange_expected_error_count + rearrange_unknown_error_count + rearrange_success_count) + ' matched the pattern: '
    print 'Failed to rearrange due to unknown error ' + str(rearrange_unknown_error_count) + '<<-- if this is not 0, please report, this script needs more polish'
    print 'Failed to rearrange due to expected error ' + str(rearrange_expected_error_count)
    print 'Total times succeeded to rearrange ' + str(rearrange_success_count)
    
    
if __name__ == "__main__":
    global new_capture_file
    global capture_file
    global workdir
    if ('help' in sys.argv) or (len(sys.argv) < 2):
        print 'Accepted arguments:'
        print 'capturefile.pcapng : the wireshark capture file to be analyzed'
        print 'cut : (optional) actually modify the pcap file to remove out-of-order frames'
        print 'index=<n> : (optional, for debugging only) start analyzing beginning with the n-th ooo frame'
        exit()
    else:
        capture_file = os.path.abspath(sys.argv[1])
        workdir = os.path.dirname(capture_file)
        os.chdir(workdir)
    if 'cut' in sys.argv:
        #backup the original capture file
        new_capture_file = os.path.join(os.path.dirname(capture_file), 'new_' + os.path.basename(capture_file))
        shutil.copyfile(capture_file, new_capture_file)
    index = 0
    arg = [arg for arg in sys.argv if arg.startswith('index=')]
    if len(arg) != 0:
        index = int(arg[0].split('=')[1])
    rearrange('cut' in sys.argv, index)

