#!/usr/bin/env python3
#Version 3
# vim: ts=4 autoindent expandtab number
"""
===============================================================================

Python script for conversion of flac files to flac/mp3/ogg/opus.

Copyright 2006-2015 Ziva-Vatra, Belgrade
(www.ziva-vatra.com, mail: zv@ziva-vatra.com)

Project website: https://github.com/ZivaVatra/flac2all

Licensed under the GNU GPL. Do not remove any information from this header
(or the header itself). If you have modified this code, feel free to add your
details below this (and by all means, mail me, I like to see what other people
have done)

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License (version 2)
as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

===============================================================================
"""

"""
===============================================================================
This is a modification of the flac2all python script.
Author of modification: Moritz Schulte
===============================================================================
"""

import sys
import os
import string,re
import pdb
import threading,time,multiprocessing
import subprocess as sp
import base64
import struct
import signal

#CODE

def preexec_function():
    os.setpgrp()

#Class that deals with vorbis
class vorbis:
    def oggconvert(self,oggencopts,infile,outfile):
        #oggenc automatically parses the flac file + metadata, quite wonderful
        #really, we don't need to do anything here
        #The binary itself deals with the tag conversion etc
        #Which makes our life rather easy


        #Uncomment the line below if you want the file currently being
        #converted to be displayed
        print(shell().parseEscapechars(infile))

        #when option is enabled show stderr of processes in stdout
        errpipe = sp.DEVNULL
        if opts['stderr']:
            errpipe = sp.STDOUT

        conversion_process = sp.Popen("%sffmpeg -loglevel panic -i %s -y -vn %s %s.ogg" % (
                oggencpath,
                shell().parseEscapechars(infile),
                oggencopts,
                shell().parseEscapechars(outfile)),
            stdout=sp.DEVNULL, stdin=sp.DEVNULL, stderr=errpipe, shell=True, preexec_fn=preexec_function)

        conversion_process.communicate()

        #coverart------------------------------------------------------

        #exctract coverart as jpeg and read it in
        jpeg_process = sp.Popen("%sffmpeg -loglevel panic -i %s -an -c:v copy -f mjpeg - " % (
                oggencpath,
                shell().parseEscapechars(infile)),
            stdout=sp.PIPE, stdin=sp.DEVNULL, stderr=errpipe, shell=True, preexec_fn=preexec_function)

        (stdout_data, stderr_data) = jpeg_process.communicate()
        data = bytearray(stdout_data)

        if len(data) > 0:
            #write the header that is required for the binary data
            int_picturetype = 3 #3 for cover(front)
            str_mime = b"image/jpeg" #mime string - assume jpeg
            str_description = b"" #description string - assume empty
            int_width = 0
            int_height = 0
            int_depth = 0
            int_index = 0

            data_header = struct.pack(">I I %ds I %ds I I I I I" %(len(str_mime), len(str_description)),
                    int_picturetype,
                    len(str_mime),
                    str_mime,
                    len(str_description),
                    str_description,
                    int_width,
                    int_height,
                    int_depth,
                    int_index,
                    len(data)
                    )
            #merge header with binary data and convert everything to base64
            data_complete = data_header + data
            data_complete_b64 = base64.b64encode(data_complete)

            #read all the comments from the fresh ogg file
            meta_process = sp.Popen("vorbiscomment -R -l %s.ogg" % (shell().parseEscapechars(outfile)),
                stdout=sp.PIPE, stdin=sp.DEVNULL, stderr=errpipe, shell=True, preexec_fn=preexec_function)

            (stdout_data, stderr_data) = meta_process.communicate()
            
            #add our coverart tag to the comments
            metadata = stdout_data + "METADATA_BLOCK_PICTURE=".encode('utf-8') + data_complete_b64

            #rewrite the comments to the ogg file
            meta_process = sp.Popen("vorbiscomment -R -w %s.ogg" % (shell().parseEscapechars(outfile)),
                stdout=sp.DEVNULL, stdin=sp.PIPE, stderr=errpipe, shell=True, preexec_fn=preexec_function)

            meta_process.communicate(metadata)


#Class that deals with FLAC

class flac:
    def flacconvert(self,flacopts, infile, outfile):
        os.system("%sflac -s -d -c \"%s\" | %sflac -f -s %s -o \"%s.flac\" -" %
            (flacpath, infile, flacpath, flacopts, outfile)
        )
        os.system("%smetaflac --no-utf8-convert --export-tags-to=- \"%s\" | %smetaflac --import-tags-from=- \"%s.flac\"" %
            (flacpath, infile,flacpath, outfile)
        )
        


    def getflacmeta(self,flacfile):
        #The FLAC file format states that song info will be stored in block 2, and the reference
    #encoder does so, but other encoders do not! This caused issue 14 and issue 16. 
    #As such, we now search by block time VORBIS_COMMENT. There should only be one such. 
        flacdata = os.popen("%smetaflac --list --block-type VORBIS_COMMENT  %s" %
            (
            metaflacpath,
            flacfile
            )
        )

        datalist = [] #init a list for storing all the data in this block

        #this dictionary (note different brackets) will store only the comments
        #for the music file
        commentlist = {}

        #parse the metaflac output looking for a Vorbis comment metablock, identified as:
        #    METADATA block #?
        #      type: 4 (VORBIS_COMMENT)
        #then start scanning for Vorbis comments. This localised searching ensures that
        #"comment" tags in non Vorbis metablocks don't corrupt the music tags
        foundnewmetadatablock = 0
        lookingforvorbiscomments = 0
        for data in flacdata.readlines():
            #get rid of any whitespace from the left to the right
            data = str.strip(data)

            #only start looking for Vorbis comments once we have latched onto a
            #new metadata block of type 4
            if(foundnewmetadatablock == 1 and data == "type: 4 (VORBIS_COMMENT)"):
                lookingforvorbiscomments = 1
            if(foundnewmetadatablock == 1):
                foundnewmetadatablock = 0
            if(data[:16] == "METADATA block #"):
                foundnewmetadatablock = 1
                lookingforvorbiscomments = 0

            if (lookingforvorbiscomments == 1):
                #check if the tag is a comment field (shown by the first 8 chars
                #spelling out "comment[")
                if(data[:8] == "comment["):
                    datalist.append(str.split(data,":",1))
     

        for data in datalist:
            #split according to [NAME]=[VALUE] structure
            comment = str.split(data[1],"=")
            comment[0] = str.strip(comment[0])
            comment[1] = str.strip(comment[1])
            #convert to upper case
            #we want the key values to always be the same case, we decided on
            #uppercase (whether the string is upper or lowercase, is dependent
            # on the tagger used)
            comment[0] = str.upper(comment[0])

            #assign key:value pair, comment[0] will be the key, and comment[1]
            #the value
            commentlist[comment[0]] = comment[1]
        return commentlist

    def flactest(self,file,outfile):
        test = os.popen(flacpath + "flac -s -t \"" + file + "\"",'r')
        #filepath = generateoutdir(file,outfile) + "results.log"

    #if (os.path.exists(filepath)):
    #   os.remove(filepath)

                #os.mknod(filepath,0775)
                #out = os.popen(filepath,'w')

                #results = ""

                #for line in test.readlines():
#                       print "++++++++++++" + line
#                       results = line

#               out.write(results)

#       print "==============" + results
#       test.flush()
        test.close()

#       out.flush()
#       out.close()





#Class dealing with shell/output related things:

class shell:
    def generateoutdir(self,indir, outdir,dirpath):
                #if we find the dirpath in the current output path, we replace
                #it with the new output path. (so that we don't get
                #/mnt/convertedfromflac/mnt/flac/[file].mp3, in this case
                #"/mnt/" exist in both)
        if (str.find(os.path.split(indir)[0], dirpath) != -1):
            return str.replace(os.path.split(indir)[0], dirpath, outdir)
        else:
            #if we do not find an instance of dir path in output
            #path (this shows that they are the same), just
            #return the output
            return outdir

    def parseEscapechars(self,file,quoteonly=False):
    #TODO: look at docs.python.org/2/library/codecs.html for info on how to do this better 
        if(quoteonly == False):
            #characters which must be escaped in the shell, note
            #"[" and "]" seems to be automatically escaped
            #(strange, look into this)
            escChars = ["\"","*",";"," ","'","(",")","&","`","$"]

            for char in escChars:
                #add an escape character to the character
                file = str.replace(file, char, '\\' + char)
        else:
            file = str.replace(file, "\"", "\\\"")

        return file


    def getfiles(self,path):
        infiles = os.listdir(path) #the files going in for reading
        outfiles = [] #the files going out in a list

        for file in infiles:
            if(os.path.isdir(os.path.join(path,file))):
                #recursive call
                outfiles = outfiles + self.getfiles(os.path.join(path,file))
            else:
                outfiles.append(os.path.join(path,file))

        return outfiles



#mp3 class:

class mp3:
    def __init__(self):
        os.environ['AV_LOG_FORCE_NOCOLOR'] = '1'
        #pass #keep the constructor empty for now

    def mp3convert(self,lameopts,infile,outfile):

        #give us an output file, full path, which is the same as the infile 
        #(minus the working directory path) and with the extension stripped
        #outfile = os.path.join(outdir+"/",os.path.split(infile)[-1]).strip(".flac")

        #Uncomment the line below if you want the file currently being
        #converted to be displayed
        print(shell().parseEscapechars(infile))

        #when option is enabled show stderr of processes in stdout
        errpipe = sp.DEVNULL
        if opts['stderr']:
            errpipe = sp.STDOUT

        conversion_process = sp.Popen("%sffmpeg -loglevel panic -i %s -y -c:v copy %s %s.mp3" % (
            lamepath,
            shell().parseEscapechars(infile),
            lameopts,
            shell().parseEscapechars(outfile)),
            stdout=sp.DEVNULL, stdin=sp.DEVNULL, stderr=errpipe, shell=True, preexec_fn=preexec_function)

        conversion_process.communicate()


#END OF CLASSES, Main body of code follows:


#Functions defined here
def header():
    return """
Flac2all python script, v3 . Copyright 2006-2015 Ziva-Vatra.com.
Licensed under the GPLv3 .
Project website: https://github.com/ZivaVatra/flac2all

    """
def infohelp():
    return """
flac2all [convert type] [input dir] <options>
where \'convert type\' is one of:
\t [mp3]: convert file to mp3
\t [vorbis]: convert file to ogg vorbis
\t [flac]: convert file to flac"""

def init():
    pass #do nothing, prolly remove this function
    #The above currently not used for anything useful
    #binpath = os.path.defpath #get the $PATH variable from the os

def source_is_newer(source, destination):
    #returns True if source's timestamp is newer
    try:
        srctime = os.path.getmtime(source)
        dsttime = os.path.getmtime(destination)
    except OSError:
        #in case of eror set dsttime to a higher value so that nothing gets overwritten
        srctime = 0
        dsttime = 1
    #print("src: " + str(srctime) + " - dst: " + str(dsttime) + " srcpath: " + source + " dstpath: " + destination  )
    return srctime > dsttime
    
def encode_thread(current_file,filecounter,opts):

    #remove the dirpath placed in parameters, so that we work from that
    #directory
    current_file_local = current_file.replace(opts['dirpath'],'')

    if (opts['nodirs'] == True):
        outdirFinal = opts['outdir']
    else:
        if (opts['include_root'] == True):
            outdirFinal = opts['outdir'] + os.path.split(opts['dirpath'])[1] + os.path.split(current_file_local)[0]
        else:
            outdirFinal = opts['outdir'] + os.path.split(current_file_local)[0]

    #if the path does not exist, then make it
    if (os.path.exists(outdirFinal) == False):
        #the try/catch here is to deal with race condition, sometimes one
        #thread creates the path before the other, causing errors
        try:
           #recursive, will make the entire path if required
           os.makedirs(outdirFinal)
        except(OSError):
           print("Directory already exists! Reusing...")


    #this chunk of code provides us with the full path sans extension
    outfile = os.path.join(outdirFinal,os.path.split(current_file_local)[1])
    #return the name on its own, without the extension
    outfile = str.split(outfile, ".flac")[0]
    #This part deals with copying non-music data over (so everything that isn't
    #a flac file)
    if (str.lower(current_file [-4:]) != "flac"):
        if (opts['copy'] == True):
            print("Copying file #%d (%s) to destination" % (filecounter,current_file.split('/')[-1]))
            if ( os.path.exists(outfile) == True) and (opts['overwrite'] == False):
                if os.stat(current_file).st_mtime - os.stat(outfile).st_mtime > 1:
                    os.system("cp \"%s\" \"%s\"" % (current_file,outdirFinal) )
                else:
                    print("File %s is same size as destination. Not copying" % current_file)
            else:
                os.system("cp \"%s\" \"%s\"" % (current_file,outdirFinal) )
            filecounter += 1

    if(opts['overwrite'] == False): #if we said not to overwrite files
        #if a file with the same filename/path does not already exist

        #the below is because "vorbis" is "ogg" extension, so we need the right extension
        #if we are to correctly check for existing files.
        if opts['mode'] == "vorbis":
            ext = "ogg"
        else:
            ext = opts['mode']

        overwrite_because_old = False
        if os.path.exists(outfile + "." + ext) and opts['overwrite_old']:
            overwrite_because_old = source_is_newer(current_file, outfile + "." + ext) 

        if overwrite_because_old:
            print("file will be overwritten because the source has changed (more recent modification date)")

        if (not (os.path.exists(outfile + "." + ext))) or overwrite_because_old:
            #[case insensitive] check if the last 4 characters say flac (as in
            #flac extension, if it doesn't, then we assume it is not a flac
            #file and skip it
            if (str.lower(current_file [-4:]) == "flac"):
                if (opts['mode'] != "test"):
                    print( "converting file #%d to %s" % (filecounter,opts['mode']))
                else:
                    print("testing file #" + str(filecounter))

                if(opts['mode'] == "mp3"):
                    mp3Class.mp3convert(opts['lameopts'],current_file,outfile)
                elif(opts['mode'] == "flac"):
                    flacClass.flacconvert(opts['flacopts'],current_file,outfile)
                elif(opts['mode'] == "vorbis"):
                    vorbisClass.oggconvert(opts['oggencopts'],current_file,outfile)
                elif(opts['mode'] == "test"):
                    flacClass.flactest(current_file, outfile)
                else:
                    print("Error, Mode %s not recognised. Thread dying" % opts['mode'])
                    sys.exit(-2)
        else:
            print("file #%d exists, skipping" % filecounter )
    else:
        #[case insensitive] check if the last 4 characters say flac (as in flac
        #extension, if it doesn't, then we assume it is not a flac file and
        #skip it
        if (str.lower(current_file [-4:]) == "flac"):
            if (opts['mode'] != "test"):
                print("Converting file %d to %s" % (filecounter,opts['mode']))
            else:
                print("Testing file %d" % filecounter)

            if(opts['mode'] == "mp3"):
                mp3Class.mp3convert(opts['lameopts'],current_file,outfile)
            elif(opts['mode'] == "flac"):
                flacClass.flacconvert(opts['flacopts'],current_file,outfile)
            elif(opts['mode'] == "vorbis"):
                vorbisClass.oggconvert(opts['oggencopts'],current_file,outfile)
            elif(opts['mode'] == "test"):
                flacClass.flactest(current_file, outfile)
            else:
                print("Error, Mode %s not recognised. Thread dying" % opts['mode'])
                sys.exit(-2)

    return filecounter + 1 #increment the file we are doing

def generateLameMeta(mp3file):
    metastring  = flac().getflacmeta("\"" + mp3file + "\"")
    return mp3Class.generateLameMeta(metastring)
    #Metadata population complete

#END Functions


#Code starts here

#Variables are here

#***NOTE***
#if the *path variables below are left blank, then the script will try to find
#the programs automatically. only change these if the script does not work
#(or add the programs to your system $PATH variable)

flacpath="" #path to flac binary, blank by default
metaflacpath="" #path to metaflac, blank be default
oggencpath="" #path to oggenc binary, blank by default
lamepath="" #path to lame binary, blank by default

opts = {
"outdir":"./", #the directory we output to, defaults to current directory
"overwrite":False, #do we overwrite existing files
"overwrite_old":False, #do we overwrite existing files if the source is newer
"nodirs":False, #do not create directories (dump all files into single dir)
"copy":False, #Copy non flac files (default is to ignore)
"buffer":2048, #How much to read in at a time
"lameopts":"qscale:a 0", #your mp3 encoding settings
"oggencopts":"qscale:a 9", # your vorbis encoder settings
"flacopts":"-q 8", #your flac encoder settings
"include_root":False,
"stderr":False,
}

#This area deals with checking the command line options,

from optparse import OptionParser

parser = OptionParser(usage=infohelp())
parser.add_option("-c","--copy",action="store_true",dest="copy",
      default=False,help="Copy non flac files across (default=False)")

parser.add_option("-v","--vorbis-options",dest="oggencopts",
        default="qscale:a 9",help="Semiolon delimited options to pass to oggenc,for example:" +
        " 'qscale:a'." +
      " Any oggenc long option (one with two '--' in front) can be specified in the above format.")
parser.add_option("-l","--lame-options",dest="lameopts",
        default="qscale:a 0",help="Semicolon delimited options (for output file) to pass to ffmpeg for mp3 encoding, for example:           'b:a 320k'. "+
      "Any ffmpeg option can be specified here, if you want a short option (e.g. -h), then just do 'h'. "+
      "If you want a long option (e.g. '--abr'), then you need a dash: '-abr'")
parser.add_option("-o","--outdir",dest="outdir",metavar="DIR", 
      help="Set custom output directory (default='./')",
      default="./"),
parser.add_option("-f","--force",dest="overwrite",action="store_true",
      help="Force overwrite of existing files (by default we skip)",
      default=False),
parser.add_option("-e","--stderr",dest="stderr",action="store_true",
      help="Print stderr messages of the child processes to stdout",
      default=False),
parser.add_option("-y","--overwrite_old",dest="overwrite_old",action="store_true",
      help="Force overwrite of existing files if the timestamp of the source has changed since (timestamp says it is newer)",
      default=False),
parser.add_option("-t","--threads",dest="threads",default=multiprocessing.cpu_count(),
      help="How many threads to run in parallel (default: autodetect [found %d cpu(s)] )" % multiprocessing.cpu_count()) 
parser.add_option("-n","--nodirs",dest="nodirs",action="store_true",
      default=False,help="Don't create Directories, put everything together")
parser.add_option("-x","--exclude",dest="exclude",default=None, help="exclude certain files from processing by PATTERN (regular expressions supported)")
parser.add_option("-r","--include-root",dest="root_include", action="store_true", default=False, help="Include the top-level directory in output path ( default=False )")

##The below isn't used anymore, so removed as an option (to re-add in future?)
#parser.add_option("-B","--buffer",dest="buffer",metavar="size", 
#      help="How much we should buffer before encoding to mp3 (in KB). The larger "+
#           "you set this too, the more of the song will be buffered before "+
#           "encoding. Set it high enough and it will buffer everything to RAM"+
#           "before encoding.")

(options,args) = parser.parse_args()

#update the opts dictionary with new values
opts.update(eval(options.__str__()))

#convert the formats in the args to valid formats for lame, oggenc and opusenc
opts['oggencopts'] = ' -'+' -'.join(opts['oggencopts'].split(';'))
#lame is stupid, it is not consistent, sometimes using long opts, sometimes not
#so we need to specify on command line with dashes whether it is a long op or short
opts['lameopts'] = ' -'+' -'.join(opts['lameopts'].split(';'))

print(header())
#pdb.set_trace()
try:
    opts['mode'] = args[0]

except(IndexError): #if no arguments specified
    print("No mode specified! Run with '-h' for help")
    sys.exit(-1) #quit the program with non-zero status

try:
    opts['dirpath'] = os.path.realpath(args[1])

except(IndexError):
    print("No directory specified! Run with '-h' for help")
    sys.exit(-1) #quit the program with non-zero status

#end command line checking

def signal_handler(signal, frame):
    global stop_conversion

    print("Stopping conversion...")
    stop_conversion = True

#start main code

stop_conversion = False
signal.signal(signal.SIGINT, signal_handler)

#create instances of classes
mp3Class = mp3()
shellClass = shell()
flacClass = flac()
vorbisClass = vorbis()
filelist=shellClass.getfiles(opts['dirpath'])


#if "exclude" set, filter out by regular expression
if opts['exclude'] != None:
    rex = re.compile(opts['exclude'])
    filelist = filter(lambda x: re.search(rex,x) == None, filelist) #Only return items that don't match

flacnum = 0 #tells us number of flac media files
filenum = 0 #tells us number of files

#pdb.set_trace()
for files in filelist:
    filenum += 1
    #make sure both flac and FLAC are read
    if (str.lower(files [-4:]) == "flac"):
        flacnum += 1


print("There are %d files, of which %d are convertable FLAC files" % \
(filenum,flacnum))
print("We are running %s simultaneous transcodes" % opts['threads'])
 
if flacnum == 0:
    print("Error, we got no flac files. Are you sure you put in the correct directory?")
    sys.exit(-1) 
x = 0 #temporary variable, only to keep track of number of files we have done

#Why did we not use "for file in filelist" for the code below? Because this is
#more flexible. As an example for multiple file encoding simultaniously, we
#can do filelist.pop() multiple times (well, along with some threading, but its
#good to plan for the future.

#one thread is always for the main program, so if we want two encoding threads,
#we need three threads in total
opts['threads'] = int(opts['threads']) + 1

while len(filelist) != 0 and not stop_conversion: #while the length of the list is not 0 (i.e. not empty)
    #remove and return the first element in the list
    current_file = filelist.pop()

    #threaded process, used by default

    threading.Thread(target=encode_thread,args=(
        current_file,
        x,
        opts
        )
    ).start()

    #Don't use threads, single process, used for debugging
    #x = encode_thread(current_file,nodirs,x,lameopts,flacopts,oggencopts,mode)
    while threading.activeCount() == opts['threads']:
        #just sit and wait. we check every tenth second to see if it has
        #finished
        time.sleep(0.3)
    x += 1

if stop_conversion:
    print("Waiting for threads to finish...")

#END
