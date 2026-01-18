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
    '''Class to represent a `Nintendo Wii DVD <https://wiibrew.org/wiki/Wii_disc>`_.'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        raise NotImplementedError("TODO https://wiibrew.org/wiki/Wii_disc")

    def __iter__(self):
        raise NotImplementedError("TODO https://wiibrew.org/wiki/Wii_disc")
