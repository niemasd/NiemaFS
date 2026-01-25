#! /usr/bin/env python
'''
Handle Nintendo GameCube file systems
'''

# NiemaFS imports
from niemafs.common import clean_string, FileSystem

# imports
from datetime import datetime
from io import BytesIO
from pathlib import Path
from struct import pack, unpack
from warnings import warn

class GcmFS(FileSystem):
    '''Class to represent a `Nintendo GameCube GCM mini-DVD <https://www.gc-forever.com/yagcd/chap13.html#sec13>`_.'''
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
        out['game_name'] =             data[0x0020 : 0x0400]                  # Game Name
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

    def parse_fst(fst_ind, parent_path, fst, string_table_start):
        '''Recursively parse the `File System Table (FST) <https://www.gc-forever.com/yagcd/chap13.html#sec13.4.1>`_.

        Args:
            `fst_ind` (`int`): This entry's index in the FST.

            `parent_path` (`Path`): The local `Path` of parent of this file/directory, or `None` if this is the root directory.

            `fst` (`bytes`): The raw bytes of the FST.

            `string_table_start` (`int`): Offset in the FST where the string table begins.

        Returns:
            `dict`: The root of the parsed FST.
        '''
        # set things up
        out = {'children':list(), 'is_root':False}

        # parse raw FST entry data
        entry_start_offset = fst_ind * 12
        is_dir =        bool(fst[entry_start_offset])                                                   # Flags: 0 = file, 1 = directory
        st_index =      unpack('>I', b'\x00' + fst[entry_start_offset + 1 : entry_start_offset + 4])[0] # Filename as Offset into String Table
        out['offset'] = unpack('>I', fst[entry_start_offset + 4 : entry_start_offset + 8])[0]           # File Offset (for files) or Parent Offset (for directories)
        out['length'] = unpack('>I', fst[entry_start_offset + 8 : entry_start_offset + 12])[0]          # File Size (for files) or Number of Entries (for root) or Next Offset (for directories

        # determine path
        if parent_path is None: # root
            out['path'] = Path('.')
            out['is_root'] = True
        else: # non-root
            fn_fst_offset = string_table_start + st_index
            fn = fst[fn_fst_offset : fst.find(b'\x00', fn_fst_offset)]
            try:
                fn = fn.decode()
            except:
                warn("Failed to parse filename as string: %s" % fn)
                fn = str(fn)
            out['path'] = parent_path / fn

        # if directory, recursively parse children
        if is_dir:
            fst_ind += 1
            while fst_ind < out['length']:
                child = GcmFS.parse_fst(fst_ind, out['path'], fst, string_table_start)
                fst_ind = child['fst_ind_next']
                out['children'].append(child)
            out['fst_ind_next'] = fst_ind
        else:
            out['fst_ind_next'] = fst_ind + 1

        # return final parsed data
        return out

    def __iter__(self):
        fst = self.get_fst_bin()
        string_table_start = 0x0C * unpack('>I', fst[0x08 : 0x0C])[0]
        to_visit = [GcmFS.parse_fst(0, None, fst, string_table_start)] # start at root directory
        while len(to_visit) != 0:
            file_entry = to_visit.pop()
            if len(file_entry['children']) == 0:
                file_data = self.read_file(file_entry['offset'], file_entry['length'])
            else:
                file_data = None
                to_visit += file_entry['children'][::-1] # descending order into stack = ascending order when popped
            if not file_entry['is_root']:
                yield (file_entry['path'], None, file_data)

class TgcFS(FileSystem):
    '''Class to represent a `Nintendo GameCube TGC image <https://hitmen.c02.at/files/yagcd/yagcd/chap14.html#sec14.8>`_.'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.header = None # Header
        self.gcm = None    # Embedded GCM Data (bogus values fixed)

    def get_header(self):
        '''Return the `Header <https://hitmen.c02.at/files/yagcd/yagcd/chap14.html#sec14.8.1>`_ of the TGC.

        Returns:
            `bytes`: The Header of the TGC.
        '''
        if self.header is None:
            self.header = self.read_file(0x00, 0x38)
        return self.header

    def parse_header(self):
        '''Return a parsed version of the `Header <https://hitmen.c02.at/files/yagcd/yagcd/chap14.html#sec14.8.1>`_ of the TGC.

        Returns:
            `dict`: A parsed version of the Header of the TGC.
        '''
        # set things up
        data = self.get_header()
        out = dict()

        # parse raw Header data
        out['magic_word'] =             data[0x00 : 0x04]                  # TGC Magic Word (should be 0xae0f38a2)
        out['offsets_0x04_0x07'] =      data[0x04 : 0x08]                  # Unknown (usually all 0s)
        out['header_size'] =            unpack('>I', data[0x08 : 0x0C])[0] # Header Size (usually 0x8000)
        out['offsets_0x0C_0x0F'] =      data[0x0C : 0x10]                  # Unknown (usually 0x00100000)
        out['embedded_fst_offset'] =    unpack('>I', data[0x10 : 0x14])[0] # Offset to FST inside embedded GCM
        out['embedded_fst_size'] =      unpack('>I', data[0x14 : 0x18])[0] # Size of FST inside embedded GCM
        out['embedded_max_fst_size'] =  unpack('>I', data[0x18 : 0x1C])[0] # Max Size of FST inside embedded GCM
        out['embedded_boot_offset'] =   unpack('>I', data[0x1C : 0x20])[0] # Offset to Boot-DOL inside embedded GCM
        out['embedded_boot_size'] =     unpack('>I', data[0x20 : 0x24])[0] # Size of Boot-DOl inside embedded GCM
        out['file_area_offset'] =       unpack('>I', data[0x24 : 0x28])[0] # Offset to File Area inside embedded GCM
        out['file_area_size'] =         unpack('>I', data[0x28 : 0x2C])[0] # Size of File Area
        out['embedded_banner_offset'] = unpack('>I', data[0x2C : 0x30])[0] # Offset to Banner inside embedded GCM(?)
        out['embedded_banner_size'] =   unpack('>I', data[0x30 : 0x34])[0] # Size of Banner inside embedded GCM(?)
        out['fst_spoof_amount'] =       unpack('>I', data[0x34 : 0x38])[0] # FST Spoof Amount

        # return final parsed data
        return out

    def get_gcm(self):
        '''Return the `Embedded GCM <https://hitmen.c02.at/files/yagcd/yagcd/chap14.html#sec14.8.2>`_ of the TGC.

        Args:
            `fix` (`bool`): `True` to update the offsets of the embedded GCM data with their correct values based on the Header, otherwise `False` to return the raw embedded GCM data.

        Returns:
            `bytes`: The Embedded GCM of the TGC.
        '''
        if self.gcm is None:
            # load raw GCM data
            header = self.parse_header()
            header_size = header['header_size']
            gcm_data = bytearray(self.read_file(header_size))

            # fix Boot-DOL and FST offsets
            fixed_boot_offset = header['embedded_boot_offset'] - header_size
            fixed_fst_offset = header['embedded_fst_offset'] - header_size
            gcm_data[0x0420 : 0x0424] = pack('>I', fixed_boot_offset)
            gcm_data[0x0424 : 0x0428] = pack('>I', fixed_fst_offset)

            # fix FST entries
            delta = header['file_area_offset'] - header['fst_spoof_amount'] - header_size
            num_entries = unpack('>I', gcm_data[fixed_fst_offset + 8 : fixed_fst_offset + 12])[0]
            for entry_offset in range(fixed_fst_offset, fixed_fst_offset + (12*num_entries), 12):
                if not bool(gcm_data[entry_offset]): # only update files
                    orig_offset = unpack('>I', gcm_data[entry_offset + 4 : entry_offset + 8])[0]
                    fixed_offset = orig_offset + delta
                    gcm_data[entry_offset + 4 : entry_offset + 8] = pack('>I', fixed_offset)

            # finalize
            self.gcm = bytes(gcm_data)
        return self.gcm

    def __iter__(self):
        return iter(GcmFS(BytesIO(self.get_gcm())))

class GcRarcFS(FileSystem):
    '''Class to represent a `Nintendo GameCube RARC (.arc) archives <https://www.gc-forever.com/yagcd/chap15.html#sec15.3>`_.'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.header = None      # Header
        self.data_header = None # Data Header

    def get_header(self):
        '''Return the `Header <https://www.lumasworkshop.com/wiki/RARC_(File_Format)>`_ of the RARC.

        Returns:
            `bytes`: The Header of the RARC.
        '''
        if self.header is None:
            self.header = self.read_file(0x00, 0x20)
        return self.header

    def parse_header(self):
        '''Return a parsed version of the `Header <https://www.lumasworkshop.com/wiki/RARC_(File_Format)#Header>`_ of the RARC.

        Returns:
            `dict`: A parsed version of the Header of the RARC.
        '''
        # set things up
        data = self.get_header()
        out = dict()

        # parse raw Header data
        out['magic_word'] =          data[0x00 : 0x04]                  # should be 'RARC'
        out['size'] =                unpack('>I', data[0x04 : 0x08])[0] # Size of Entire File
        out['data_header_offset'] =  unpack('>I', data[0x08 : 0x0C])[0] # Data Header Offset (always 0x20)
        out['data_start_offset'] =   unpack('>I', data[0x0C : 0x10])[0] # Data Start Offset (add 0x20 to this value)
        out['data_section_size'] =   unpack('>I', data[0x10 : 0x14])[0] # Size of File Data Section
        out['mram_size'] =           unpack('>I', data[0x14 : 0x18])[0] # Size of All MRAM Files in File Data Section
        out['aram_size'] =           unpack('>I', data[0x18 : 0x1C])[0] # Size of All ARAM Files in File Data Section
        out['dvd_size'] =            unpack('>I', data[0x1C : 0x20])[0] # Size of All DVD Files in File Data Section

        # clean strings
        for k in ['magic_word']:
            try:
                out[k] = clean_string(out[k])
            except:
                warn("Unable to parse Header '%s' as string: %s" % (k, out[k]))

        # check for validity
        if out['magic_word'] != 'RARC':
            warn("RARC magic word should be 'RARC', but it was: %s" % out['magic_word'])

        # return final parsed data
        return out

    def get_data_header(self):
        '''Return the `Data Header <https://www.lumasworkshop.com/wiki/RARC_(File_Format)#Data_Header>`_ of the RARC.

        Returns:
            `bytes`: The Data Header of the RARC.
        '''
        if self.data_header is None:
            self.data_header = self.read_file(self.parse_header()['data_header_offset'], 0x20)
        return self.data_header

    def parse_data_header(self):
        '''Return a parsed version of the `Data Header <https://www.lumasworkshop.com/wiki/RARC_(File_Format)#Data_Header>`_ of the RARC.

        Returns:
            `dict`: A parsed version of the Data Header of the RARC.
        '''
        # set things up
        data = self.get_data_header()
        out = dict()

        # parse raw Data Header data
        out['num_dirs'] =            unpack('>I', data[0x00 : 0x04])[0] # Number of Directory Nodes
        out['dir_offset'] =          unpack('>I', data[0x04 : 0x08])[0] # Offset to Directory Node Section (always 0x20) (add 0x20 to this)
        out['num_files'] =           unpack('>I', data[0x08 : 0x0C])[0] # Number of File Nodes
        out['file_offset'] =         unpack('>I', data[0x0C : 0x10])[0] # Offset to File Node Section (add 0x20 to this)
        out['string_table_size'] =   unpack('>I', data[0x10 : 0x14])[0] # Size of String Table
        out['string_table_offset'] = unpack('>I', data[0x14 : 0x18])[0] # Offset to String Table (add 0x20 to this)
        out['next_file_index'] =     unpack('>H', data[0x18 : 0x1A])[0] # Next Available File Index (number of File Nodes that are files?)
        out['keep_file_ID_sync'] =   bool(data[0x1A])                   # Keep File IDs Synced
        out['offsets_0x1B_0x1F'] =   data[0x1B : 0x20]                  # Padding (all 0s)

        # return final parsed data
        return out

    def parse_dir_node(data):
        '''Return a parsed version of a `Directory Node <https://www.lumasworkshop.com/wiki/RARC_(File_Format)#Directory_Node_section>`_ of the RARC.

        Args:
            `data` (`bytes`): The raw Directory Node data

        Returns:
            `dict`: A parsed version of the Directory Node
        '''
        # set things up
        if len(data) != 16:
            raise ValueError("Directory Node data must be exactly 16 bytes: %s" % data)
        out = dict()

        # parse raw node data
        out['name_prefix'] =      data[0x00 : 0x04]                  # First 4 Characters of Directory Name (all caps)
        out['name_offset'] =      unpack('>I', data[0x04 : 0x08])[0] # Offset of Directory Name in String Table
        out['name_hash'] =        unpack('>H', data[0x08 : 0x0A])[0] # Hash of Directory Name
        out['num_files'] =        unpack('>H', data[0x0A : 0x0C])[0] # Number of Files in this Directory Node
        out['file_nodes_index'] = unpack('>I', data[0x0C : 0x10])[0] # Index of First File Node in this Directory Node

        # clean strings
        for k in ['name_prefix']:
            try:
                out[k] = clean_string(out[k])
            except:
                warn("Unable to parse Header '%s' as string: %s" % (k, out[k]))

        # return final parsed data
        return out

    def parse_file_node(data):
        '''Return a parsed version of a `File Node <https://wiki.tockdom.com/wiki/RARC_(File_Format)#Directory>`_ of the RARC.

        Args:
            `data` (`bytes`): The raw File Node data

        Returns:
            `dict`: A parsed version of the File Node
        '''
        # set things up
        if len(data) != 0x14:
            raise ValueError("File Node data must be exactly 0x14 bytes: %s" % data)
        out = dict()

        # parse raw node data
        out['index'] =             unpack('>H', data[0x00 : 0x02])[0]           # Node Index (0xFFFF if this is a subdirectory)
        out['name_hash'] =         unpack('>H', data[0x02 : 0x04])[0]           # Hash of Node Name
        out['attributes'] =        data[0x04]                                   # Node Attributes
        out['name_offset'] =       unpack('>I', b'\x00' + data[0x05 : 0x08])[0] # Name Offset in String Table
        out['offset'] =            unpack('>I', data[0x08 : 0x0C])[0]           # If File: Offset in File Data Section; If Directory: Index in Directory Node Section
        out['size'] =              unpack('>I', data[0x0C : 0x10])[0]           # If File: Size of File's Data; If Directory: always 0x10
        out['offsets_0x10_0x13'] = data[0x10 : 0x14]                            # Unknown (all 0s?)

        # parse node attributes
        out['attributes'] = GcRarcFS.parse_node_attributes(out['attributes'])

        # return final parsed data
        return out

    def parse_node_attributes(x):
        '''Return a parsed version of the `Attributes <https://www.lumasworkshop.com/wiki/RARC_(File_Format)#Node_Attributes>`_ of a File Node of the RARC.

        Args:
            `x` (`int`): The integer representation of the Attributes of a File Node.

        Returns:
            `dict`: A parsed version of the Attributes.
        '''
        return {
            'is_file':       bool(x & 0x01), # Node is a File
            'is_dir':        bool(x & 0x02), # Node is a Directory
            'is_compressed': bool(x & 0x04), # Node's File is Compressed
            'preload_mram':  bool(x & 0x10), # Preload File to Main RAM (MRAM)
            'preload_aram':  bool(x & 0x20), # Preload File to Auxiliary RAM (ARAM)
            'load_dvd':      bool(x & 0x40), # Load File from DVD when Needed
            'is_yaz0':       bool(x & 0x80), # Node is YAZ0-Compressed ('is_compressed' should be True as well)
        }

    def __iter__(self):
        # set things up
        header = self.parse_header()
        data_header = self.parse_data_header()
        dir_nodes_start = data_header['dir_offset'] + 0x20
        dir_nodes = [GcRarcFS.parse_dir_node(self.read_file(i,16)) for i in range(dir_nodes_start, dir_nodes_start + (16 * data_header['num_dirs']), 16)]
        file_nodes_start = data_header['file_offset'] + 0x20
        file_nodes = [GcRarcFS.parse_file_node(self.read_file(i,0x14)) for i in range(file_nodes_start, file_nodes_start + (0x14 * data_header['num_files']), 0x14)]
        string_table = self.read_file(data_header['string_table_offset'] + 0x20, data_header['string_table_size'])
        file_data_start = header['data_start_offset'] + 0x20

        # load node names
        for node in dir_nodes + file_nodes:
            node['name'] = clean_string(string_table[node['name_offset'] : string_table.find(b'\x00',node['name_offset'])])

        # iterate over all files
        dir_nodes[0]['parent_path'] = Path('.')
        for dir_node_ind, dir_node in enumerate(dir_nodes):
            dir_path = dir_node['parent_path'] / dir_node['name']
            yield (dir_path, None, None)
            for file_node_ind in range(dir_node['file_nodes_index'], dir_node['file_nodes_index'] + dir_node['num_files']):
                file_node = file_nodes[file_node_ind]
                if file_node['attributes']['is_dir']:
                    if file_node['name'] in {'.', '..'}:
                        continue # skip current ('.') and parent ('..') directories
                    dir_nodes[file_node['offset']]['parent_path'] = dir_path
                else:
                    yield (dir_path / file_node['name'], None, self.read_file(file_data_start + file_node['offset'], file_node['size']))
