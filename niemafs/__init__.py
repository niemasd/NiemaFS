#! /usr/bin/env python
# standard imports
from warnings import warn

# NiemaFS imports
from niemafs.common import clean_string, FileSystem, open_file, safename
from niemafs.dir import DirFS
from niemafs.gcn import GcmFS, GcRarcFS, TgcFS
from niemafs.hfs import HfsFS
from niemafs.iso import IsoFS
from niemafs.pcecd import PceCdFS
from niemafs.tar import TarFS
from niemafs.zip import ZipFS

# build __all__
__all__ = [
    'clean_string', 'FileSystem', 'open_file', 'safename', # common.py
    'DirFS',                                               # dir.py
    'GcmFS', 'GcRarcFS', 'TgcFS',                          # gcn.py
    'HfsFS',                                               # hfs.py
    'IsoFS',                                               # iso.py
    'PceCdFS',                                             # pcecd.py
    'TarFS',                                               # tar.py
    'ZipFS',                                               # zip.py
]

# WiiFS depends on PyCryptodome, so import it afterwards
try:
    from niemafs.wii import WiiFS
    __all__.append('WiiFS')
except:
    warn("Unable to import WiiFS. Ensure that you have PyCryptodome installed")
