#! /usr/bin/env python
'''
Handle Nintendo Wii DVD file system
'''

# NiemaFS imports
from niemafs.common import clean_string, FileSystem

# imports
from datetime import datetime
from pathlib import Path
from struct import unpack
from warnings import warn

# constants
PARTITION_TYPE = [
    'data',              # type 0
    'update',            # type 1
    'channel_installer', # type 2
]
REGION = {
    0: 'Japan/Taiwan',
    1: 'USA',
    2: 'PAL',
    4: 'Korea',
}

class WiiFS(FileSystem):
    '''Class to represent a `Nintendo Wii DVD <https://wiibrew.org/wiki/Wii_disc#%22System_Area%22>`_.'''
    def __init__(self, file_obj, path=None):
        # set things up
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.header = None           # Header
        self.partitions_info = None  # Partitions Information
        self.partition_tables = None # Partition Tables
        self.region_info = None      # Region Information

    def get_header(self):
        '''Return the `Header <https://wiibrew.org/wiki/Wii_disc#Header>`_ of the Wii disc.

        Returns:
            `bytes`: The Header of the Wii disc.
        '''
        if self.header is None:
            self.header = self.read_file(0x0000, 0x0400)
        return self.header

    def get_partitions_info(self):
        '''Return the `Partitions Information <https://wiibrew.org/wiki/Wii_disc#Partitions_information>`_ of the Wii disc.

        Returns:
            `bytes`: The Partitions Information of the Wii disc.
        '''
        if self.partitions_info is None:
            self.partitions_info = self.read_file(0x40000, 32)
        return self.partitions_info

    def get_partition_tables(self):
        '''Return the `Partition Tables <https://wiibrew.org/wiki/Wii_disc#Partition_table_entry>`_ of the Wii disc.

        Returns:
            `list` of `bytes`: The Partition Tables of the Wii disc.
        '''
        if self.partition_tables is None:
            self.partition_tables = [self.read_file(parts_info['table_offset'], 8 * parts_info['num_partitions']) for parts_info in self.parse_partitions_info()]
        return self.partition_tables

    def get_region_info(self):
        '''Return the `Region Information <https://wiibrew.org/wiki/Wii_disc#Region_setting>`_ of the Wii disc.

        Returns:
            `bytes`: The Region Information of the Wii disc.
        '''
        if self.region_info is None:
            self.region_info = self.read_file(0x4E000, 32)
        return self.region_info

    def parse_header(self):
        '''Return a parsed version of the `Header <https://wiibrew.org/wiki/Wii_disc#Header>`_ of the Wii disc.

        Returns:
            `dict`: A parsed version of the Header of the Wii disc.
        '''
        # set things up
        data = self.get_header()
        out = dict()

        # parse raw Header data
        out['game_code'] =                 data[0x0000 : 0x0004] # Game Code "XYYZ": X = Console ID, YY = Game Code, Z = Country Code
        out['maker_code'] =                data[0x0004 : 0x0006] # Maker Code
        out['disk_id'] =                   data[0x0006]          # Disk ID
        out['version'] =                   data[0x0007]          # Version
        out['audio_streaming'] =           data[0x0008]          # Audio Streaming
        out['stream_buffer_size'] =        data[0x0009]          # Stream Buffer Size
        out['offsets_0x000A_0x0017'] =     data[0x000A : 0x0018] # Unused (should be 0s)
        out['wii_magic_word'] =            data[0x0018 : 0x001C] # Wii Magic Word (should be 0x5d1c9ea3)
        out['gc_magic_word'] =             data[0x001C : 0x0020] # GameCube Magic Word (should be 0s on Wii discs)
        out['game_name'] =                 data[0x0020 : 0x0060] # Game Name
        out['disable_hash_verification'] = data[0x0060]          # Disable Hash Verification
        out['disable_disc_encryption'] =   data[0x0061]          # Disable Disc Encryption and H3 Hash Table Load/Verification
        out['offsets_0x0062_0x007F'] =     data[0x0062 : 0x0080] # Unknown
        out['offsets_0x0080_0x043F'] =     data[0x0080 : 0x0440] # Unushed (should be 0s)

        # clean strings
        for k in ['game_code', 'maker_code', 'game_name']:
            try:
                out[k] = clean_string(out[k])
            except:
                warn("Unable to parse Header '%s' as string: %s" % (k, out[k]))

        # return final parsed data
        return out

    def parse_partitions_info(self):
        '''Return a parsed version of the `Partitions Information <https://wiibrew.org/wiki/Wii_disc#Partitions_information>`_ of the Wii disc.

        Returns:
            `list` of `dict`: A parsed version of the Partitions Information of the Wii disc.
        '''
        # set things up
        data = self.get_partitions_info()
        out = [dict(), dict(), dict(), dict()]

        # parse raw Partitions Information data
        out[0]['num_partitions'] = unpack('>I', data[0 : 4])[0]        # Number of 1st Partitions
        out[0]['table_offset'] =   unpack('>I', data[4 : 8])[0]   << 2 # 1st Partitions Info Table Offset
        out[1]['num_partitions'] = unpack('>I', data[8 : 12])[0]       # Number of 2nd Partitions
        out[1]['table_offset'] =   unpack('>I', data[12 : 16])[0] << 2 # 2nd Partitions Info Table Offset
        out[2]['num_partitions'] = unpack('>I', data[16 : 20])[0]      # Number of 3rd Partitions
        out[2]['table_offset'] =   unpack('>I', data[20 : 24])[0] << 2 # 3rd Partitions Info Table Offset
        out[3]['num_partitions'] = unpack('>I', data[24 : 28])[0]      # Number of 4th Partitions
        out[3]['table_offset'] =   unpack('>I', data[28 : 32])[0] << 2 # 4th Partitions Info Table Offset

        # return final parsed data
        return out

    def parse_partition_tables(self):
        '''Return a parsed version of the `Partition Tables <https://wiibrew.org/wiki/Wii_disc#Partition_table_entry>` of the Wii disc.

        Returns:
            `list` of `dict`: A parsed version of the Partition Tables
        '''
        # set things up
        raw_tables = self.get_partition_tables()
        out = list()

        # parse raw Partition Table data
        for table_num, data in enumerate(raw_tables):
            partitions = list()
            for i in range(0, len(data), 8):
                partitions.append({
                    'offset': unpack('>I', data[i : i + 4])[0] << 2, # Partition Offset
                    'type':   unpack('>I', data[i + 4 : i + 8])[0],  # Partition Type (0 = Data Partition, 1 = Update Partition, 2 = Channel Installer)
                })
            out.append(partitions)
        
        # return final parsed data
        return out

    def parse_region_info(self):
        '''Return a parsed version of the `Region Information <https://wiibrew.org/wiki/Wii_disc#Region_setting>`_ of the Wii disc.

        Returns:
            `dict`: A parsed version of the Region Information of the Wii disc.
        '''
        # set things up
        data = self.get_region_info()
        out = dict()

        # parse raw Region Information data
        out['region'] =                  unpack('>I', data[0x00 : 0x04])[0] # Region (0 = Japan/Taiwan, 1 = USA, 2 = PAL, 4 = Korea)
        out['offsets_0x04_0x0F'] =       data[0x04 : 0x10]                  # Unused(?)
        out['age_rating_japan_taiwan'] = data[0x10]                         # Age Rating: Japan/Taiwan
        out['age_rating_usa'] =          data[0x11]                         # Age Rating: USA
        out['offset_0x12'] =             data[0x12]                         # Unused(?)
        out['age_rating_germany'] =      data[0x13]                         # Age Rating: Germany
        out['age_rating_pegi'] =         data[0x14]                         # Age Rating: PEGI
        out['age_rating_finland'] =      data[0x15]                         # Age Rating: Finland
        out['age_rating_portugal'] =     data[0x16]                         # Age Rating: Portugal
        out['age_rating_britain'] =      data[0x17]                         # Age Rating: Britain
        out['age_rating_australia'] =    data[0x18]                         # Age Rating: Australia
        out['age_rating_korea'] =        data[0x19]                         # Age Rating: Korea
        out['offsets_0x1A_0x1F'] =       data[0x1A : 0x20]                  # Unused(?)

        # parse region byte
        try:
            out['region'] = REGION[out['region']]
        except:
            warn("Unable to parse region byte: %s" % out['region'])

        # return final parsed data
        return out

    def __iter__(self):
        # parse each partition table
        for partitions_num, parsed_partition_table in enumerate(self.parse_partition_tables()):
            partitions_path = Path('partitions_%d' % (partitions_num+1))
            yield (partitions_path, None, None)

            # parse each partition in the partition table
            for partition_num, partition in enumerate(parsed_partition_table):
                # load partition header
                try:
                    partition_type = PARTITION_TYPE[partition['type']]
                except:
                    partition_type = 'type%d' % partition['type']
                partition_path = partitions_path / ('partition_%d_%s' % (partition_num+1, partition_type))
                yield (partition_path, None, None)
                partition_header = self.read_file(partition['offset'], 0x02C0)
                partition_header_path = partition_path / 'partition_header'

                # parse partition header: ticket
                ticket = partition_header[0x0000 : 0x02A4]
                yield (partition_header_path / 'ticket.tik', None, ticket)

                # parse partition header: TMD
                tmd_size =   unpack('>I', partition_header[0x02A4 : 0x02A8])[0]
                tmd_offset = unpack('>I', partition_header[0x02A8 : 0x02AC])[0] >> 2
                yield (partition_header_path / 'title.tmd', None, self.read_file(tmd_offset, tmd_size))

                # parse partition header: cert chain
                cert_chain_size =   unpack('>I', partition_header[0x02AC : 0x02B0])[0]
                cert_chain_offset = unpack('>I', partition_header[0x02B0 : 0x02B4])[0] >> 2
                yield (partition_header_path / 'cert.sys', None, self.read_file(cert_chain_offset, cert_chain_size))

                # parse partition header: H3 table
                h3_table_offset = unpack('>I', partition_header[0x02B4 : 0x02B8])[0] >> 2 # size is always 0x18000
                yield (partition_header_path / 'table.h3', None, self.read_file(h3_table_offset, 0x18000))

                # parse partition header: data
                partition_data_offset = unpack('>I', partition_header[0x02B8 : 0x02BC])[0] >> 2
                partition_data_size =   unpack('>I', partition_header[0x02BC : 0x02C0])[0] >> 2
                print(partition, partition_data_offset, partition_data_size) # TODO PARSE THIS PARTITION: https://wiibrew.org/wiki/Wii_disc#Partition
