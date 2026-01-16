#! /usr/bin/env python
'''
Handle ISO (9660) file systems for optical discs: https://wiki.osdev.org/ISO_9660
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from pathlib import Path

class IsoFS(FileSystem):
    '''Class to represent an ISO (9660) optical disc'''
    def __init__(self, file_obj, path=None):
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.sector_size = None

    def get_sector_size(self):
        if self.sector_size is None:
            raise NotImplementedError("TODO DETERMINE SECTOR SIZE AUTOMATICALLY FROM CD001 AT BEGINNING")
        return self.sector_size

    def read_system_area(self):
        '''Read the System Area (sectors 0x00-0x0F = first 16 sectors) of the ISO

        Returns:
            `bytes`: The System Area (sectors 0x00-0x0F = first 16 sectors) of the ISO
        '''
        self.file.seek(0)
        return self.file.read(16 * self.get_sector_size())

    def __iter__(self):
        print(self.read_system_area().hex())
        raise NotImplementedError("TODO NEED TO IMPLEMENT")
