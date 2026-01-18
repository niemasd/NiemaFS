#! /usr/bin/env python
'''
Handle Nintendo GameCube mini-DVD GCM file system
'''

# NiemaFS imports
from niemafs.common import clean_string, FileSystem

# imports
from datetime import datetime
from struct import unpack
from warnings import warn

class GcmFS(FileSystem):
    '''Class to represent a `Nintendo GameCube GCM mini-DVD <https://www.gc-forever.com/yagcd/chap13.html#sec13>`_'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.boot_bin = None   # Disk Header (boot.bin)
        self.bi2_bin = None    # Disk Header Information (bi2.bin)
        self.appldr_bin = None # Apploader (appldr.bin)
        self.fst_bin = None    # File System Table (FST) (fst.bin)

        # load header to ensure file validity up-front
        self.get_boot_bin()
        self.get_bi2_bin()
        self.get_appldr_bin()
        self.get_fst_bin()

    def parse_ascii_date(data):
        '''Parse a date in the "YYYY/MM/DD" format.

        Args:
            `data` (`bytes`): A date in the "YYYY/MM/DD" format.

        Returns:
            `datetime`: A Python `datetime` object.
        '''
        if isinstance(data, bytes):
            data = data.decode()
        return datetime.strptime(data, '%Y/%m/%d')

    def parse_fst_entry(data):
        '''Parse a `File System Table (FST) entry <https://www.gc-forever.com/yagcd/chap13.html#sec13.4.1>`_.

        Args:
            `data` (`bytes`): The raw bytes of the FST entry.

        Returns:
            `dict`: The parsed FST entry.
        '''
        # set things up
        if len(data) != 12:
            raise ValueError("FST entries must be exactly 12 bytes in length: %s" % data)
        out = dict()

        # parse raw FST entry data
        out['flags'] =    data[0x00]                         # Flags: 0 = file, 1 = directory
        out['filename'] = data[0x01 : 0x04]                  # Filename as Offset into String Table
        out['offset'] =   unpack('>I', data[0x04 : 0x08])[0] # File Offset (for files) or Parent Offset (for directories)
        out['length'] =   unpack('>I', data[0x08 : 0x0C])[0] # File Size (for files) or Number of Entries (for root) or Next Offset (for directories)

        # return final parsed data
        return out

    def get_boot_bin(self):
        '''Return the `Disk Header ("boot.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.1>`_ of the GCM.

        Returns:
            `bytes`: The Disk Header ("boot.bin") of the GCM.
        '''
        if self.boot_bin is None:
            self.boot_bin = self.read_file(0x0000, 0x0440)
        return self.boot_bin

    def get_bi2_bin(self):
        '''Return the `Disc Header Information ("bi2.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.2>`_ of the GCM.

        Returns:
            `bytes`: The Disc Header Information ("bi2.bin") of the GCM.
        '''
        if self.bi2_bin is None:
            self.bi2_bin = self.read_file(0x0440, 0x2000)
        return self.bi2_bin

    def get_appldr_bin(self):
        '''Return the `Apploader ("appldr.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.3>`_ of the GCM.

        Returns:
            `bytes`: The Apploader ("appldr.bin") of the GCM.
        '''
        if self.appldr_bin is None:
            size = unpack('>I', self.read_file(0x2440 + 0x0014, 4))[0]
            self.appldr_bin = self.read_file(0x2440, size)
        return self.appldr_bin

    def get_fst_bin(self):
        '''Return the `File System Table (FST, "fst.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.4>`_ of the GCM.

        Returns:
            `bytes`: The File System Table (FST, "fst.bin") of the GCM.
        '''
        if self.fst_bin is None:
            parsed_boot_bin = self.parse_boot_bin()
            self.fst_bin = self.read_file(parsed_boot_bin['fst_offset'], parsed_boot_bin['fst_size'])
        return self.fst_bin

    def parse_boot_bin(self):
        '''Return a parsed version of the `Disk Header ("boot.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.1>`_ of the GCM.

        Returns:
            `dict`: A parsed version of the Disk Header ("boot.bin") of the GCM.
        '''
        # set things up
        data = self.get_boot_bin()
        out = dict()

        # parse raw Disk Header (boot.bin) data
        out['game_code'] =             data[0x0000 : 0x0004]                  # Game Code "XYYZ": X = Console ID, YY = Game Code, Z = Country Code
        out['maker_code'] =            data[0x0004 : 0x0006]                  # Maker Code
        out['disk_id'] =               data[0x0006]                           # Disk ID
        out['version'] =               data[0x0007]                           # Version
        out['audio_streaming'] =       data[0x0008]                           # Audio Streaming
        out['stream_buffer_size'] =    data[0x0009]                           # Stream Buffer Size
        out['offsets_0x000A_0x001B'] = data[0x000A : 0x001C]                  # Unused (should be 0s)
        out['dvd_magic_word'] =        data[0x001C : 0x0020]                  # DVD Magic Word (should be 0xc2339f3d)
        out['game_name'] =             data[0x0020 : 0x03FF]                  # Game Name
        out['debug_monitor_offset'] =  unpack('>I', data[0x0400 : 0x0404])[0] # Offset of Debug Monitor (dh.bin)?
        out['debug_monitor_address'] = unpack('>I', data[0x0404 : 0x0408])[0] # Address(?) to load Debug Monitor (dh.bin)?
        out['offsets_0x0408_0x0419'] = data[0x0408 : 0x0420]                  # Unused (should be 0s)
        out['main_dol_offset'] =       unpack('>I', data[0x0420 : 0x0424])[0] # Offset of Main Executable Bootfile (main.dol)
        out['fst_offset'] =            unpack('>I', data[0x0424 : 0x0428])[0] # Offset of FST (fst.bin)
        out['fst_size'] =              unpack('>I', data[0x0428 : 0x042C])[0] # Size of FST (fst.bin)
        out['max_fst_size'] =          unpack('>I', data[0x042C : 0x0430])[0] # Max Size of FST (fst.bin) (usually same as previous, except in multi-disc games)
        out['user_position'] =         unpack('>I', data[0x0430 : 0x0434])[0] # User Position(?)
        out['user_length'] =           unpack('>I', data[0x0434 : 0x0438])[0] # User Length(?)
        out['offsets_0x0438_0x043B'] = data[0x0438 : 0x043C]                  # Unknown
        out['offsets_0x043C_0x043F'] = data[0x043C : 0x0440]                  # Unused (should be 0s)

        # clean strings
        for k in ['game_code', 'maker_code', 'game_name']:
            try:
                out[k] = clean_string(out[k])
            except:
                warn("Unable to parse Disk Header (boot.bin) '%s' as string: %s" % (k, out[k]))

        # return final parsed data
        return out

    def parse_bi2_bin(self):
        '''Return a parsed version of the `Disc Header Information ("bi2.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.2>`_ of the GCM.

        Returns:
            `dict`: A parsed version of the Disc Header Information ("bi2.bin") of the GCM.
        '''
        # set things up
        data = self.get_bi2_bin()
        out = dict()

        # parse raw Disk Header Information (bi2.bin) data
        out['debug_monitor_size'] =    unpack('>I', data[0x0000 : 0x0004])[0] # Debug-Monitor Size
        out['simulated_memory_size'] = unpack('>I', data[0x0004 : 0x0008])[0] # Simulated Memory Size
        out['argument_offset'] =       unpack('>I', data[0x0008 : 0x000C])[0] # Argument Offset
        out['debug_flag'] =            unpack('>I', data[0x000C : 0x0010])[0] # Debug Flag
        out['track_location'] =        unpack('>I', data[0x0010 : 0x0014])[0] # Track Location
        out['track_size'] =            unpack('>I', data[0x0014 : 0x0018])[0] # Track Size
        out['country_code'] =          unpack('>I', data[0x0018 : 0x001C])[0] # Country Code

        # return final parsed data
        return out

    def parse_appldr_bin(self):
        '''Return a parsed version of the `Apploader ("appldr.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.3>`_ of the GCM.

        Returns:
            `dict`: A parsed version of the Apploader ("appldr.bin") of the GCM.
        '''
        # set things up
        data = self.get_appldr_bin()
        out = dict()

        # parse raw Apploader (appldr.bin) data
        out['date'] =                  data[0x0000 : 0x000A]                  # Date (Version) of the Apploader
        out['offsets_0x000A_0x000F'] = data[0x000A : 0x0010]                  # Padding (should be 0s)
        out['apploader_entrypoint'] =  unpack('>I', data[0x0010 : 0x0014])[0] # Apploader Entrypoint
        out['apploader_size'] =        unpack('>I', data[0x0014 : 0x0018])[0] # Apploader Size
        out['trailer_size'] =          unpack('>I', data[0x0018 : 0x001C])[0] # Trailer Size
        out['offsets_0x001C_0x001F'] = data[0x001C : 0x0020]                  # Padding(?)
        out['apploader_code'] =        data[0x0020:]                          # Apploader Code (loaded to 0x81200000 in RAM)

        # parse dates
        for k in ['date']:
            try:
                out[k] = GcmFS.parse_ascii_date(out[k])
            except:
                warn("Unable to parse Apploader (appldr.bin) '%s' as date: %s" % (k, out[k]))

        # return final parsed data
        return out

    def __iter__(self):
        # load root directory entry and string table
        fst = self.get_fst_bin()
        root_dir_entry = GcmFS.parse_fst_entry(fst[0x00 : 0x0C])
        num_entries = root_dir_entry['length']
        string_table = [s.decode() for s in fst[0x0C * num_entries :][:-1].split(b'\x00')]
        raise NotImplementedError("TODO") # TODO CONTINUE HERE https://www.gc-forever.com/yagcd/chap13.html#sec13.4
