#! /usr/bin/env python
'''
Handle ZIP archives
'''

# NiemaFS imports
from niemafs.common import DEFAULT_BUFFER_SIZE, FileSystem

# standard imports
from datetime import datetime
from pathlib import Path
from warnings import warn

class DirFS(FileSystem):
    '''Class to represent a directory on disk'''
    def __init__(self, path, file_obj=None):
        if file_obj is not None:
            warn("DirFS initializer was given non-None 'file_obj' parameter, which will be ignored")
        super().__init__(path=path, file_obj=None)

    def __iter__(self):
        for curr_path in self.path.rglob('*'):
            curr_timestamp = datetime.fromtimestamp(curr_path.stat().st_mtime)
            if curr_path.is_dir():
                curr_data = None
            else:
                with open(curr_path, mode='rb', buffering=DEFAULT_BUFFER_SIZE) as curr_file:
                    curr_data = curr_file.read()
            yield (curr_path, curr_timestamp, curr_data)
