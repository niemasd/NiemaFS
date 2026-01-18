#! /usr/bin/env python3
'''
Extract the contents of a given file system
'''

# imports
from niemafs import IsoFS, open_file, ZipFS
from pathlib import Path
from sys import stdout
import argparse

# constants
FORMAT_TO_CLASS = {
    'ISO': IsoFS,
    'ZIP': ZipFS,
}

# run tool
if __name__ == "__main__":
    # parse user args
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-i', '--input', required=True, type=str, help="Input File")
    parser.add_argument('-f', '--format', required=True, type=str, help="Input Format (options: %s)" % ', '.join(sorted(FORMAT_TO_CLASS.keys())))
    parser.add_argument('-o', '--output', required=True, type=str, help="Output Directory")
    args = parser.parse_args()

    # check user args
    args.input = Path(args.input)
    if not args.input.is_file():
        print("ERROR: Input file not found: %s" % args.input); exit(1)
    args.format = args.format.strip().upper()
    if args.format not in FORMAT_TO_CLASS:
        print("ERROR: Invalid input format (%s). Options: %s" % (args.format, ', '.join(sorted(FORMAT_TO_CLASS.keys())))); exit(1)
    args.output = Path(args.output)
    if args.output.exists():
        print("ERROR: Output directory exists: %s" % args.output); exit(1)
    if not args.output.parent.is_dir():
        print("ERROR: Output's parent directory does not exist: %s" % args.output.parent); exit(1)

    # extract files
    print("Loading input file: %s" % args.input); stdout.flush()
    with open_file(args.input, 'rb') as input_file:
        fs = FORMAT_TO_CLASS[args.format](input_file)
        file_tuples = sorted(fs)
        print("Extracting %d files to: %s" % (len(file_tuples), args.output)); stdout.flush()
        args.output.mkdir()
        for file_num, file_tuple in enumerate(file_tuples):
            curr_path, curr_timestamp, curr_data = file_tuple
            out_path = args.output / curr_path
            if (len(out_path.name) > 2) and (out_path.name[-2] == ';') and (out_path.name[-1].isdigit()):
                out_path = out_path.parent / out_path.name[:-2]
            print("[%d/%d] Extracting '%s' to '%s'..." % (file_num + 1, len(file_tuples), args.input / curr_path, out_path)); stdout.flush()
            if curr_data is None: # directory
                out_path.mkdir()
            else: # file
                with open_file(out_path, 'wb') as output_file:
                    output_file.write(curr_data)
