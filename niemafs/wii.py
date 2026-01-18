#! /usr/bin/env python
'''
Handle Nintendo Wii DVD file system
'''

# NiemaFS imports
from niemafs.common import clean_string, FileSystem

# imports
from datetime import datetime
from pathlib import Path
from struct import unpack
from warnings import warn

class WiiFS(FileSystem):
    '''Class to represent a `Nintendo Wii DVD <https://wiibrew.org/wiki/Wii_disc#%22System_Area%22>`_.'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.header = None # Header

    def get_header(self):
        '''Return the `Header <https://wiibrew.org/wiki/Wii_disc#Header>`_ of the Wii disc.

        Returns:
            `bytes`: The Header of the Wii disc.
        '''
        if self.header is None:
            self.header = self.read_file(0x0000, 0x0400)
        return self.header

    def parse_header(self):
        '''Return a parsed version of the `Header <https://wiibrew.org/wiki/Wii_disc#Header>`_ of the Wii disc.

        Returns:
            `dict`: A parsed version of the Header of the Wii disc.
        '''
        # set things up
        data = self.get_header()
        out = dict()

        # parse raw Header data
        out['game_code'] =                 data[0x0000 : 0x0004] # Game Code "XYYZ": X = Console ID, YY = Game Code, Z = Country Code
        out['maker_code'] =                data[0x0004 : 0x0006] # Maker Code
        out['disk_id'] =                   data[0x0006]          # Disk ID
        out['version'] =                   data[0x0007]          # Version
        out['audio_streaming'] =           data[0x0008]          # Audio Streaming
        out['stream_buffer_size'] =        data[0x0009]          # Stream Buffer Size
        out['offsets_0x000A_0x0017'] =     data[0x000A : 0x0018] # Unused (should be 0s)
        out['wii_magic_word'] =            data[0x0018 : 0x001C] # Wii Magic Word (should be 0x5d1c9ea3)
        out['gc_magic_word'] =             data[0x001C : 0x0020] # GameCube Magic Word (should be 0s on Wii discs)
        out['game_name'] =                 data[0x0020 : 0x0060] # Game Name
        out['disable_hash_verification'] = data[0x0060]          # Disable Hash Verification
        out['disable_disc_encryption'] =   data[0x0061]          # Disable Disc Encryption and H3 Hash Table Load/Verification
        out['offsets_0x0062_0x007F'] =     data[0x0062 : 0x0080] # Unknown
        out['offsets_0x0080_0x043F'] =     data[0x0080 : 0x0440] # Unushed (should be 0s)

        # clean strings
        for k in ['game_code', 'maker_code', 'game_name']:
            try:
                out[k] = clean_string(out[k])
            except:
                warn("Unable to parse Header '%s' as string: %s" % (k, out[k]))

        # return final parsed data
        return out

    def __iter__(self):
        print(self.parse_header())
        raise NotImplementedError("TODO https://wiibrew.org/wiki/Wii_disc")
