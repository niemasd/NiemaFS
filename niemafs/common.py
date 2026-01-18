#! /usr/bin/env python
'''
Common variables, classes, functions, etc.
'''

# standard imports
from abc import ABC, abstractmethod
from gzip import open as gopen
from pathlib import Path
from sys import stdin, stdout

# constants
DEFAULT_BUFFER_SIZE = 1048576 # 1 MB
DEFAULT_COMPRESS_LEVEL = 9

def open_file(path, mode='rb', buffering=DEFAULT_BUFFER_SIZE, compresslevel=DEFAULT_COMPRESS_LEVEL):
    '''Open a file for reading, writing, or appending. Automatically handles GZIP compression.

    Args:
        `path` (`Path`): The path of the file, or `None` for `stdin`/`stdout`.

        `mode` (`str`): The mode in which to open the file.

        `buffering` (`int`): The buffer size for buffered input/output.

    Returns:
        `file`-like object
    '''
    mode = mode.strip().lower()
    if path is None:
        if 'r' in mode:
            return stdin
        else:
            return stdout
    if isinstance(path, str):
        path = Path(path)
    ext = path.suffix.strip().lower()
    if ext == '.gz':
        return gopen(path, mode=mode, compresslevel=compresslevel)
    else:
        return open(path, mode=mode, buffering=buffering)

class FileSystem(ABC):
    '''Base class to represent a file system'''
    def __init__(self, path=None, file_obj=None):
        '''Initialize this `FileSystem` object.

        Args:
            `path` (`Path`): The path of this `FileSystem` object (e.g. the file on disk, or directory if it's a folder on disk).

            `file_obj` (`file`-like): The input stream of data for this `FileSystem`, or `None` if the `FileSystem` will be a folder on disk. Use `open` for files on disk, `gzip.open` for GZIP files on disk, `io.BytesIO` for bytes in-memory, etc.
        '''
        self.path = path
        self.file = file_obj

    @abstractmethod
    def __iter__(self):
        '''Iterate over the files and folders in this `FileSystem`

        Yields:
            Each file or folder in this `FileSystem` as a `tuple` containing the following elements: (1) the `Path` of the file/folder within this `FileSystem`, (2) the modification timestamp of this file/folder, and (3) the `bytes` of data for files or `None` for folders.
        '''
        pass

    def read_file(self, offset, length, return_to_init=False):
        '''Read data from the underlying `file`-like object.

        Args:
            `offset` (`int`): The offset from which to start reading.

            `length` (`int`): The number of bytes to read.

            `return_to_init` (`bool`): `True` to seek back to the initial offset after finishing the read, otherwise `False` (faster)

        Returns:
            `bytes`: The read data.
        '''
        if return_to_init:
            start_offset = self.file.tell()
        self.file.seek(offset)
        data = self.file.read(length)
        if return_to_init:
            self.file.seek(start_offset)
        return data
