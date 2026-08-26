#! /usr/bin/env python
'''
Handle Microsoft Xbox / Xbox 360 XDVDFS file systems
'''

# NiemaFS imports
from niemafs.common import clean_string, FileSystem

# imports
from datetime import datetime, timedelta, timezone
from pathlib import Path
from struct import unpack
from warnings import warn


# constants
XDVDFS_MAGIC_WORD = b'MICROSOFT*XBOX*MEDIA'
XDVDFS_SECTOR_SIZE = 2048
XDVDFS_VOLUME_DESCRIPTOR_SECTOR = 32
XDVDFS_VOLUME_DESCRIPTOR_SIZE = XDVDFS_SECTOR_SIZE

# Known locations of the XDVDFS game partition within Xbox/Xbox 360
# disc images.
#
# XISO:
#     The XDVDFS game partition starts at byte 0.
#
# XGD2:
#     The game partition starts at 0x0FD90000.
#
# XGD3:
#     The game partition starts at 0x02080000.
#
# XGD1:
#     The game partition starts at 0x18300000.
XDVDFS_PARTITION_LAYOUTS = [
    ('XISO', 0x00000000),
    ('XGD2', 0x0FD90000),
    ('XGD3', 0x02080000),
    ('XGD1', 0x18300000),
]

# XDVDFS directory entry constants
XDVDFS_DIRECTORY_ENTRY_HEADER_SIZE = 14
XDVDFS_FILENAME_OFFSET = 14
XDVDFS_FILENAME_MAX_LENGTH = 255

# XDVDFS file attributes
XDVDFS_ATTRIBUTE_READ_ONLY = 0x01
XDVDFS_ATTRIBUTE_HIDDEN = 0x02
XDVDFS_ATTRIBUTE_SYSTEM = 0x04
XDVDFS_ATTRIBUTE_DIRECTORY = 0x10
XDVDFS_ATTRIBUTE_ARCHIVE = 0x20
XDVDFS_ATTRIBUTE_NORMAL = 0x80

# XDVDFS uses DWORD offsets for directory-tree pointers.
XDVDFS_DWORD_SIZE = 4

# Windows FILETIME epoch
WINDOWS_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


class XdvdFS(FileSystem):
    '''Class to represent a Microsoft Xbox / Xbox 360 XDVDFS file system.'''

    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")

        super().__init__(path=path, file_obj=file_obj)

        self.disc_layout = None
        self.game_partition_offset = None

        self.volume_descriptor = None
        self.volume_descriptor_parsed = None

        self.root_directory_sector = None
        self.root_directory_size = None

        # detect the game partition and load the volume descriptor to
        # ensure that the file is a valid XDVDFS image
        self.detect_layout()
        self.get_volume_descriptor()

    @staticmethod
    def parse_filetime(data):
        '''Parse a Windows FILETIME.

        Args:
            `data` (`bytes`): An 8-byte Windows FILETIME.

        Returns:
            `datetime`: A timezone-aware UTC datetime.
        '''
        if len(data) != 8:
            raise ValueError(
                "XDVDFS FILETIME must be exactly 8 bytes: %s" % data
            )

        value = unpack('<Q', data)[0]

        try:
            return WINDOWS_EPOCH + timedelta(
                microseconds=value / 10
            )
        except (OverflowError, ValueError):
            raise ValueError(
                "Invalid XDVDFS FILETIME: %s" % data
            )

    @staticmethod
    def parse_attributes(x):
        '''Parse XDVDFS file attributes.

        Args:
            `x` (`int`): The raw attribute byte.

        Returns:
            `dict`: Parsed file attributes.
        '''
        return {
            'is_read_only': bool(
                x & XDVDFS_ATTRIBUTE_READ_ONLY
            ),
            'is_hidden': bool(
                x & XDVDFS_ATTRIBUTE_HIDDEN
            ),
            'is_system': bool(
                x & XDVDFS_ATTRIBUTE_SYSTEM
            ),
            'is_directory': bool(
                x & XDVDFS_ATTRIBUTE_DIRECTORY
            ),
            'is_archive': bool(
                x & XDVDFS_ATTRIBUTE_ARCHIVE
            ),
            'is_normal': bool(
                x & XDVDFS_ATTRIBUTE_NORMAL
            ),
        }

    @staticmethod
    def parse_directory_entry(data):
        '''Parse an XDVDFS directory entry.

        Args:
            `data` (`bytes`): The raw directory-entry data.

        Returns:
            `dict`: The parsed directory entry.
        '''
        if len(data) < XDVDFS_DIRECTORY_ENTRY_HEADER_SIZE:
            raise ValueError(
                "XDVDFS directory entry is too short: %d bytes"
                % len(data)
            )

        out = dict()

        # These are offsets in DWORDs relative to the beginning of
        # the directory table, NOT byte offsets.
        out['left_offset'] = unpack(
            '<H', data[0x00:0x02]
        )[0]

        out['right_offset'] = unpack(
            '<H', data[0x02:0x04]
        )[0]

        # Starting sector of the file/directory relative to the
        # beginning of the XDVDFS game partition.
        out['start_sector'] = unpack(
            '<I', data[0x04:0x08]
        )[0]

        # File size in bytes.
        out['file_size'] = unpack(
            '<I', data[0x08:0x0C]
        )[0]

        # File attributes.
        out['attributes_raw'] = data[0x0C]
        out['attributes'] = XdvdFS.parse_attributes(
            out['attributes_raw']
        )

        # Filename length.
        out['filename_length'] = data[0x0D]

        filename_end = (
            XDVDFS_FILENAME_OFFSET +
            out['filename_length']
        )

        if filename_end > len(data):
            raise ValueError(
                "XDVDFS filename extends beyond directory entry: "
                "%d > %d" % (filename_end, len(data))
            )

        filename = data[
            XDVDFS_FILENAME_OFFSET:filename_end
        ]

        # XDVDFS filenames are single-byte strings. Most Xbox/Xbox 360
        # filenames are ASCII. Decode UTF-8 first to retain compatibility
        # with existing NiemaFS string handling, then fall back to cp1252
        # for unusual images.
        try:
            out['filename'] = filename.decode('utf-8')
        except UnicodeDecodeError:
            try:
                out['filename'] = filename.decode('cp1252')
            except UnicodeDecodeError:
                warn(
                    "Unable to parse XDVDFS filename as string: %s"
                    % filename
                )
                out['filename'] = str(filename)

        out['filename'] = clean_string(out['filename'])

        # XDVDFS does not have a per-file modification timestamp in
        # the directory entry. The volume creation timestamp is the
        # closest filesystem-level timestamp available.
        out['datetime'] = None

        return out

    @staticmethod
    def directory_entry_size(filename_length):
        '''Return the on-disc size of an XDVDFS directory entry.

        Args:
            `filename_length` (`int`): Length of the filename.

        Returns:
            `int`: Entry size rounded up to a DWORD boundary.
        '''
        size = (
            XDVDFS_DIRECTORY_ENTRY_HEADER_SIZE +
            filename_length
        )

        return (
            size +
            (XDVDFS_DWORD_SIZE - 1)
        ) & ~(XDVDFS_DWORD_SIZE - 1)

    def read_game_partition(self, offset, length=None):
        '''Read bytes relative to the XDVDFS game partition.

        Args:
            `offset` (`int`): Byte offset within the game partition.

            `length` (`int`): Number of bytes to read, or `None` to
                read through EOF.

        Returns:
            `bytes`: The requested data.
        '''
        if offset < 0:
            raise ValueError(
                "offset must be non-negative"
            )

        return self.read_file(
            self.game_partition_offset + offset,
            length
        )

    def read_game_sectors(self, sector, count=1):
        '''Read XDVDFS sectors.

        Args:
            `sector` (`int`): First XDVDFS sector.

            `count` (`int`): Number of sectors.

        Returns:
            `bytes`: Concatenated sector data.
        '''
        if sector < 0:
            raise ValueError(
                "sector must be non-negative"
            )

        if count <= 0:
            return b''

        return self.read_game_partition(
            sector * XDVDFS_SECTOR_SIZE,
            count * XDVDFS_SECTOR_SIZE
        )

    def detect_layout(self):
        '''Detect the XDVDFS game-partition location.

        The XDVDFS volume descriptor is at sector 32 relative to the
        beginning of the game partition.

        Returns:
            `None`
        '''
        if self.game_partition_offset is not None:
            return

        descriptor_offset = (
            XDVDFS_VOLUME_DESCRIPTOR_SECTOR *
            XDVDFS_SECTOR_SIZE
        )

        for layout_name, partition_offset in XDVDFS_PARTITION_LAYOUTS:
            try:
                magic = self.read_file(
                    partition_offset + descriptor_offset,
                    len(XDVDFS_MAGIC_WORD)
                )

                if magic == XDVDFS_MAGIC_WORD:
                    self.disc_layout = layout_name
                    self.game_partition_offset = partition_offset
                    return

            except Exception:
                pass

        raise ValueError(
            "XDVDFS layout does not match any known "
            "Xbox/Xbox 360 layouts"
        )

    def get_game_partition_offset(self):
        '''Return the XDVDFS game-partition offset.

        Returns:
            `int`: Byte offset of the game partition.
        '''
        if self.game_partition_offset is None:
            self.detect_layout()

        return self.game_partition_offset

    def get_volume_descriptor(self):
        '''Return the raw XDVDFS volume descriptor.

        Returns:
            `bytes`: The 2048-byte volume descriptor.
        '''
        if self.volume_descriptor is None:
            self.volume_descriptor = self.read_game_sectors(
                XDVDFS_VOLUME_DESCRIPTOR_SECTOR
            )

            if len(self.volume_descriptor) != (
                XDVDFS_VOLUME_DESCRIPTOR_SIZE
            ):
                raise ValueError(
                    "XDVDFS volume descriptor must be exactly "
                    "2048 bytes"
                )

            if self.volume_descriptor[0x00:0x14] != (
                XDVDFS_MAGIC_WORD
            ):
                raise ValueError(
                    "Invalid XDVDFS volume descriptor magic"
                )

            if self.volume_descriptor[0x7EC:0x800] != (
                XDVDFS_MAGIC_WORD
            ):
                raise ValueError(
                    "Invalid XDVDFS volume descriptor trailing magic"
                )

        return self.volume_descriptor

    def parse_volume_descriptor(self):
        '''Parse the XDVDFS volume descriptor.

        Returns:
            `dict`: Parsed volume-descriptor fields.
        '''
        if self.volume_descriptor_parsed is not None:
            return self.volume_descriptor_parsed

        data = self.get_volume_descriptor()

        out = dict()

        out['magic_word'] = data[0x00:0x14]

        # Root directory table location and size.
        out['root_directory_sector'] = unpack(
            '<I', data[0x14:0x18]
        )[0]

        out['root_directory_size'] = unpack(
            '<I', data[0x18:0x1C]
        )[0]

        # Volume/image creation time.
        try:
            out['datetime'] = self.parse_filetime(
                data[0x1C:0x24]
            )
        except ValueError:
            warn(
                "Unable to parse XDVDFS volume creation "
                "date/time"
            )
            out['datetime'] = None

        # Preserve the unused area and trailing magic.
        out['unused'] = data[0x24:0x7EC]
        out['trailing_magic_word'] = data[0x7EC:0x800]

        self.root_directory_sector = (
            out['root_directory_sector']
        )

        self.root_directory_size = (
            out['root_directory_size']
        )

        self.volume_descriptor_parsed = out

        return out

    def get_root_directory_table(self):
        '''Return the raw root directory table.

        Returns:
            `bytes`: The root directory table.
        '''
        if self.root_directory_sector is None:
            self.parse_volume_descriptor()

        if self.root_directory_size == 0:
            return b''

        return self.read_game_partition(
            self.root_directory_sector *
            XDVDFS_SECTOR_SIZE,
            self.root_directory_size
        )

    def get_directory_table(self, entry):
        '''Return the directory table associated with an entry.

        Args:
            `entry` (`dict`): A parsed directory entry.

        Returns:
            `bytes`: The raw directory table.
        '''
        if not entry['attributes']['is_directory']:
            raise ValueError(
                "Directory table requested for a non-directory entry"
            )

        # An empty directory has start sector and size set to zero.
        if (
            entry['start_sector'] == 0 or
            entry['file_size'] == 0
        ):
            return b''

        return self.read_game_partition(
            entry['start_sector'] * XDVDFS_SECTOR_SIZE,
            entry['file_size']
        )

    def read_entry_data(self, entry):
        '''Read the data associated with an XDVDFS directory entry.

        Args:
            `entry` (`dict`): A parsed directory entry.

        Returns:
            `bytes`: File data, or b'' for directories/empty files.
        '''
        if entry['attributes']['is_directory']:
            return b''

        if entry['file_size'] == 0:
            return b''

        return self.read_game_partition(
            entry['start_sector'] * XDVDFS_SECTOR_SIZE,
            entry['file_size']
        )

    def _read_entry_at(self, table, offset):
        '''Read an XDVDFS directory entry at a byte offset.

        Args:
            `table` (`bytes`): Raw directory-table data.

            `offset` (`int`): Byte offset of the entry.

        Returns:
            `dict`: Parsed directory entry.
        '''
        if offset < 0 or offset >= len(table):
            raise ValueError(
                "XDVDFS directory entry offset out of bounds: "
                "0x%X" % offset
            )

        if offset + XDVDFS_DIRECTORY_ENTRY_HEADER_SIZE > len(table):
            raise ValueError(
                "XDVDFS directory entry header extends beyond "
                "directory table at 0x%X" % offset
            )

        filename_length = table[offset + 0x0D]

        entry_size = self.directory_entry_size(
            filename_length
        )

        if offset + entry_size > len(table):
            raise ValueError(
                "XDVDFS directory entry extends beyond "
                "directory table at 0x%X" % offset
            )

        return self.parse_directory_entry(
            table[offset:offset + entry_size]
        )

    def _walk_directory_tree(
        self,
        table,
        offset,
        visited=None
    ):
        '''Walk an XDVDFS directory binary tree.

        XDVDFS directory entries are stored as a binary search tree.
        The root entry is at byte offset 0.

        Importantly, the left/right pointers are stored as DWORD
        offsets, rather than byte offsets. A pointer value of zero
        means that the corresponding subtree is empty.

        Args:
            `table` (`bytes`): Raw directory-table data.

            `offset` (`int`): Byte offset of the current entry.

            `visited` (`set`): Set of already visited byte offsets.

        Yields:
            `(offset, entry)` tuples.
        '''
        if visited is None:
            visited = set()

        if offset < 0 or offset >= len(table):
            raise ValueError(
                "XDVDFS directory entry offset out of bounds: "
                "0x%X" % offset
            )

        if offset in visited:
            raise ValueError(
                "Cycle detected in XDVDFS directory tree at "
                "0x%X" % offset
            )

        visited.add(offset)

        entry = self._read_entry_at(
            table,
            offset
        )

        # XDVDFS stores these values in DWORDs.
        #
        # For example:
        #
        #     left_offset == 1
        #
        # means byte offset 4 in the directory table.
        left_offset = (
            entry['left_offset'] *
            XDVDFS_DWORD_SIZE
        )

        right_offset = (
            entry['right_offset'] *
            XDVDFS_DWORD_SIZE
        )

        # A child pointer of zero means no child.
        if entry['left_offset'] != 0:
            yield from self._walk_directory_tree(
                table,
                left_offset,
                visited
            )

        yield (offset, entry)

        if entry['right_offset'] != 0:
            yield from self._walk_directory_tree(
                table,
                right_offset,
                visited
            )

    def parse_directory_table(self, table=None):
        '''Parse an XDVDFS directory table.

        Args:
            `table` (`bytes`): Raw directory-table data. If None,
                the root directory table is used.

        Returns:
            `list`: Directory entries in sorted filename order.
        '''
        if table is None:
            table = self.get_root_directory_table()

        if len(table) == 0:
            return []

        # The root of every XDVDFS directory tree is the entry at
        # byte offset zero.
        return [
            entry
            for offset, entry in self._walk_directory_tree(
                table,
                0
            )
        ]

    def _parse_directory(
        self,
        parent_path,
        table,
        timestamp
    ):
        '''Recursively parse an XDVDFS directory.

        Args:
            `parent_path` (`Path`): Path of the parent directory.

            `table` (`bytes`): Raw directory-table data.

            `timestamp` (`datetime`): Filesystem-level timestamp.

        Yields:
            NiemaFS `(Path, datetime, bytes)` tuples.
        '''
        for entry in self.parse_directory_table(table):
            path = parent_path / entry['filename']

            if entry['attributes']['is_directory']:
                yield (
                    path,
                    timestamp,
                    None
                )

                child_table = self.get_directory_table(
                    entry
                )

                yield from self._parse_directory(
                    path,
                    child_table,
                    timestamp
                )

            else:
                yield (
                    path,
                    timestamp,
                    self.read_entry_data(entry)
                )

    def __iter__(self):
        '''Iterate over the files and folders in the XDVDFS.

        Yields:
            Each entry as a tuple containing:

                (Path, modification timestamp, bytes or None)
        '''
        # Ensure that the volume descriptor has been parsed.
        volume = self.parse_volume_descriptor()

        timestamp = volume.get('datetime')

        root_table = self.get_root_directory_table()

        for entry in self.parse_directory_table(root_table):
            path = Path(entry['filename'])

            if entry['attributes']['is_directory']:
                yield (
                    path,
                    timestamp,
                    None
                )

                child_table = self.get_directory_table(
                    entry
                )

                yield from self._parse_directory(
                    path,
                    child_table,
                    timestamp
                )

            else:
                yield (
                    path,
                    timestamp,
                    self.read_entry_data(entry)
                )
