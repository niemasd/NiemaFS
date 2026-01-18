#! /usr/bin/env python
'''
Handle Nintendo GameCube mini-DVD GCM file system
'''

# NiemaFS imports
from niemafs.common import FileSystem

class GcmFS(FileSystem):
    '''Class to represent a `Nintendo GameCube GCM mini-DVD <https://www.gc-forever.com/yagcd/chap13.html#sec13>`_'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)

    def get_boot_bin(self):
        pass
