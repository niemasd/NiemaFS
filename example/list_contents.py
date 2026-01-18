#! /usr/bin/env python3
'''
List the contents of a given file system
'''

# imports
from niemafs import DirFS, GcmFS, IsoFS, open_file, ZipFS
from pathlib import Path
from sys import argv, stderr

# constants
EXT_TO_CLASS = {
    None:  DirFS,
    'bin': IsoFS,
    'gcm': GcmFS,
    'iso': IsoFS,
    'zip': ZipFS,
}

# run tool
if __name__ == "__main__":
    # parse user args
    if len(argv) != 2 or argv[1].strip().replace('-','').lower() in {'h', 'help'}:
        print("USAGE: %s <input_path>" % argv[0], file=stderr); exit(1)
    path = Path(argv[1])
    if path.is_dir():
        ext = None
    else:
        ext = path.suffix.lstrip('.').strip().lower()
        if ext == 'gz':
            ext = path.suffixes[-2].lstrip('.').strip().lower()
    if ext not in EXT_TO_CLASS:
        print("ERROR: Unknown file extension: %s" % path)

    # list the contents of the file system
    if ext is None:
        file_obj = None
    else:
        file_obj = open_file(path, mode='rb')
    fs = EXT_TO_CLASS[ext](path=path, file_obj=file_obj)
    print("Path\tTimestamp\tSize (bytes)")
    for curr_path, curr_timestamp, curr_data in sorted(fs):
        if curr_data is None:
            curr_size = 'DIR'
        else:
            curr_size = len(curr_data)
        print("%s\t%s\t%s" % (curr_path, curr_timestamp, curr_size))
    if file_obj is not None:
        file_obj.close()
