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
