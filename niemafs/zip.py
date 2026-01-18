#! /usr/bin/env python
'''
Handle ZIP archives
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

class ZipFS(FileSystem):
    '''Class to represent a ZIP archive'''
    def __init__(self, file_obj, path=None):
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.zip = ZipFile(self.file, 'r')

    def __del__(self):
        if hasattr(self, 'zip'):
            self.zip.close()

    def __iter__(self):
        for curr_entry in self.zip.infolist():
            curr_path = Path(curr_entry.filename)
            curr_timestamp = datetime(*curr_entry.date_time)
            if curr_entry.is_dir():
                curr_data = None
            else:
                curr_data = self.zip.read(curr_entry.filename)
            yield (curr_path, curr_timestamp, curr_data)
