#! /usr/bin/env python
'''
Handle ISO (9660) file systems for optical discs: https://wiki.osdev.org/ISO_9660
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from pathlib import Path

# constants
ISO9660_PVD_MAGIC_WORD = bytes(ord(c) for c in 'CD001') # https://wiki.osdev.org/ISO_9660#Volume_Descriptors
MAGIC_WORD_SEARCH_SIZE = 50000 # magic word probably in first 50 KB; increase this if fail to find

class IsoFS(FileSystem):
    '''Class to represent an ISO (9660) optical disc'''
    def __init__(self, file_obj, path=None):
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.sector_size = None

    def get_sector_size(self):
        '''Return the sector size of this ISO in bytes (usually 2048)

        Returns:
            `int`: The sector size of this ISO in bytes
        '''
        if self.sector_size is None:
            start_offset = self.file.tell()
            self.file.seek(0)
            chunk = self.file.read(MAGIC_WORD_SEARCH_SIZE)
            self.file.seek(start_offset)
            magic_word_offset = chunk.find(ISO9660_PVD_MAGIC_WORD)
            if magic_word_offset == -1:
                raise ValueError("Failed to find ISO 9660 magic word 'CD001' in first %d bytes" % MAGIC_WORD_SEARCH_SIZE)
            self.sector_size = (magic_word_offset - 1) // 16
        return self.sector_size

    def read_system_area(self):
        '''Read the System Area (sectors 0x00-0x0F = first 16 sectors) of the ISO

        Returns:
            `bytes`: The System Area (sectors 0x00-0x0F = first 16 sectors) of the ISO
        '''
        self.file.seek(0)
        return self.file.read(16 * self.get_sector_size())

    def read_primary_volume_descriptor(self):
        '''Read the Primary Volume Descriptor (PVD; sector 0x10 = 16) of the ISO

        Returns:
            `bytes`: The Primary Volume Descriptor (PVD; sector 0x10 = 16) of the ISO
        '''
        self.file.seek(16 * self.get_sector_size())
        return self.file.read(self.get_sector_size())

    def __iter__(self):
        print(self.read_primary_volume_descriptor())
        raise NotImplementedError("TODO NEED TO IMPLEMENT")
