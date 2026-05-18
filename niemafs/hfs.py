#! /usr/bin/env python
'''
Handle Apple HFS file systems
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from struct import unpack
from warnings import warn

# constants
MACTIME_START = datetime(1904, 1, 1)
HFS_LOGICAL_BLOCK_SIZE = 512
HFS_MDB_SIGNATURE = b'BD'   # classic HFS MDB signature
HFS_DDR_SIGNATURE = b'ER'   # Apple Driver Descriptor Record
HFS_APM_SIGNATURE = b'PM'   # Apple Partition Map entry
HFS_ROOT_CNID = 2
HFS_EXTENTS_CNID = 3
HFS_CATALOG_CNID = 4
HFS_DATA_FORK = 0x00
HFS_RESOURCE_FORK = 0xFF
HFS_SIGNATURE_SCAN_SIZE = 1024 * 1024

# Physical sector size, user-data offset within sector, user-data bytes.
# The 2352/16 case is what makes an APM/DDR "ER" appear at file offset 0x10.
COMMON_HFS_LAYOUT_CANDIDATES = [
    ( 512,  0,  512), # raw HFS with 512 sector size
    (2048,  0, 2048), # raw HFS with 2048 sector size
    (2352, 16, 2048), # CD-ROM Mode 1 raw
    (2352, 24, 2048), # CD-ROM XA Form 1 raw
    (2448, 16, 2048), # raw + subchannel
    (2448, 24, 2048), # XA raw + subchannel
    (2340,  4, 2048), # no sync, 4-byte header
    (2064, 16, 2048), # sync/header + data
    (2076, 16, 2048), # sync/header + data + EDC/zero
]

class HfsBTree:
    '''Class to represent HFS B-Tree'''
    NODE_HEADER_SIZE = 14
    NODE_TYPE_HEADER = 0x01
    NODE_TYPE_LEAF = 0xFF

    def __init__(self, data=b''):
        # set things up
        self.data = data
        self.node_size = 512

        # parse B-tree header
        header = self.read_node(0)
        desc = self.node_descriptor(header)
        if desc['type'] != self.NODE_TYPE_HEADER:
            raise ValueError("HFS B-tree node 0 is not a header node")
        rec0 = self.node_records(header)[0]
        if len(rec0) < 106:
            raise ValueError("HFS B-tree header record is too short")
        self.depth =        unpack('>H', rec0[0:2])[0]
        self.root =         unpack('>I', rec0[2:6])[0]
        self.record_count = unpack('>I', rec0[6:10])[0]
        self.first_leaf =   unpack('>I', rec0[10:14])[0]
        self.last_leaf =    unpack('>I', rec0[14:18])[0]
        self.node_size =    unpack('>H', rec0[18:20])[0] or 512
        self.key_len =      unpack('>H', rec0[20:22])[0]
        self.node_count =   unpack('>I', rec0[22:26])[0]
        self.free_nodes =   unpack('>I', rec0[26:30])[0]

    def read_node(self, node_number):
        '''Read a B-Tree node

        Args:
            `node_number` (`int`): The node number to read

        Returns:
            `bytes`: The node that was read
        '''
        start = node_number * self.node_size
        end = start + self.node_size
        node = self.data[start:end]
        if len(node) != self.node_size:
            raise ValueError("HFS B-tree node %d is incomplete" % node_number)
        return node

    def node_descriptor(self, node):
        '''Parse a descriptor of a node

        Args:
            `node` (`bytes`): The node to parse

        Returns:
            `dict`: The parsed node descriptor
        '''
        return {
            'flink':        unpack('>I', node[0:4])[0],
            'blink':        unpack('>I', node[4:8])[0],
            'type':         node[8],
            'height':       node[9],
            'record_count': unpack('>H', node[10:12])[0],
        }

    def node_records(self, node):
        '''Parse the records of a node

        Args:
            `node` (`bytes`): The node to parse

        Returns:
            `list`: The parsed node records
        '''
        n = unpack('>H', node[10:12])[0]
        offsets = [
            unpack('>H', node[self.node_size - 2 * (i + 1): self.node_size - 2 * i])[0]
            for i in range(n + 1)
        ]
        out = list()
        for i in range(n):
            start, end = offsets[i], offsets[i + 1]
            if start < self.NODE_HEADER_SIZE or end < start or end > self.node_size:
                raise ValueError("Bad HFS B-tree record offsets")
            out.append(node[start:end])
        return out

    def leaf_records(self):
        '''Iterate over the leaf records'''
        node_number = self.first_leaf
        seen = set()
        while node_number and node_number not in seen:
            seen.add(node_number)
            node = self.read_node(node_number)
            desc = self.node_descriptor(node)
            if desc['type'] != self.NODE_TYPE_LEAF:
                break
            for rec in self.node_records(node):
                yield rec
            if node_number == self.last_leaf:
                break
            node_number = desc['flink']


class HfsFS(FileSystem):
    '''Minimal reader for classic Apple HFS, not HFS+.'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.physical_logical_block_size = None
        self.user_data_offset = None
        self.user_data_size = None
        self.image_base_offset = 0
        self.volume_offset = None
        self.mdb = None
        self.allocation_block_size = None
        self.first_allocation_block = None
        self.extents_overflow = {}
        self.catalog_records = None
        self.detect_layout()
        self.parse_master_directory_block()
        self.load_extents_overflow()

    def get_mac_time(seconds):
        '''Parse integer seconds as Mac Time

        Args:
            `seconds` (`int`): The seconds since the Mac Time start

        Returns:
            `datetime`: The parsed Mac Time
        '''
        try:
            return MACTIME_START + timedelta(seconds=seconds)
        except Exception:
            return None

    def decode_text(data):
        '''Decode HFS string

        Args:
            `data` (`bytes`): The raw HFS bytes representing the string

        Returns:
            `str`: The decoded string
        '''
        data = bytes(data).split(b'\0', 1)[0]
        try:
            return data.decode('mac_roman').rstrip()
        except Exception:
            return data.decode('latin-1', errors='replace').rstrip()

    def pstring(data):
        '''Decode a pstring (e.g. volume name)

        Args:
            `data` (`bytes`): The raw bytes to decode

        Returns:
            `str`: The decoded string
        '''
        if not data:
            return ''
        n = min(data[0], len(data) - 1)
        return HfsFS.decode_text(data[1:1 + n]).replace('/', ':')

    def read_stream(self, offset, length):
        '''Read bytes from the logical user-data stream, stripping raw CD sector headers if needed.

        Args:
            `offset` (`int`): The offset from which to start reading.

            `length` (`int`): The number of bytes to read, or `None` to read to the end.

        Returns:
            `bytes`: The read data.
        '''
        if length <= 0:
            return b''
        if self.physical_logical_block_size == self.user_data_size and self.user_data_offset == 0:
            return self.read_file(self.image_base_offset + offset, length)
        out = bytearray()
        pos = offset
        remaining = length
        while remaining > 0:
            sector, inside = divmod(pos, self.user_data_size)
            n = min(remaining, self.user_data_size - inside)
            raw_off = (
                self.image_base_offset
                + sector * self.physical_logical_block_size
                + self.user_data_offset
                + inside
            )
            chunk = self.read_file(raw_off, n)
            if not chunk:
                break
            out.extend(chunk)
            got = len(chunk)
            pos += got
            remaining -= got
            if got < n:
                break
        return bytes(out)

    def read_volume(self, offset, length):
        '''Read a volume

        Args:
            `offset` (`int`): The offset from which to start reading.

            `length` (`int`): The number of bytes to read, or `None` to read to the end.

        Returns:
            `bytes`: The read data.
        '''
        return self.read_stream(self.volume_offset + offset, length)

    def parse_extents(self, data):
        '''Parse extents

        Args:
            `data` (`bytes`): The raw data to parse

        Returns:
            `list`: The parsed extents
        '''
        out = list()
        for i in range(0, min(len(data), 12), 4):
            start = unpack('>H', data[i   : i+2])[0]
            count = unpack('>H', data[i+2 : i+4])[0]
            if count:
                out.append((start, count))
        return out

    def check_hfs(self, volume_offset):
        '''Check if this looks like a valid HFS starting at a given volume offset

        Args:
            `volume_offset` (`int`): The volume offset to check

        Returns:
            `bool`: `True` if this is a valid HFS, otherwise `False`.
        '''
        mdb = self.read_stream(volume_offset + 2 * HFS_LOGICAL_BLOCK_SIZE, 162)
        if len(mdb) < 162 or mdb[0:2] != HFS_MDB_SIGNATURE:
            return False
        alloc_size = unpack('>I', mdb[20 : 24])[0]
        alloc_count = unpack('>H', mdb[18 : 20])[0]
        first_alloc = unpack('>H', mdb[28 : 30])[0]
        cat_size = unpack('>I', mdb[146 : 150])[0]
        cat_ext = self.parse_extents(mdb[150:162])
        if alloc_size == 0 or alloc_size % HFS_LOGICAL_BLOCK_SIZE != 0:
            return False
        if alloc_count == 0 or first_alloc < 3:
            return False
        if cat_size == 0 or not cat_ext:
            return False
        return True

    def find_apm(self, apm_base, block_size):
        '''Find the Apple Partition Map (APM) in an HFS filesystem

        Args:
            `apm_base` (`int`): The APM base to check

            `block_size` (`int`): The block size

        Returns:
            `int`: The volume offset of the APM base if found, otherwise `None`.
        '''
        if block_size not in {512, 1024, 2048, 4096}:
            return None
        first = self.read_stream(apm_base + block_size, min(block_size, 512))
        if len(first) < 136 or first[0:2] != HFS_APM_SIGNATURE:
            return None
        count = unpack('>I', first[4 : 8])[0]
        if count == 0 or count > 4096:
            return None
        fallback = None
        for i in range(1, count + 1):
            entry = self.read_stream(apm_base + i * block_size, min(block_size, 512))
            if len(entry) < 136 or entry[0:2] != HFS_APM_SIGNATURE:
                continue
            start_block = unpack('>I', entry[8 : 12])[0]
            part_type = HfsFS.decode_text(entry[48:80])
            vol_off = apm_base + start_block * block_size
            if self.check_hfs(vol_off):
                if part_type == 'Apple_HFS':
                    return vol_off
                if fallback is None:
                    fallback = vol_off
        return fallback

    def probe_layout(self, scan=False):
        '''Probe the HFS layout for the Apple Partition Map (APM)

        Args:
            `scan` (`bool`): `True` to scan fo rthe HFS DDR signature, otherwise `False.

        Returns:
            `int`: The offset of the APM, otherwise `None`.
        '''
        if self.check_hfs(0):
            return 0
        ddr = self.read_stream(0, 512)
        if len(ddr) >= 8 and ddr[0:2] == HFS_DDR_SIGNATURE:
            block_size = unpack('>H', ddr[2 : 4])[0]
            found = self.find_apm(0, block_size)
            if found is not None:
                return found
        for block_size in (512, 2048):
            found = self.find_apm(0, block_size)
            if found is not None:
                return found
        if not scan:
            return None
        buf = self.read_stream(0, HFS_SIGNATURE_SCAN_SIZE)
        pos = 0
        while True:
            pos = buf.find(HFS_DDR_SIGNATURE, pos)
            if pos < 0:
                break
            ddr = self.read_stream(pos, 512)
            if len(ddr) >= 8 and ddr[0:2] == HFS_DDR_SIGNATURE:
                block_size = unpack('>H', ddr[2 : 4])[0]
                found = self.find_apm(pos, block_size)
                if found is not None:
                    return found
            pos += 1
        pos = 0
        while True:
            pos = buf.find(HFS_MDB_SIGNATURE, pos)
            if pos < 0:
                break
            vol_off = pos - 2 * HFS_LOGICAL_BLOCK_SIZE
            if vol_off >= 0 and vol_off % HFS_LOGICAL_BLOCK_SIZE == 0:
                if self.check_hfs(vol_off):
                    return vol_off
            pos += 1
        return None

    def detect_layout(self):
        '''Detect HFS image layout'''
        if self.volume_offset is not None:
            return

        # first pass: exact probes (this catches direct images and raw CD sectors cleanly)
        for phys, off, user_size in COMMON_HFS_LAYOUT_CANDIDATES:
            self.physical_logical_block_size = phys
            self.user_data_offset = off
            self.user_data_size = user_size
            self.image_base_offset = 0
            found = self.probe_layout(scan=False)
            if found is not None:
                self.volume_offset = found
                return

        # second pass: signature scan (prefer non-identity/raw-CD layouts to avoid falsely treating a raw sector header as a one-time file prefix)
        scan_order = [c for c in COMMON_HFS_LAYOUT_CANDIDATES if c[0] != c[2] or c[1] != 0]
        scan_order += [c for c in COMMON_HFS_LAYOUT_CANDIDATES if c not in scan_order]
        for phys, off, user_size in scan_order:
            self.physical_logical_block_size = phys
            self.user_data_offset = off
            self.user_data_size = user_size
            self.image_base_offset = 0
            found = self.probe_layout(scan=True)
            if found is not None:
                self.volume_offset = found
                return
        raise ValueError("No classic HFS volume found")

    def parse_master_directory_block(self):
        '''Parse Master Directory Block

        Returns:
            `dict`: The parsed Master Directory Block
        '''
        if self.mdb is not None:
            return self.mdb
        mdb = self.read_volume(2 * HFS_LOGICAL_BLOCK_SIZE, HFS_LOGICAL_BLOCK_SIZE)
        if len(mdb) < 162 or mdb[0:2] != HFS_MDB_SIGNATURE:
            raise ValueError("Not a classic HFS volume (missing MDB signature)")
        self.mdb = {
            'signature': mdb[0:2],
            'created': HfsFS.get_mac_time(unpack('>I', mdb[2 : 6])[0]),
            'modified': HfsFS.get_mac_time(unpack('>I', mdb[6 : 10])[0]),
            'allocation_block_count': unpack('>H', mdb[18 : 20])[0],
            'allocation_block_size': unpack('>I', mdb[20 : 24])[0],
            'first_allocation_block': unpack('>H', mdb[28 : 30])[0],
            'volume_name': HfsFS.pstring(mdb[36:64]),
            'extents_file_size': unpack('>I', mdb[130 : 134])[0],
            'extents_file_extents': self.parse_extents(mdb[134:146]),
            'catalog_file_size': unpack('>I', mdb[146 : 150])[0],
            'catalog_file_extents': self.parse_extents(mdb[150:162]),
        }
        self.allocation_block_size = self.mdb['allocation_block_size']
        self.first_allocation_block = self.mdb['first_allocation_block']
        return self.mdb

    def read_from_extents(self, extents, length):
        '''Read from extents

        Args:
            `extents` (`list`): The extents to read from

            `length` (`int`): The number of blocks to read

        Returns:
            `bytes`: The read data
        '''
        if length <= 0:
            return b''
        out = bytearray()
        remaining = length
        for start, count in extents:
            if remaining <= 0:
                break
            n = min(remaining, count * self.allocation_block_size)
            allocation_block_offset = self.first_allocation_block * HFS_LOGICAL_BLOCK_SIZE + start * self.allocation_block_size
            out.extend(self.read_volume(allocation_block_offset, n))
            remaining -= n
        if len(out) < length:
            warn("HFS fork is shorter than expected; extents-overflow data may be incomplete")
        return bytes(out[:length])

    def resolve_extents_from_overflow(self, file_id, fork_type, initial_extents, length):
        extents = list(initial_extents)
        needed = ceil(length / self.allocation_block_size) if length else 0
        have = sum(count for _, count in extents)
        if have >= needed:
            return extents
        for fabn, more_extents in sorted(self.extents_overflow.get((file_id, fork_type), [])):
            if fabn < have:
                continue
            extents.extend(more_extents)
            have = sum(count for _, count in extents)
            if have >= needed:
                break
        return extents

    def read_fork(self, file_id, fork_type, initial_extents, length):
        extents = self.resolve_extents_from_overflow(
            file_id,
            fork_type,
            initial_extents,
            length,
        )
        return self.read_from_extents(extents, length)

    def parse_extents_overflow_records(self, data):
        records = {}
        if not data:
            return records
        tree = HfsBTree(data)
        for rec in tree.leaf_records():
            if len(rec) < 20 or rec[0] != 7:
                continue
            fork_type = rec[1]
            file_id = unpack('>I', rec[2 : 6])[0]
            fabn = unpack('>H', rec[6 : 8])[0]
            extents = self.parse_extents(rec[8:20])
            if extents:
                records.setdefault((file_id, fork_type), []).append((fabn, extents))
        return records

    def load_extents_overflow(self):
        self.extents_overflow = {}
        size = self.mdb['extents_file_size']
        initial = self.mdb['extents_file_extents']
        if not size or not initial:
            return self.extents_overflow
        extents = list(initial)
        # usually one pass is enough: extra passes allow the extents-overflow file to describe additional extents of itself
        for _ in range(3):
            data = self.read_from_extents(extents, size)
            parsed = self.parse_extents_overflow_records(data)
            self.extents_overflow = parsed
            new_extents = self.resolve_extents_from_overflow(
                HFS_EXTENTS_CNID,
                HFS_DATA_FORK,
                initial,
                size,
            )
            if new_extents == extents:
                break
            extents = new_extents
        return self.extents_overflow

    def catalog_leaf_records(self):
        data = self.read_fork(
            HFS_CATALOG_CNID,
            HFS_DATA_FORK,
            self.mdb['catalog_file_extents'],
            self.mdb['catalog_file_size'],
        )
        return HfsBTree(data).leaf_records()

    def parse_catalog_key(self, rec):
        key_len = rec[0]
        if key_len == 0 or len(rec) < 1 + key_len:
            return None
        parent_id = unpack('>I', rec[2 : 6])[0]
        name_len = rec[6]
        name = HfsFS.decode_text(rec[7:7 + name_len]).replace('/', ':')
        return {
            'key_len': key_len,
            'data_offset': 1 + key_len,
            'parent_id': parent_id,
            'name': name,
        }

    def parse_catalog_record(self, rec):
        key = self.parse_catalog_key(rec)
        if key is None or len(rec) <= key['data_offset']:
            return None
        data = rec[key['data_offset']:]
        record_type = data[0]
        if record_type == 1 and len(data) >= 70:  # directory record
            return {
                'kind': 'directory',
                'name': key['name'],
                'parent_id': key['parent_id'],
                'cnid': unpack('>I', data[6 : 10])[0],
                'created': HfsFS.get_mac_time(unpack('>I', data[10 : 14])[0]),
                'modified': HfsFS.get_mac_time(unpack('>I', data[14 : 18])[0]),
            }
        if record_type == 2 and len(data) >= 102:  # file record
            return {
                'kind': 'file',
                'name': key['name'],
                'parent_id': key['parent_id'],
                'cnid': unpack('>I', data[20 : 24])[0],
                'created': HfsFS.get_mac_time(unpack('>I', data[44 : 48])[0]),
                'modified': HfsFS.get_mac_time(unpack('>I', data[48 : 52])[0]),

                # Data fork only, to match your IsoFS iterator shape.
                'data_length': unpack('>I', data[26 : 30])[0],
                'data_extents': self.parse_extents(data[74:86]),

                # Parsed, but not yielded.
                'resource_length': unpack('>I', data[36 : 40])[0],
                'resource_extents': self.parse_extents(data[86:98]),
            }
        return None

    def load_catalog_records(self):
        if self.catalog_records is not None:
            return self.catalog_records
        records = list()
        for raw in self.catalog_leaf_records():
            parsed = self.parse_catalog_record(raw)
            if parsed is not None and parsed.get('name'):
                records.append(parsed)
        self.catalog_records = records
        return records

    def __iter__(self):
        # map parent directory IDs to children
        records = self.load_catalog_records()
        children = dict()
        directories = dict()
        for rec in records:
            if rec['parent_id'] not in children:
                children[rec['parent_id']] = list()
            children[rec['parent_id']].append(rec)
            if rec['kind'] == 'directory':
                directories[rec['cnid']] = rec

        # perform search starting from root directory
        to_visit = [(Path(''), HFS_ROOT_CNID)]
        while len(to_visit) != 0:
            curr_path, curr_id = to_visit.pop()

            # handle current directory
            if curr_path != Path(''):
                curr_directory_entry = directories[curr_id]
                yield (curr_path, curr_directory_entry['modified'], None)

            # load children of current directory
            for next_entry in children.get(curr_id, []):
                next_entry_fn = next_entry['name']
                next_path = curr_path / next_entry_fn

                # next entry is a directory: add it to `to_visit`
                if next_entry['kind'] == 'directory':
                    to_visit.append((next_path, next_entry['cnid']))

                # next entry is a file: read and yield it
                elif next_entry['kind'] == 'file':
                    next_data = self.read_fork(next_entry['cnid'], HFS_DATA_FORK, next_entry['data_extents'], next_entry['data_length'])
                    yield (next_path, next_entry['modified'], next_data)
