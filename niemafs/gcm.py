#! /usr/bin/env python
'''
Handle Nintendo GameCube mini-DVD GCM file system
'''

# NiemaFS imports
from niemafs.common import FileSystem

class GcmFS(FileSystem):
    '''Class to represent a `Nintendo GameCube GCM mini-DVD <https://www.gc-forever.com/yagcd/chap13.html#sec13>`_'''
    def __init__(self, file_obj, path=None):
        raise NotImplementedError("TODO https://www.gc-forever.com/yagcd/chap13.html#sec13")
