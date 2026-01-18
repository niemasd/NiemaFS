#! /usr/bin/env python3
'''
List and optionally extract the contents of a given file system
'''

# imports
from pathlib import Path
from sys import stderr, stdout
import argparse
import niemafs

# constants
FORMAT_TO_CLASS = {
    'GCM': niemafs.GcmFS,
    'ISO': niemafs.IsoFS,
    'WII': niemafs.WiiFS,
    'ZIP': niemafs.ZipFS,
}

# print log message
def print_log(s='', end='\n', file=stdout):
    print(s, end=end, file=file); file.flush()

# print error message and exit
def error(s, end='\n', file=stderr, exitcode=1):
    print_log("ERROR: %s" % s, end=end, file=file); exit(exitcode)

# run tool
if __name__ == "__main__":
    # parse user args
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-i', '--input', required=True, type=str, help="Input File")
    parser.add_argument('-f', '--format', required=True, type=str, help="Input Format (options: %s)" % ', '.join(sorted(FORMAT_TO_CLASS.keys())))
    parser.add_argument('-o', '--output', required=False, type=str, default=None, help="Output Directory for Extraction")
    args = parser.parse_args()

    # check user args
    args.input = Path(args.input)
    if not args.input.is_file():
        error("Input file not found: %s" % args.input)
    args.format = args.format.strip().upper()
    if args.format not in FORMAT_TO_CLASS:
        error("Invalid input format (%s). Options: %s" % (args.format, ', '.join(sorted(FORMAT_TO_CLASS.keys()))))
    if args.output is not None:
        args.output = Path(args.output)
        if args.output.exists():
            error("Output directory exists: %s" % args.output)
        if not args.output.parent.is_dir():
            error("Output's parent directory does not exist: %s" % args.output.parent)

    # extract files
    print_log("Loading input file: %s" % args.input)
    with niemafs.open_file(args.input, 'rb') as input_file:
        fs = FORMAT_TO_CLASS[args.format](input_file)
        if args.output is not None:
            print_log("Extracting files to: %s" % args.output)
            args.output.mkdir()
        for file_num, file_tuple in enumerate(fs):
            curr_path, curr_timestamp, curr_data = file_tuple
            if args.output is None:
                if curr_data is None:
                    size_str = 'DIR'
                else:
                    size_str = '%d bytes' % len(curr_data)
                print_log("[%d] '%s' (%s) (%s)" % (file_num + 1, args.input / curr_path, curr_timestamp, size_str))
            else:
                out_path = args.output / curr_path
                if (len(out_path.name) > 2) and (out_path.name[-2] == ';') and (out_path.name[-1].isdigit()):
                    out_path = out_path.parent / out_path.name[:-2]
                print_log("[%d] Extracting '%s' (%s) to '%s'..." % (file_num + 1, args.input / curr_path, curr_timestamp, out_path))
                if curr_data is None: # directory
                    out_path.mkdir()
                else: # file
                    with niemafs.open_file(out_path, 'wb') as output_file:
                        output_file.write(curr_data)
