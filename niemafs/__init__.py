#! /usr/bin/env python
# standard imports
from warnings import warn

# NiemaFS imports
from niemafs.common import clean_string, FileSystem, open_file, safename
from niemafs.dir import DirFS
from niemafs.gcn import GcmFS
from niemafs.iso import IsoFS
from niemafs.tar import TarFS
from niemafs.zip import ZipFS

# build __all__
__all__ = [
    'clean_string', 'FileSystem', 'open_file', 'safename', # common.py
    'DirFS',                                               # dir.py
    'GcmFS',                                               # gcn.py
    'IsoFS',                                               # iso.py
    'TarFS',                                               # tar.py
    'ZipFS',                                               # zip.py
]

# WiiFS depends on PyCryptodome, so import it afterwards
try:
    from niemafs.wii import WiiFS
    __all__.append('WiiFS')
except:
    warn("Unable to import WiiFS. Ensure that you have PyCryptodome installed")
