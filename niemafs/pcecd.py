#! /usr/bin/env python
'''
Handle PC Engine CD / TurboGrafx-CD CUE/BIN images
'''

# NiemaFS imports
from niemafs.common import FileSystem, open_file, safename

# imports
from pathlib import Path
import re

# constants
PCECD_RAW_SECTOR_SIZE = 2352

class PceCdFS(FileSystem):
    '''Class to represent a PC Engine CD / TurboGrafx-CD CUE/BIN image as mixed-media tracks'''
    def __init__(self, file_obj=None, path=None):
        if path is None:
            raise ValueError("path must be a CUE file path")
        path = Path(path)
        if path.suffix.strip().lower() != '.cue':
            raise ValueError("PceCdFS requires a CUE file path")
        super().__init__(path=path, file_obj=file_obj)
        self.cue_path = path
        self.tracks = self.parse_cue(path)
        self.set_track_lengths()

    @staticmethod
    def cue_time_to_frames(t):
        parts = [int(p) for p in t.strip().split(':')]
        if len(parts) != 3:
            raise ValueError("Invalid CUE time: %s" % t)
        return ((parts[0] * 60) + parts[1]) * 75 + parts[2]

    @staticmethod
    def parse_cue(path):
        tracks = []
        current_file = None
        current_track = None
        quoted_file_re = re.compile(r'^FILE\s+"([^"]+)"\s+\S+', re.IGNORECASE)
        bare_file_re = re.compile(r'^FILE\s+(\S+)\s+\S+', re.IGNORECASE)
        with open_file(path, 'rt') as cue_file:
            for line in cue_file:
                s = line.strip()
                lower = s.lower()
                if lower.startswith('file '):
                    m = quoted_file_re.match(s)
                    if m is None:
                        m = bare_file_re.match(s)
                    if m is None:
                        raise ValueError("Unsupported CUE FILE line: %s" % s)
                    current_file = m.group(1)
                elif lower.startswith('track '):
                    parts = s.split()
                    if len(parts) < 3:
                        raise ValueError("Unsupported CUE TRACK line: %s" % s)
                    current_track = {
                        'number': int(parts[1]),
                        'mode': parts[2].upper().replace('/', '_'),
                        'file': current_file,
                        'index01': None,
                        'length': None,
                    }
                    tracks.append(current_track)
                elif current_track is not None and lower.startswith('index 01 '):
                    current_track['index01'] = PceCdFS.cue_time_to_frames(s.split()[-1])
        return tracks

    def set_track_lengths(self):
        files_to_sectors = {
            track['file']: (self.cue_path.parent / track['file']).stat().st_size // PCECD_RAW_SECTOR_SIZE
            for track in self.tracks
            if track['file'] is not None
        }
        for i, track in enumerate(self.tracks):
            if track['file'] is None or track['index01'] is None:
                track['length'] = 0
                continue
            next_start = files_to_sectors[track['file']]
            for next_track in self.tracks[i+1:]:
                if next_track['file'] == track['file'] and next_track['index01'] is not None:
                    next_start = next_track['index01']
                    break
                if next_track['file'] != track['file']:
                    break
            track['length'] = max(0, next_start - track['index01'])

    def read_track(self, track):
        if track['file'] is None or track['index01'] is None or track['length'] is None:
            return b''
        image_path = self.cue_path.parent / track['file']
        offset = track['index01'] * PCECD_RAW_SECTOR_SIZE
        length = track['length'] * PCECD_RAW_SECTOR_SIZE
        with open_file(image_path, 'rb') as image_file:
            image_file.seek(offset)
            return image_file.read(length)

    def __iter__(self):
        yield (Path('tracks'), None, None)
        for track in self.tracks:
            ext = 'bin' if track['mode'].startswith('MODE') else 'raw'
            name = 'track%s_%s.%s' % (str(track['number']).zfill(2), safename(track['mode']), ext)
            yield (Path('tracks') / name, None, self.read_track(track))
