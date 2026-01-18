#! /usr/bin/env python
'''
Handle Nintendo GameCube mini-DVD GCM file system
'''

# NiemaFS imports
from niemafs.common import clean_string, FileSystem

# imports
from struct import unpack
from warnings import warn

class GcmFS(FileSystem):
    '''Class to represent a `Nintendo GameCube GCM mini-DVD <https://www.gc-forever.com/yagcd/chap13.html#sec13>`_'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.boot_bin = None # Disk Header (boot.bin)
        self.bi2_bin = None  # Disk Header Information (bi2.bin)

        # load header to ensure file validity up-front
        self.get_boot_bin()
        self.get_bi2_bin()

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

    def parse_boot_bin(self):
        '''Return a parsed version of the `Disk Header ("boot.bin") <https://www.gc-forever.com/yagcd/chap13.html#sec13.1>`_ of the GCM.

        Returns:
            `dict`: A parsed version of the Disk Header ("boot.bin") of the GCM.
        '''
        # set things up
        data = self.get_boot_bin()
        out = dict()

        # parse raw Disk Header ("boot.bin") data
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
        out['debug_monitor_address'] = data[0x0404 : 0x0408]                  # Address(?) to load Debug Monitor (dh.bin)?
        out['offsets_0x0408_0x0419'] = data[0x0408 : 0x0420]                  # Unused (should be 0s)
        out['main_dol_offset'] =       unpack('>I', data[0x0420 : 0x0424])[0] # Offset of Main Executable Bootfile (main.dol)
        out['fst_offset'] =            unpack('>I', data[0x0424 : 0x0428])[0] # Offset of FST (fst.bin)
        out['fst_size'] =              unpack('>I', data[0x0428 : 0x042C])[0] # Size of FST (fst.bin)
        out['max_fst_size'] =          unpack('>I', data[0x042C : 0x0430])[0] # Max Size of FST (fst.bin)
        out['user_position'] =         data[0x0430 : 0x0434]                  # User Position(?)
        out['user_length'] =           data[0x0434 : 0x0438]                  # User Length(?)
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

    def __iter__(self):
        print(self.parse_boot_bin()); exit() # TODO
        raise NotImplementedError("TODO") # TODO
