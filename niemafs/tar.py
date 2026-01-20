#! /usr/bin/env python
'''
Handle TAR archives
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from datetime import datetime
from pathlib import Path
from tarfile import TarFile

class TarFS(FileSystem):
    '''Class to represent a TAR archive'''
    def __init__(self, file_obj, path=None):
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.tar = TarFile(fileobj=self.file, mode='r')

    def __del__(self):
        if hasattr(self, 'tar'):
            self.tar.close()

    def __iter__(self):
        for curr_entry in self.tar.getmembers():
            curr_path = Path(curr_entry.name)
            curr_timestamp = datetime.fromtimestamp(curr_entry.mtime)
            if curr_entry.isdir():
                curr_data = None
            else:
                curr_data = self.tar.extractfile(curr_entry).read()
            yield (curr_path, curr_timestamp, curr_data)
