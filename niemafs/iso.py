#! /usr/bin/env python
'''
Handle ISO (9660) file systems for optical discs
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

    def read_system_area(self):
        '''Read the System Area (first 32,768 bytes) of the ISO

        Returns:
            `bytes`: The System Area (first 32,768 bytes) of the ISO
        '''
        self.file.seek(0)
        return self.file.read(32768)

    def __iter__(self):
        print(self.read_system_area().hex())
        raise NotImplementedError("TODO NEED TO IMPLEMENT")
