#! /usr/bin/env python
'''
Handle SCG, SCW, and SCX containers (e.g. EA Lord of the Rings games)
'''

# NiemaFS imports
from niemafs.common import FileSystem, safename

# imports
from pathlib import Path
from struct import unpack
import re
import zlib

# constants
PAGE_SIZE = 0x10000
STREAM_TOP_LEVEL_TAGS = {'STOC', 'SWVR', 'FILL', 'CTRL', 'SHOC', 'SONO', 'PADD'}
RESOURCE_INNER_TAGS = {'SHDR', 'SDAT', 'Rdat'}
SUPPORTED_FORMATS = {'auto', 'scg', 'scw', 'scx'}
STOC_V2_VERSION = 2
STOC_V2_RECORDS_OFFSET = 0x38
STOC_V2_RECORD_SIZE = 0x20
STOC_V2_MAX_RECORDS = 1000000
STOC_V2_RESOURCE_TAGS = {'SHOC', 'SONO'}
STOC_V2_VARIANT = 'third-age-stoc-v2-swvr'
THIRD_AGE_STANDALONE_SAS_VARIANT = 'third-age-standalone-companion-sas'
THIRD_AGE_STREAM_RECORD_SIZE = 0x18
THIRD_AGE_STREAM_GROUP_COUNT_OFFSET = 0x38
THIRD_AGE_STREAM_GROUP_OFFSETS_OFFSET = 0x3C
THIRD_AGE_STREAM_GROUP_DATA_OFFSET = 0x40
THIRD_AGE_STREAM_GROUP_DATA_SIZE_OFFSET = 0x44
THIRD_AGE_STREAM_GROUP_END_OFFSET = 0x48
THIRD_AGE_STREAM_GROUP_COUNT_COPY_OFFSET = 0x7C
THIRD_AGE_SAMPLE_RATE_SCALE = 32000
FORMAT_LAYOUTS = {
    'scg': {
        'format_code': 'SCG',
        'family': 'stream',
        'endian': '>',
        'reverse_tags': False,
        'byte_order': 'big',
        'variant': 'SCG/GameCube stream-wrapper',
    },
    'scw': {
        'format_code': 'SCW',
        'family': 'stream',
        'endian': '<',
        'reverse_tags': True,
        'byte_order': 'little',
        'variant': 'SCW/PC stream-wrapper',
    },
    'scx': {
        'format_code': 'SCX',
        'family': 'flat',
        'endian': '<',
        'reverse_tags': True,
        'byte_order': 'little',
        'variant': 'SCX/Xbox flat-chunk container',
    },
}

def align_up(value, alignment):
    '''Round `value` up to the next multiple of `alignment`.

    Args:
        `value` (`int`): The value to round.

        `alignment` (`int`): The number to compare `value` against.

    Returns:
        `int`: The result of rounding `value` up to the next multiple of `alignment`.
    '''
    return (value + alignment - 1) // alignment * alignment

def printable_tag(tag):
    '''Return a readable representation of a possibly non-printable FourCC.

    Args:
        `tag` (`str`): A FourCC.

    Returns:
        `str`: A readable representation of `tag`.
    '''
    return ''.join(char if 32 <= ord(char) < 127 else '\\x%02x' % ord(char) for char in tag)

def is_printable_fourcc(raw):
    '''Check if a FourCC is printable.

    Args:
        `raw` (`str`): The FourCC to check.

    Returns:
        `bool`: `True` if `raw` is four printable non-NULL bytes, otherwise `False`.
    '''
    return len(raw) == 4 and all(32 <= byte < 127 for byte in raw)

class ScFS(FileSystem):
    '''Class to represent an SCG, SCW, or SCX container'''
    def __init__(self, file_obj, path=None, sc_format='auto', bulk_mode='file', raw_streams=False, split_blocks=False):
        # check args
        if file_obj is None:
            raise ValueError('file_obj must be a file-like object')
        if not isinstance(sc_format, str):
            raise TypeError('sc_format must be a string')
        sc_format = sc_format.lower()
        if sc_format not in SUPPORTED_FORMATS:
            raise ValueError("sc_format must be 'auto', 'scg', 'scw', or 'scx'")
        if bulk_mode not in ('file', 'pages', 'none'):
            raise ValueError("bulk_mode must be 'file', 'pages', or 'none'")
        if not isinstance(raw_streams, bool):
            raise TypeError('raw_streams must be a bool')
        if not isinstance(split_blocks, bool):
            raise TypeError('split_blocks must be a bool')

        # set things up
        super().__init__(path=path, file_obj=file_obj)
        self.sc_format = sc_format
        self.bulk_mode = bulk_mode
        self.raw_streams = raw_streams
        self.split_blocks = split_blocks
        self.file_size = self.get_file_size()
        layout = self.detect_layout(sc_format=sc_format)
        self.format_code = layout['format_code']
        self.family = layout['family']
        self.endian = layout['endian']
        self.reverse_tags = layout['reverse_tags']
        self.byte_order = layout['byte_order']
        self.variant = layout['variant']
        self.stoc_version = None
        if self.family == 'stream' and self.looks_like_stoc_v2(self.endian, self.reverse_tags):
            self.stoc_version = STOC_V2_VERSION
            self.variant = STOC_V2_VARIANT
        self.companion_bulk_path = None
        archive = self.parse_archive()
        self.toc_size = archive['toc_size']
        self.toc_entries = archive['toc_entries']
        self.streams = archive['streams']
        self.chunks = archive['chunks']
        self.bulk_offset = archive['bulk_offset']
        self.bulk_size = archive['bulk_size']
        self.companion_bulk_path = archive.get('companion_bulk_path')
        self.trailing_offset = archive['trailing_offset']
        self.trailing_size = archive['trailing_size']
        self.warnings = archive['warnings']

    def probe_u32(self, offset, endian):
        '''Read a u32 during layout detection, before self.endian is set.'''
        return unpack(endian + 'I', self.read_file(offset, 4))[0]

    def probe_tag(self, offset, reverse_tags):
        '''Read a normalized FourCC during layout detection.'''
        raw = self.read_file(offset, 4)
        if reverse_tags:
            raw = raw[::-1]
        return raw.decode('latin-1')

    def read_u32(self, offset):
        '''Read one unsigned 32-bit integer in the archive's byte order.'''
        return unpack(self.endian + 'I', self.read_file(offset, 4))[0]

    def read_raw_tag(self, offset):
        '''Read the four bytes making up a stored FourCC.'''
        return self.read_file(offset, 4)

    def read_tag(self, offset):
        '''Read and normalize a FourCC from any supported SC layout.'''
        raw = self.read_raw_tag(offset)
        if self.reverse_tags:
            raw = raw[::-1]
        return raw.decode('latin-1')

    def read_cstring(self, offset, limit=4096):
        '''Read a NUL-terminated UTF-8 string with a bounded maximum length.'''
        size = min(limit, self.file_size - offset)
        return self.read_file(offset, size).split(b'\x00', 1)[0].decode('utf-8', 'replace')

    def is_range_zero(self, offset, size):
        '''Return `True` when a range consists entirely of zero bytes.'''
        position = offset
        remaining = size
        while remaining:
            amount = min(1024 * 1024, remaining)
            if any(self.read_file(position, amount)):
                return False
            position += amount
            remaining -= amount
        return True

    def get_path_suffix(self):
        '''Return the lowercase suffix of the associated path, if available.'''
        if self.path is None:
            return ''
        try:
            return Path(self.path).suffix.lower()
        except (TypeError, ValueError):
            return ''

    def looks_like_stoc_v2(self, endian, reverse_tags, offset=0):
        '''Return `True` for the versioned STOC package catalog used by The Third Age.'''
        if endian != '>' or reverse_tags:
            return False
        if offset < 0 or self.file_size - offset < STOC_V2_RECORDS_OFFSET + STOC_V2_RECORD_SIZE:
            return False
        try:
            if self.probe_tag(offset, reverse_tags) != 'STOC':
                return False
            outer_size = self.probe_u32(offset + 4, endian)
            if outer_size < STOC_V2_RECORDS_OFFSET or outer_size > self.file_size - offset:
                return False
            inner = offset + 16
            if self.probe_tag(inner, reverse_tags) != 'STOC':
                return False
            version = self.probe_u32(inner + 4, endian)
            inner_size = self.probe_u32(inner + 8, endian)
            count_a = self.probe_u32(inner + 12, endian)
            count_b = self.probe_u32(inner + 28, endian)
            if version != STOC_V2_VERSION or inner_size < 40:
                return False
            if not 1 <= count_a <= STOC_V2_MAX_RECORDS or count_a != count_b:
                return False
            catalog_end = max(offset + outer_size, inner + inner_size)
            if catalog_end > self.file_size:
                return False
            records_offset = inner + 40
            records_end = records_offset + count_a * STOC_V2_RECORD_SIZE
            if records_end > catalog_end:
                return False
            package_offset = self.probe_u32(records_offset + 4, endian)
            package_size = self.probe_u32(records_offset + 8, endian)
            if package_size < 8 or package_offset < catalog_end:
                return False
            if package_offset + package_size > self.file_size:
                return False
            return self.probe_tag(package_offset, reverse_tags) == 'SWVR'
        except ValueError:
            return False

    def get_source_path(self):
        '''Return the source archive path when one is available.'''
        candidate = self.path
        if candidate is None:
            candidate = getattr(self.file_obj, 'name', None)
            if isinstance(candidate, str) and candidate.startswith('<'):
                return None
        if candidate is None:
            return None
        try:
            return Path(candidate)
        except (TypeError, ValueError):
            return None

    def find_companion_sas(self):
        '''Return a same-stem `.sas` companion path when one exists.'''
        source_path = self.get_source_path()
        if source_path is None:
            return None

        for suffix in ('.sas', '.SAS'):
            candidate = source_path.with_suffix(suffix)
            try:
                if candidate.is_file():
                    return candidate
            except OSError:
                pass

        try:
            siblings = source_path.parent.iterdir()
        except OSError:
            return None
        wanted_stem = source_path.stem.lower()
        for candidate in siblings:
            try:
                if candidate.is_file() and candidate.stem.lower() == wanted_stem and candidate.suffix.lower() == '.sas':
                    return candidate
            except OSError:
                continue
        return None

    def looks_like_third_age_grouped_stream_shdr(self, data):
        '''Return whether *data* is a validated Third Age grouped stream catalog.

        Chapter SCGs put this catalog in a STOC-v2 package.  ``globscen.scg``
        stores the same style of catalog in a standalone stream wrapper, so the
        container shape alone is not enough to decide whether an adjacent SAS
        belongs to the archive.
        '''
        if self.endian != '>' or len(data) < THIRD_AGE_STREAM_GROUP_COUNT_COPY_OFFSET + 4:
            return False
        try:
            group_count = unpack('>I', data[THIRD_AGE_STREAM_GROUP_COUNT_OFFSET:THIRD_AGE_STREAM_GROUP_COUNT_OFFSET + 4])[0]
            offsets_offset = unpack('>I', data[THIRD_AGE_STREAM_GROUP_OFFSETS_OFFSET:THIRD_AGE_STREAM_GROUP_OFFSETS_OFFSET + 4])[0]
            group_data_offset = unpack('>I', data[THIRD_AGE_STREAM_GROUP_DATA_OFFSET:THIRD_AGE_STREAM_GROUP_DATA_OFFSET + 4])[0]
            group_data_size = unpack('>I', data[THIRD_AGE_STREAM_GROUP_DATA_SIZE_OFFSET:THIRD_AGE_STREAM_GROUP_DATA_SIZE_OFFSET + 4])[0]
            group_end_offset = unpack('>I', data[THIRD_AGE_STREAM_GROUP_END_OFFSET:THIRD_AGE_STREAM_GROUP_END_OFFSET + 4])[0]
            group_count_copy = unpack('>I', data[THIRD_AGE_STREAM_GROUP_COUNT_COPY_OFFSET:THIRD_AGE_STREAM_GROUP_COUNT_COPY_OFFSET + 4])[0]
        except (ValueError, IndexError):
            return False

        if not 1 <= group_count <= 0x1000 or group_count_copy != group_count:
            return False
        offsets_size = group_count * 4
        if not 0 <= offsets_offset <= len(data) - offsets_size:
            return False
        if group_data_offset != offsets_offset + offsets_size:
            return False
        if group_end_offset != group_data_offset + group_data_size:
            return False
        if not group_data_offset <= group_end_offset <= len(data):
            return False

        try:
            relative_offsets = unpack('>' + ('I' * group_count), data[offsets_offset:offsets_offset + offsets_size])
        except (ValueError, IndexError):
            return False
        if not relative_offsets or relative_offsets[0] != 0:
            return False
        if any(next_offset <= offset for offset, next_offset in zip(relative_offsets, relative_offsets[1:])):
            return False
        if relative_offsets[-1] >= group_data_size:
            return False

        meaningful_records = 0
        for group_index, relative_offset in enumerate(relative_offsets):
            start = group_data_offset + relative_offset
            next_relative = relative_offsets[group_index + 1] if group_index + 1 < group_count else group_data_size
            limit = group_data_offset + next_relative
            if start + 4 > limit:
                return False
            record_count, _record_type = unpack('>HH', data[start:start + 4])
            if 4 + record_count * THIRD_AGE_STREAM_RECORD_SIZE != limit - start:
                return False
            for record_index in range(record_count):
                position = start + 4 + record_index * THIRD_AGE_STREAM_RECORD_SIZE
                fixed_rate, _unknown_04, bulk_offset, stored_size = unpack('>4I', data[position:position + 16])
                final_padding, block_count, _flags = unpack('>3H', data[position + 16:position + 22])
                channels = data[position + 22]
                if stored_size == 0:
                    if not (fixed_rate == 0 and bulk_offset == 0xFFFFFFFF and block_count == 0 and channels == 0):
                        return False
                    continue
                sample_rate = (fixed_rate * THIRD_AGE_SAMPLE_RATE_SCALE + 0x8000) // 0x10000
                if not 1000 <= sample_rate <= 384000:
                    return False
                if not 1 <= channels <= 8 or block_count == 0 or not 0 <= final_padding < 0x8000:
                    return False
                final_block_size = 0x8000 - final_padding
                if final_block_size < 0x100:
                    return False
                expected_size = channels * ((block_count - 1) * 0x8000 + final_block_size)
                if stored_size != expected_size:
                    return False
                meaningful_records += 1

        return meaningful_records > 0

    def has_third_age_grouped_stream_catalog(self, streams):
        '''Return whether any parsed SHDR resource contains that catalog.'''
        for stream in streams:
            for resource in stream.get('resources', ()): 
                if str(resource.get('type_code', '')).lower() != 'shdr':
                    continue
                try:
                    data = self.get_resource_data(resource)
                except (OSError, ValueError, zlib.error):
                    continue
                if self.looks_like_third_age_grouped_stream_shdr(data):
                    return True
        return False

    def looks_like_nested_stoc(self, endian, reverse_tags, offset=0):
        '''Return `True` when *offset* starts a supported nested STOC directory.'''
        if self.looks_like_stoc_v2(endian, reverse_tags, offset=offset):
            return True
        if offset < 0 or self.file_size - offset < 48:
            return False
        try:
            if self.probe_tag(offset, reverse_tags) != 'STOC':
                return False
            outer_size = self.probe_u32(offset + 4, endian)
            if outer_size < 16 or outer_size > self.file_size - offset:
                return False
            inner = offset + 16
            if inner + 32 > offset + outer_size:
                return False
            if self.probe_tag(inner, reverse_tags) != 'STOC':
                return False
            inner_size = self.probe_u32(inner + 4, endian)
            if inner_size < 32 or inner + inner_size > offset + outer_size:
                return False
            count_a = self.probe_u32(inner + 8, endian)
            count_b = self.probe_u32(inner + 24, endian)
            if count_a != count_b or count_a > 100000:
                return False
            records_end = inner + 28 + count_a * 16
            return records_end <= inner + inner_size
        except ValueError:
            return False

    def looks_like_stream_wrapper(self, endian, reverse_tags):
        '''Probe for structural evidence of the SCG/SCW resource layout.'''
        if self.file_size < 8:
            return False
        if self.looks_like_nested_stoc(endian, reverse_tags):
            return True
        position = 0
        scanned = 0
        scan_limit = min(self.file_size, 4 * 1024 * 1024)
        while position + 8 <= scan_limit and scanned < 256:
            try:
                tag = self.probe_tag(position, reverse_tags)
            except ValueError:
                return False
            if tag == 'FILL':
                try:
                    declared = self.probe_u32(position + 4, endian)
                except ValueError:
                    return False
                declared_end = position + declared
                aligned_end = align_up(position + 4, PAGE_SIZE)
                if declared >= 8 and declared_end <= self.file_size:
                    next_position = declared_end
                else:
                    next_position = min(aligned_end, self.file_size)
                if next_position <= position:
                    return False
                position = next_position
                scanned += 1
                continue
            try:
                total_size = self.probe_u32(position + 4, endian)
            except ValueError:
                return False
            if total_size < 8 or total_size > self.file_size - position:
                return False
            if total_size >= 20:
                try:
                    inner = self.probe_tag(position + 16, reverse_tags)
                except ValueError:
                    return False
                if tag == 'SWVR' and inner == 'FILE':
                    return True
                if tag in ('SHOC', 'SONO') and inner in RESOURCE_INNER_TAGS:
                    return True
            position += total_size
            scanned += 1
        return False

    def looks_like_flat_chunks(self, endian='<', reverse_tags=True):
        '''Probe for the SCX flat `tag + size + payload` chunk sequence.'''
        if self.file_size < 8:
            return False
        position = 0
        count = 0
        while position < self.file_size and count < 256:
            remaining = self.file_size - position
            if remaining < 8:
                try:
                    return count > 0 and self.is_range_zero(position, remaining)
                except ValueError:
                    return False
            try:
                raw = self.read_file(position, 4)
                normalized = raw[::-1] if reverse_tags else raw
                total_size = self.probe_u32(position + 4, endian)
            except ValueError:
                return False
            if not is_printable_fourcc(normalized):
                try: # completely zero tail is permitted after the last chunk
                    return count > 0 and self.is_range_zero(position, remaining)
                except ValueError:
                    return False
            if total_size < 8 or total_size > remaining:
                return False
            position += total_size
            count += 1
        return count > 0 and (position == self.file_size or count >= 3)

    def is_layout_plausible(self, code):
        '''Return `True` when a candidate format agrees with the file bytes.'''
        if self.file_size < 8:
            return False
        layout = FORMAT_LAYOUTS[code]
        endian = layout['endian']
        reverse_tags = layout['reverse_tags']
        if code in ('scg', 'scw'):
            return self.looks_like_stream_wrapper(endian, reverse_tags)
        return self.looks_like_flat_chunks(endian, reverse_tags)

    def detect_layout(self, sc_format='auto'):
        '''Detect the SC format, integer endianness, and FourCC order.

        Args:
            sc_format (str): `'auto'`, `'scg'`, `'scw'`, or `'scx'`.

        Returns:
            dict: Layout metadata including `format_code`, `family`, `endian`, `reverse_tags`, `byte_order`, and `variant`.
        '''
        if self.file_size < 8:
            raise ValueError('file is too small to contain an SC header')
        if sc_format != 'auto':
            if not self.is_layout_plausible(sc_format):
                raise ValueError('file does not match the requested %s layout' % sc_format.upper())
            return dict(FORMAT_LAYOUTS[sc_format])
        suffix_to_code = {'.scg': 'scg', '.scw': 'scw', '.scx': 'scx'}
        suffix_code = suffix_to_code.get(self.get_path_suffix())
        if suffix_code and self.is_layout_plausible(suffix_code):
            return dict(FORMAT_LAYOUTS[suffix_code])
        raw = self.read_file(0, 4)
        normal = raw.decode('latin-1')
        reversed_tag = raw[::-1].decode('latin-1')

        # normal known wrapper tags strongly indicate the big-endian SCG representation
        # reversed wrapper tags require a structural probe to distinguish nested SCW from flat SCX
        if normal in STREAM_TOP_LEVEL_TAGS and self.is_layout_plausible('scg'):
            return dict(FORMAT_LAYOUTS['scg'])
        if reversed_tag in STREAM_TOP_LEVEL_TAGS:
            if self.is_layout_plausible('scw'):
                return dict(FORMAT_LAYOUTS['scw'])
            if self.is_layout_plausible('scx'):
                return dict(FORMAT_LAYOUTS['scx'])

        # fall back to structural probes so pathless SCX files whose first chunk has an arbitrary resource FourCC can still be recognized
        for code in ('scg', 'scw', 'scx'):
            if self.is_layout_plausible(code):
                return dict(FORMAT_LAYOUTS[code])
        raise ValueError('unrecognized SC container: initial bytes %r do not match a supported SCG, SCW, or SCX layout' % raw)

    def get_toc(self):
        '''Return the raw outer `STOC` chunk, if this archive has one.'''
        if not self.toc_size:
            return None
        return self.read_file(0, self.toc_size)

    def parse_stoc_v2_toc(self):
        '''Parse a version-2 STOC catalog into package entries.'''
        outer_size = self.read_u32(4)
        if outer_size < STOC_V2_RECORDS_OFFSET or outer_size > self.file_size:
            raise ValueError('invalid outer STOC-v2 size 0x%X' % outer_size)
        inner_offset = 16
        if self.read_tag(inner_offset) != 'STOC':
            raise ValueError('outer STOC-v2 does not contain the expected nested STOC at +0x10')

        version = self.read_u32(inner_offset + 4)
        inner_size = self.read_u32(inner_offset + 8)
        count_a = self.read_u32(inner_offset + 12)
        count_b = self.read_u32(inner_offset + 28)
        if version != STOC_V2_VERSION:
            raise ValueError('unsupported nested STOC version 0x%X' % version)
        if inner_size < 40:
            raise ValueError('invalid nested STOC-v2 size 0x%X' % inner_size)
        if count_a != count_b:
            raise ValueError('STOC-v2 entry counts disagree (%d vs %d)' % (count_a, count_b))
        if not 1 <= count_a <= STOC_V2_MAX_RECORDS:
            raise ValueError('implausible STOC-v2 entry count %d' % count_a)

        catalog_limit = max(outer_size, inner_offset + inner_size)
        if catalog_limit > self.file_size:
            raise ValueError('STOC-v2 catalog extends beyond the archive')
        records_offset = inner_offset + 40
        records_size = count_a * STOC_V2_RECORD_SIZE
        if records_offset + records_size > catalog_limit:
            raise ValueError('STOC-v2 entry table extends beyond the nested catalog')

        catalog = self.read_file(0, catalog_limit)
        entries = list()
        occupied = list()
        for index in range(count_a):
            position = records_offset + index * STOC_V2_RECORD_SIZE
            (
                name_offset,
                package_offset,
                allocated_size,
                category,
                declared_resource_count,
                logical_size,
                field_18,
                field_1c,
            ) = unpack(self.endian + '8I', catalog[position:position + STOC_V2_RECORD_SIZE])

            if not 0 <= name_offset < catalog_limit:
                raise ValueError('STOC-v2 entry %d has invalid name offset 0x%X' % (index, name_offset))
            name_end = catalog.find(b'\x00', name_offset, catalog_limit)
            if name_end < 0:
                raise ValueError('STOC-v2 entry %d has an unterminated name' % index)
            name = catalog[name_offset:name_end].decode('utf-8', 'replace')

            package_end = package_offset + allocated_size
            if allocated_size < 8 or package_offset < catalog_limit or package_end > self.file_size:
                raise ValueError('STOC-v2 package %r has invalid range 0x%X..0x%X' % (name, package_offset, package_end))
            if self.read_tag(package_offset) != 'SWVR':
                raise ValueError('STOC-v2 package %r does not begin with SWVR' % name)

            entries.append({
                'layout': 'stoc-v2',
                'index': index,
                'name_offset': name_offset,
                'resolved_name_offset': name_offset,
                'offset': package_offset,
                'length': allocated_size,
                'end': package_end,
                'flags': category,
                'category': category,
                'declared_resource_count': declared_resource_count,
                'logical_size': logical_size,
                'field_18': field_18,
                'field_1c': field_1c,
                'name': name,
            })
            occupied.append((package_offset, package_end, name))

        occupied.sort()
        for previous, current in zip(occupied, occupied[1:]):
            if current[0] < previous[1]:
                raise ValueError('STOC-v2 packages %r and %r overlap' % (previous[2], current[2]))
        return catalog_limit, entries

    def parse_toc(self):
        '''Parse the nested top-level `STOC` directory used by SCG/SCW.

        Returns:
            `tuple`: `(outer_size, entries)`. Each entry is a dict containing its name, source offset, length, flags, and original table index. A standalone wrapper or SCX archive returns `(0, list())`.
        '''
        if self.family != 'stream' or self.read_tag(0) != 'STOC':
            return 0, list()
        if self.stoc_version == STOC_V2_VERSION:
            return self.parse_stoc_v2_toc()
        outer_size = self.read_u32(4)
        if outer_size < 16 or outer_size > self.file_size:
            raise ValueError('invalid outer STOC size 0x%X' % outer_size)
        inner_offset = 16
        if self.read_tag(inner_offset) != 'STOC':
            raise ValueError('outer STOC does not contain the expected nested STOC at +0x10')
        inner_size = self.read_u32(inner_offset + 4)
        if inner_size < 32 or inner_offset + inner_size > outer_size:
            raise ValueError('invalid nested STOC size 0x%X' % inner_size)
        count_a = self.read_u32(inner_offset + 8)
        count_b = self.read_u32(inner_offset + 24)
        if count_a != count_b:
            raise ValueError('STOC entry counts disagree (%d vs %d)' % (count_a, count_b))
        if count_a > 100000:
            raise ValueError('implausible STOC entry count %d' % count_a)
        records_offset = inner_offset + 28
        records_size = count_a * 16
        if records_offset + records_size > inner_offset + inner_size:
            raise ValueError('STOC entry table extends beyond the nested STOC')
        entries = list()
        for index in range(count_a):
            position = records_offset + index * 16
            name_offset = self.read_u32(position)
            stream_offset = self.read_u32(position + 4)
            stream_length = self.read_u32(position + 8)
            flags = self.read_u32(position + 12)

            # known files use absolute string offsets
            # relative fallback makes the parser tolerant of related builds using inner-relative offsets instead
            resolved_name_offset = name_offset
            if not 0 <= resolved_name_offset < self.file_size:
                candidate = inner_offset + name_offset
                if 0 <= candidate < self.file_size:
                    resolved_name_offset = candidate
                else:
                    raise ValueError('STOC entry %d has invalid name offset 0x%X' % (index, name_offset))
            name = self.read_cstring(resolved_name_offset)
            entries.append({
                'index': index,
                'name_offset': name_offset,
                'resolved_name_offset': resolved_name_offset,
                'offset': stream_offset,
                'length': stream_length,
                'end': stream_offset + stream_length,
                'flags': flags,
                'name': name,
            })
        return outer_size, entries

    def parse_swvr_name(self, position, total_size):
        '''Return the optional name stored inside an `SWVR/FILE` chunk.'''
        if total_size < 20 or self.read_tag(position + 16) != 'FILE':
            return ''
        return self.read_file(position + 20, total_size - 20).split(b'\x00', 1)[0].decode('utf-8', 'replace')

    def finish_resource(self, current, resources):
        '''Finalize derived fields and append one resource metadata dict.'''
        if current is None:
            return None
        current['index'] = len(resources)
        current['stored_size'] = sum(block['stored_size'] for block in current['blocks'])
        current['block_expanded_size'] = sum(block['expanded_size'] for block in current['blocks'])
        current['expanded_alignment_slack'] = current['block_expanded_size'] - current['declared_expanded_size']
        current['contains_rdat'] = any(block['kind'] == 'Rdat' for block in current['blocks'])
        current['all_sdat'] = bool(current['blocks']) and all(block['kind'] == 'SDAT' for block in current['blocks'])
        resources.append(current)
        return None

    def finish_stoc_v2_resource(self, current, resources, package_name):
        '''Finalize one STOC-v2 logical resource and append its metadata.'''
        if current is None:
            return None
        if not current['blocks']:
            raise ValueError(
                'resource %s id 0x%X in package %r has no data chunks'
                % (printable_tag(current['type_code']), current['resource_id'], package_name)
            )

        current['index'] = len(resources)
        current['stored_size'] = sum(block['stored_size'] for block in current['blocks'])
        if current['storage_mode'] == 'raw':
            current['block_expanded_size'] = current['stored_size']
            current['expanded_alignment_slack'] = current['stored_size'] - current['declared_expanded_size']
            if current['stored_size'] != current['declared_expanded_size']:
                raise ValueError(
                    'raw resource %s id 0x%X in package %r stores 0x%X bytes, expected 0x%X'
                    % (
                        printable_tag(current['type_code']),
                        current['resource_id'],
                        package_name,
                        current['stored_size'],
                        current['declared_expanded_size'],
                    )
                )
        elif current['storage_mode'] == 'zlib':
            current['block_expanded_size'] = current['declared_expanded_size']
            current['expanded_alignment_slack'] = 0
        else:
            raise ValueError(
                'resource %s id 0x%X in package %r has unsupported storage mode %r'
                % (printable_tag(current['type_code']), current['resource_id'], package_name, current['storage_mode'])
            )
        current['contains_rdat'] = False
        current['all_sdat'] = current['storage_mode'] == 'raw'
        resources.append(current)
        return None

    def parse_stoc_v2_stream(self, entry, stream_index):
        '''Parse one STOC-v2 SWVR package into logical resource metadata.'''
        start = entry['offset']
        end = entry['end']
        position = start
        wrapper_name = ''
        current = None
        resources = list()
        counts = dict()
        warnings = list()

        while position < end:
            if end - position < 4:
                raise ValueError('truncated STOC-v2 chunk tag at 0x%X' % position)
            tag = self.read_tag(position)
            counts[tag] = counts.get(tag, 0) + 1

            # Most STOC-v2 FILL chunks use the normal ``tag + size`` form.
            # Some Third Age archives instead place only the four-byte FILL
            # sentinel at the end of a 64 KiB page; the following chunk starts
            # exactly at the next page boundary.
            if tag == 'FILL':
                declared = self.read_u32(position + 4) if end - position >= 8 else 0
                declared_end = position + declared
                aligned_end = align_up(position + 4, PAGE_SIZE)
                if declared >= 8 and declared_end <= end:
                    next_position = declared_end
                elif position < aligned_end <= end:
                    if aligned_end < end:
                        next_tag = self.read_tag(aligned_end)
                        if next_tag not in STREAM_TOP_LEVEL_TAGS:
                            raise ValueError(
                                'marker-only FILL at 0x%X in STOC-v2 package %r '
                                'aligns to unknown chunk %r at 0x%X'
                                % (position, entry['name'], printable_tag(next_tag), aligned_end)
                            )
                    next_position = aligned_end
                else:
                    raise ValueError(
                        'invalid FILL chunk size 0x%X at 0x%X in STOC-v2 package %r'
                        % (declared, position, entry['name'])
                    )
                if next_position <= position:
                    raise ValueError(
                        'FILL chunk at 0x%X does not advance in STOC-v2 package %r'
                        % (position, entry['name'])
                    )
                position = next_position
                continue

            if end - position < 8:
                raise ValueError('truncated STOC-v2 chunk header at 0x%X' % position)
            total_size = self.read_u32(position + 4)
            if total_size < 8 or total_size > end - position:
                raise ValueError(
                    'invalid %r chunk size 0x%X at 0x%X in STOC-v2 package %r'
                    % (printable_tag(tag), total_size, position, entry['name'])
                )
            chunk_end = position + total_size

            if tag == 'SWVR':
                parsed_name = self.parse_swvr_name(position, total_size)
                if parsed_name:
                    wrapper_name = parsed_name
            elif tag in STOC_V2_RESOURCE_TAGS:
                if total_size < 20:
                    raise ValueError('short %s chunk at 0x%X in STOC-v2 package %r' % (tag, position, entry['name']))
                body_prefix = self.read_file(position + 16, min(8, total_size - 16))
                inner = body_prefix[:4].decode('latin-1')

                if inner == 'SHDR':
                    current = self.finish_stoc_v2_resource(current, resources, entry['name'])
                    if total_size < 36:
                        raise ValueError('short SHDR chunk at 0x%X in STOC-v2 package %r' % (position, entry['name']))
                    current = {
                        'layout': 'stoc-v2',
                        'index': -1,
                        'header_offset': position,
                        'header_chunk_size': total_size,
                        'outer_type': tag,
                        'storage_class': self.read_u32(position + 20),
                        'type_code': self.read_tag(position + 24),
                        'resource_id': self.read_u32(position + 28),
                        'declared_expanded_size': self.read_u32(position + 32),
                        'header_extra': self.read_file(position + 36, total_size - 36),
                        'storage_mode': None,
                        'blocks': list(),
                    }
                elif body_prefix == b'SDATSHDR':
                    if current is None:
                        raise ValueError('orphan SDATSHDR chunk at 0x%X in STOC-v2 package %r' % (position, entry['name']))
                    if current['storage_mode'] not in (None, 'raw'):
                        raise ValueError('resource %s id 0x%X in package %r mixes raw and compressed data' % (printable_tag(current['type_code']), current['resource_id'], entry['name']))
                    data_offset = position + 64
                    if data_offset > chunk_end:
                        raise ValueError('short SDATSHDR chunk at 0x%X in STOC-v2 package %r' % (position, entry['name']))
                    stored_size = chunk_end - data_offset
                    current['storage_mode'] = 'raw'
                    current['blocks'].append({
                        'index': len(current['blocks']),
                        'outer_type': tag,
                        'kind': 'SDATSHDR',
                        'chunk_offset': position,
                        'chunk_size': total_size,
                        'data_offset': data_offset,
                        'stored_size': stored_size,
                        'expanded_size': stored_size,
                    })
                elif inner == 'Ldat':
                    if current is None:
                        raise ValueError('orphan Ldat chunk at 0x%X in STOC-v2 package %r' % (position, entry['name']))
                    if current['storage_mode'] not in (None, 'zlib'):
                        raise ValueError('resource %s id 0x%X in package %r mixes raw and compressed data' % (printable_tag(current['type_code']), current['resource_id'], entry['name']))
                    if total_size < 24:
                        raise ValueError('short Ldat chunk at 0x%X in STOC-v2 package %r' % (position, entry['name']))
                    compressed_size = self.read_u32(position + 20)
                    data_offset = position + 24
                    if compressed_size > chunk_end - data_offset:
                        raise ValueError(
                            'Ldat chunk at 0x%X in STOC-v2 package %r declares 0x%X compressed bytes, only 0x%X available'
                            % (position, entry['name'], compressed_size, chunk_end - data_offset)
                        )
                    current['storage_mode'] = 'zlib'
                    current['blocks'].append({
                        'index': len(current['blocks']),
                        'outer_type': tag,
                        'kind': 'Ldat',
                        'chunk_offset': position,
                        'chunk_size': total_size,
                        'data_offset': data_offset,
                        'stored_size': compressed_size,
                        'expanded_size': 0,
                    })
                else:
                    raise ValueError(
                        'unknown %s resource body %r at 0x%X in STOC-v2 package %r'
                        % (tag, body_prefix, position, entry['name'])
                    )
            position = chunk_end

        current = self.finish_stoc_v2_resource(current, resources, entry['name'])
        if position != end:
            raise ValueError('STOC-v2 package %r ends at 0x%X, expected 0x%X' % (entry['name'], position, end))
        if len(resources) != entry['declared_resource_count']:
            raise ValueError(
                'STOC-v2 package %r contains %d resources, catalog declares %d'
                % (entry['name'], len(resources), entry['declared_resource_count'])
            )

        return {
            'layout': 'stoc-v2',
            'index': stream_index,
            'toc_index': entry['index'],
            'toc_name': entry['name'],
            'wrapper_name': wrapper_name,
            'offset': entry['offset'],
            'length': entry['length'],
            'end': entry['end'],
            'flags': entry['flags'],
            'category': entry['category'],
            'declared_resource_count': entry['declared_resource_count'],
            'logical_size': entry['logical_size'],
            'field_18': entry['field_18'],
            'field_1c': entry['field_1c'],
            'chunk_counts': dict(sorted(counts.items())),
            'resources': resources,
            'warnings': warnings,
        }

    def parse_stream(self, entry, stream_index):
        '''Parse one SCG/SCW indexed stream into resource metadata.'''
        if self.family != 'stream':
            raise ValueError('SCX flat archives do not contain SWVR streams')
        if entry.get('layout') == 'stoc-v2':
            return self.parse_stoc_v2_stream(entry, stream_index)
        start = entry['offset']
        end = entry['end']
        position = start
        wrapper_name = ''
        current = None
        resources = list()
        counts = dict()
        warnings = list()
        while position < end:
            if end - position < 4:
                tail = self.read_file(position, end - position)
                if any(tail):
                    warnings.append('non-zero %d-byte stream tail at 0x%X' % (len(tail), position))
                break
            tag = self.read_tag(position)
            if tag not in counts:
                counts[tag] = 0
            counts[tag] += 1
            if tag == 'FILL':
                declared = self.read_u32(position + 4) if end - position >= 8 else 0
                declared_end = position + declared
                aligned_end = align_up(position + 4, PAGE_SIZE)
                if declared >= 8 and declared_end <= end:
                    next_position = declared_end
                else:
                    next_position = min(aligned_end, end)
                if next_position <= position:
                    raise ValueError(
                        'FILL chunk at 0x%X does not advance' % position
                    )
                position = next_position
                continue
            if end - position < 8:
                raise ValueError('truncated chunk header at 0x%X' % position)
            total_size = self.read_u32(position + 4)
            if total_size == 0:
                if self.is_range_zero(position, end - position):
                    warnings.append('zero-filled remainder begins at 0x%X' % position)
                    break
                raise ValueError('zero-sized non-zero chunk at 0x%X' % position)
            if total_size < 8 or total_size > end - position:
                raise ValueError('invalid %r chunk size 0x%X at 0x%X (stream ends at 0x%X)' % (printable_tag(tag), total_size, position, end))
            chunk_end = position + total_size
            if tag == 'SWVR':
                parsed_name = self.parse_swvr_name(position, total_size)
                if parsed_name:
                    wrapper_name = parsed_name
            elif tag in ('SHOC', 'SONO'):
                if total_size < 20:
                    warnings.append('short %s chunk at 0x%X' % (tag, position))
                else:
                    inner = self.read_tag(position + 16)
                    if inner == 'SHDR':
                        current = self.finish_resource(current, resources)
                        if total_size < 36:
                            raise ValueError('short SHDR chunk at 0x%X' % position)
                        current = {
                            'index': -1,
                            'header_offset': position,
                            'header_chunk_size': total_size,
                            'outer_type': tag,
                            'storage_class': self.read_u32(position + 20),
                            'type_code': self.read_tag(position + 24),
                            'resource_id': self.read_u32(position + 28),
                            'declared_expanded_size': self.read_u32(position + 32),
                            'header_extra': self.read_file(position + 36, total_size - 36),
                            'blocks': list(),
                        }
                    elif inner == 'SDAT':
                        data_offset = position + 64
                        if data_offset > chunk_end:
                            raise ValueError('short SDAT chunk at 0x%X' % position)
                        if current is None:
                            warnings.append('orphan SDAT chunk at 0x%X' % position)
                        else:
                            stored_size = chunk_end - data_offset
                            current['blocks'].append({
                                'index': len(current['blocks']),
                                'outer_type': tag,
                                'kind': inner,
                                'chunk_offset': position,
                                'chunk_size': total_size,
                                'data_offset': data_offset,
                                'stored_size': stored_size,
                                'expanded_size': stored_size,
                            })
                    elif inner == 'Rdat':
                        data_offset = position + 68
                        if data_offset > chunk_end:
                            raise ValueError('short Rdat chunk at 0x%X' % position)
                        if current is None:
                            warnings.append('orphan Rdat chunk at 0x%X' % position)
                        else:
                            current['blocks'].append({
                                'index': len(current['blocks']),
                                'outer_type': tag,
                                'kind': inner,
                                'chunk_offset': position,
                                'chunk_size': total_size,
                                'data_offset': data_offset,
                                'stored_size': chunk_end - data_offset,
                                'expanded_size': self.read_u32(position + 64),
                            })
                    else:
                        key = '%s/%s' % (tag, printable_tag(inner))
                        counts[key] = counts.get(key, 0) + 1
            position = chunk_end
        self.finish_resource(current, resources)
        return {
            'index': stream_index,
            'toc_index': entry['index'],
            'toc_name': entry['name'],
            'wrapper_name': wrapper_name,
            'offset': entry['offset'],
            'length': entry['length'],
            'end': entry['end'],
            'flags': entry['flags'],
            'chunk_counts': dict(sorted(counts.items())),
            'resources': resources,
            'warnings': warnings,
        }

    def parse_stream_archive(self):
        '''Parse all SCG/SCW stream-wrapper metadata.'''
        warnings = list()
        toc_size, toc_entries = self.parse_toc()
        if toc_entries:
            nonempty_entries = [entry for entry in toc_entries if entry['length']]
        else:
            if self.path is None:
                name = 'stream'
            else:
                name = Path(self.path).stem or 'stream'
            nonempty_entries = [{
                'index': 0,
                'name_offset': 0,
                'resolved_name_offset': 0,
                'offset': 0,
                'length': self.file_size,
                'end': self.file_size,
                'flags': 0,
                'name': name,
            }]
            warnings.append('no STOC directory found; parsed the entire file as one stream')
        streams = [self.parse_stream(entry, stream_index) for stream_index, entry in enumerate(nonempty_entries)]
        indexed_end = max([entry['end'] for entry in nonempty_entries] or [toc_size])
        indexed_end = max(indexed_end, toc_size)

        companion_bulk_path = None
        standalone_third_age_catalog = (
            self.stoc_version is None
            and indexed_end == self.file_size
            and self.has_third_age_grouped_stream_catalog(streams)
        )
        uses_companion_sas = (
            self.stoc_version == STOC_V2_VERSION
            or standalone_third_age_catalog
        )
        if standalone_third_age_catalog:
            self.variant = THIRD_AGE_STANDALONE_SAS_VARIANT

        if uses_companion_sas:
            companion_bulk_path = self.find_companion_sas()
            if companion_bulk_path is None:
                bulk_offset = None
                bulk_size = 0
                if self.bulk_mode != 'none':
                    warnings.append('no same-stem .sas companion file was found')
            else:
                try:
                    bulk_size = companion_bulk_path.stat().st_size
                except OSError as error:
                    raise ValueError('unable to stat companion SAS %s: %s' % (companion_bulk_path, error))
                bulk_offset = None
            trailing_offset = min(indexed_end, self.file_size)
            trailing_size = self.file_size - trailing_offset
        else:
            bulk_offset = min(indexed_end, self.file_size)
            bulk_size = self.file_size - bulk_offset
            trailing_offset = self.file_size
            trailing_size = 0

        return {
            'toc_size': toc_size,
            'toc_entries': toc_entries,
            'streams': streams,
            'chunks': list(),
            'bulk_offset': bulk_offset,
            'bulk_size': bulk_size,
            'companion_bulk_path': companion_bulk_path,
            'trailing_offset': trailing_offset,
            'trailing_size': trailing_size,
            'warnings': warnings,
        }

    def parse_chunks(self):
        '''Parse the flat chunk sequence used by SCX.

        Returns:
            tuple: `(chunks, trailing_offset, trailing_size, warnings)`.
            Chunk offsets and lengths refer to the original archive.
        '''
        if self.family != 'flat':
            raise ValueError('SCG/SCW stream archives are not flat SCX chunks')
        chunks = list()
        warnings = list()
        position = 0
        trailing_offset = self.file_size
        trailing_size = 0
        while position < self.file_size:
            remaining = self.file_size - position
            if remaining < 8:
                if self.is_range_zero(position, remaining):
                    trailing_offset = position
                    trailing_size = remaining
                    if remaining:
                        warnings.append('zero-filled %d-byte trailer begins at 0x%X' % (remaining, position))
                    break
                raise ValueError('truncated SCX chunk header at 0x%X' % position)
            raw_tag = self.read_raw_tag(position)
            tag = self.read_tag(position)
            if not is_printable_fourcc(tag.encode('latin-1')):
                if self.is_range_zero(position, remaining):
                    trailing_offset = position
                    trailing_size = remaining
                    warnings.append('zero-filled trailer begins at 0x%X' % position)
                    break
                raise ValueError('non-printable SCX FourCC %r at 0x%X' % (raw_tag, position))
            total_size = self.read_u32(position + 4)
            if total_size < 8 or total_size > remaining:
                raise ValueError('invalid SCX %r chunk size 0x%X at 0x%X (archive size 0x%X)' % (printable_tag(tag), total_size, position, self.file_size))
            chunks.append({
                'index': len(chunks),
                'type_code': tag,
                'stored_type_code': raw_tag.decode('latin-1'),
                'offset': position,
                'header_size': 8,
                'data_offset': position + 8,
                'data_size': total_size - 8,
                'total_size': total_size,
                'end': position + total_size,
            })
            position += total_size
        return chunks, trailing_offset, trailing_size, warnings

    def parse_flat_archive(self):
        '''Parse all SCX flat-chunk metadata.'''
        chunks, trailing_offset, trailing_size, warnings = self.parse_chunks()
        return {
            'toc_size': 0,
            'toc_entries': list(),
            'streams': list(),
            'chunks': chunks,
            'bulk_offset': self.file_size,
            'bulk_size': 0,
            'trailing_offset': trailing_offset,
            'trailing_size': trailing_size,
            'warnings': warnings,
        }

    def parse_archive(self):
        '''Parse metadata for the detected SC container layout.'''
        if self.family == 'flat':
            return self.parse_flat_archive()
        return self.parse_stream_archive()

    def get_resource_data(self, resource):
        '''Return one SCG/SCW logical resource.

        Standard `Rdat` resources retain their exact encoded representation.
        STOC-v2 `Ldat` fragments are reassembled and zlib-decompressed because
        that catalog stores one logical resource across one or more chunks.
        '''
        if self.family != 'stream':
            raise ValueError('SCX flat chunks do not contain parsed resources')
        output = bytearray()
        for block in resource['blocks']:
            output.extend(self.read_file(block['data_offset'], block['stored_size']))

        if resource.get('layout') != 'stoc-v2':
            return bytes(output)

        if resource['storage_mode'] == 'raw':
            data = bytes(output)
        elif resource['storage_mode'] == 'zlib':
            decompressor = zlib.decompressobj()
            try:
                data = decompressor.decompress(bytes(output)) + decompressor.flush()
            except zlib.error as error:
                raise ValueError(
                    'unable to decompress %s id 0x%X: %s'
                    % (printable_tag(resource['type_code']), resource['resource_id'], error)
                )
            if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
                raise ValueError(
                    'compressed %s id 0x%X is not one complete zlib stream'
                    % (printable_tag(resource['type_code']), resource['resource_id'])
                )
        else:
            raise ValueError('unsupported STOC-v2 storage mode %r' % resource['storage_mode'])

        if len(data) != resource['declared_expanded_size']:
            raise ValueError(
                'resource %s id 0x%X decoded to 0x%X bytes, expected 0x%X'
                % (
                    printable_tag(resource['type_code']),
                    resource['resource_id'],
                    len(data),
                    resource['declared_expanded_size'],
                )
            )
        return data

    def get_block_data(self, block):
        '''Return the exact stored payload of one `SDAT` or `Rdat` block.'''
        if self.family != 'stream':
            raise ValueError('SCX flat chunks do not contain parsed blocks')
        return self.read_file(block['data_offset'], block['stored_size'])

    def get_stream_data(self, stream):
        '''Return the exact bytes of one complete indexed wrapper stream.'''
        if self.family != 'stream':
            raise ValueError('SCX flat archives do not contain SWVR streams')
        return self.read_file(stream['offset'], stream['length'])

    def get_chunk_data(self, chunk, include_header=False):
        '''Return one SCX chunk payload, optionally including its 8-byte header.'''
        if self.family != 'flat':
            raise ValueError('SCG/SCW stream archives are not flat SCX chunks')
        if include_header:
            return self.read_file(chunk['offset'], chunk['total_size'])
        return self.read_file(chunk['data_offset'], chunk['data_size'])

    def get_companion_bulk_data(self):
        '''Return the complete external `.sas` bulk file for a companion-SAS archive.'''
        if self.companion_bulk_path is None:
            raise ValueError('this archive has no companion bulk file')
        try:
            data = self.companion_bulk_path.read_bytes()
        except OSError as error:
            raise ValueError('unable to read companion SAS %s: %s' % (self.companion_bulk_path, error))
        if len(data) != self.bulk_size:
            raise ValueError(
                'companion SAS %s changed size while reading: 0x%X != 0x%X'
                % (self.companion_bulk_path, len(data), self.bulk_size)
            )
        return data

    def get_stream_component(self, stream):
        '''Return a stable output-directory component for a stream.'''
        source_name = stream['toc_name'] or stream['wrapper_name']
        safe_name = safename(source_name, 'stream_%02d' % stream['index'])
        return '%02d_%s' % (stream['index'], safe_name)

    def get_resource_basename(self, resource, storage_suffix=True):
        '''Return the stable filename used for a logical resource.'''
        extension = safename(resource['type_code'], 'bin')
        return '%04d_id%08d.%s' % (resource['index'], resource['resource_id'], extension)

    def get_chunk_basename(self, chunk):
        '''Return a stable filename for one SCX flat chunk payload.'''
        extension = safename(chunk['type_code'].lower(), 'bin')
        return '%06d_%08x.%s' % (chunk['index'], chunk['offset'], extension)

    def iter_stream_archive(self):
        '''Yield the NiemaFS view for an SCG/SCW stream archive.'''
        resources_root = Path('resources')
        yield resources_root, None, None
        for stream in self.streams:
            stream_component = self.get_stream_component(stream)
            stream_directory = resources_root / stream_component
            yield stream_directory, None, None
            for resource in stream['resources']:
                resource_path = stream_directory / self.get_resource_basename(resource)
                yield resource_path, None, self.get_resource_data(resource)
        if self.raw_streams:
            streams_root = Path('streams')
            yield streams_root, None, None
            for stream in self.streams:
                stream_path = streams_root / (self.get_stream_component(stream) + '.swvr')
                yield stream_path, None, self.get_stream_data(stream)
        if self.split_blocks:
            blocks_root = Path('blocks')
            yield blocks_root, None, None
            for stream in self.streams:
                stream_directory = blocks_root / self.get_stream_component(stream)
                yield stream_directory, None, None
                for resource in stream['resources']:
                    resource_directory = stream_directory / self.get_resource_basename(resource, storage_suffix=False)
                    yield resource_directory, None, None
                    for block in resource['blocks']:
                        block_path = resource_directory / ('%04d.%s' % (block['index'], block['kind'].lower()))
                        yield block_path, None, self.get_block_data(block)
        if self.companion_bulk_path is not None and self.bulk_size and self.bulk_mode == 'file':
            bulk_root = Path('bulk')
            yield bulk_root, None, None
            yield (bulk_root / self.companion_bulk_path.name, None, self.get_companion_bulk_data())
        elif self.companion_bulk_path is not None and self.bulk_size and self.bulk_mode == 'pages':
            page_root = Path('bulk_pages')
            yield page_root, None, None
            try:
                with self.companion_bulk_path.open('rb') as bulk_file:
                    page_index = 0
                    position = 0
                    while position < self.bulk_size:
                        size = min(PAGE_SIZE, self.bulk_size - position)
                        data = bulk_file.read(size)
                        if len(data) != size:
                            raise ValueError('companion SAS %s was truncated while reading page %d' % (self.companion_bulk_path, page_index))
                        page_path = page_root / ('%04d_%08x.bin' % (page_index, position))
                        yield (page_path, None, data)
                        page_index += 1
                        position += size
            except OSError as error:
                raise ValueError('unable to read companion SAS %s: %s' % (self.companion_bulk_path, error))
        elif self.bulk_size and self.bulk_mode == 'file':
            bulk_root = Path('bulk')
            yield bulk_root, None, None
            bulk_path = bulk_root / ('bulk_%08x.bin' % self.bulk_offset)
            yield (bulk_path, None, self.read_file(self.bulk_offset, self.bulk_size))
        elif self.bulk_size and self.bulk_mode == 'pages':
            page_root = Path('bulk_pages')
            yield page_root, None, None
            page_index = 0
            position = self.bulk_offset
            while position < self.file_size:
                size = min(PAGE_SIZE, self.file_size - position)
                page_path = page_root / ('%04d_%08x.bin' % (page_index, position))
                yield (page_path, None, self.read_file(position, size))
                page_index += 1
                position += size

    def iter_flat_archive(self):
        '''Yield the NiemaFS view for an SCX flat-chunk archive.'''
        chunks_root = Path('chunks')
        yield chunks_root, None, None
        for chunk in self.chunks:
            yield (chunks_root / self.get_chunk_basename(chunk), None, self.get_chunk_data(chunk))
        if self.trailing_size:
            yield (chunks_root / ('%06d_%08x.trailing.bin' % (len(self.chunks), self.trailing_offset)), None, self.read_file(self.trailing_offset, self.trailing_size))

    def __iter__(self):
        '''Yield archive directories and files as NiemaFS tuples.'''
        if self.family == 'flat':
            yield from self.iter_flat_archive()
        else:
            yield from self.iter_stream_archive()

class ScgFS(ScFS):
    '''SCG-only reader using the big-endian stream-wrapper layout.'''
    def __init__(self, file_obj, path=None, bulk_mode='file', raw_streams=False, split_blocks=False):
        super().__init__(file_obj=file_obj, path=path, sc_format='scg', bulk_mode=bulk_mode, raw_streams=raw_streams, split_blocks=split_blocks)

class ScwFS(ScFS):
    '''SCW-only reader using the little-endian stream-wrapper layout.'''
    def __init__(self, file_obj, path=None, bulk_mode='file', raw_streams=False, split_blocks=False):
        super().__init__(file_obj=file_obj, path=path, sc_format='scw', bulk_mode=bulk_mode, raw_streams=raw_streams, split_blocks=split_blocks)

class ScxFS(ScFS):
    '''SCX-only reader using the little-endian flat-chunk layout.'''
    def __init__(self, file_obj, path=None):
        super().__init__(file_obj=file_obj, path=path, sc_format='scx', bulk_mode='none', raw_streams=False, split_blocks=False)
