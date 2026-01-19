#! /usr/bin/env python
'''
Handle Nintendo Wii DVD file system
'''

# NiemaFS imports
from niemafs.common import clean_string, FileSystem
from niemafs.gcm import GcmFS

# imports
from datetime import datetime
from pathlib import Path
from struct import unpack
from warnings import warn

# constants
COMMON_KEY = [
    b"\xEB\xE4\x2A\x22\x5E\x85\x93\xE4\x48\xD9\xC5\x45\x73\x81\xAA\xF7", # Common Key: https://github.com/grp/Wii.py/blob/6978355656ac73aa73ef1eea0f52c50644010b56/title.py#L76
    b"\x63\xB8\x2B\xB4\xF4\x61\x4E\x2E\x13\xF2\xFE\xFB\xBA\x4C\x9B\x7E", # Korean Key: https://github.com/grp/Wii.py/blob/6978355656ac73aa73ef1eea0f52c50644010b56/title.py#L77
]
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
        self.volume_info = None      # Volume (Partitions) Information
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

    def get_volume_info(self):
        '''Return the `Volume (Partitions) Information <https://wiibrew.org/wiki/Wii_disc#Partitions_information>`_ of the Wii disc.

        Returns:
            `bytes`: The Volume (Partitions) Information of the Wii disc.
        '''
        if self.volume_info is None:
            self.volume_info = self.read_file(0x40000, 32)
        return self.volume_info

    def get_partition_tables(self):
        '''Return the `Partition Tables <https://wiibrew.org/wiki/Wii_disc#Partition_table_entry>`_ of the Wii disc.

        Returns:
            `list` of `bytes`: The Partition Tables of the Wii disc.
        '''
        if self.partition_tables is None:
            self.partition_tables = [self.read_file(parts_info['table_offset'], 8 * parts_info['num_partitions']) for parts_info in self.parse_volume_info()]
        return self.partition_tables

    def get_region_info(self):
        '''Return the `Region Information <https://wiibrew.org/wiki/Wii_disc#Region_setting>`_ of the Wii disc.

        Returns:
            `bytes`: The Region Information of the Wii disc.
        '''
        if self.region_info is None:
            self.region_info = self.read_file(0x4E000, 32)
        return self.region_info

    def parse_header(data):
        '''Return a parsed version of the `Header <https://wiibrew.org/wiki/Wii_disc#Header>`_ of the Wii disc or partition.

        Returns:
            `dict`: A parsed version of the Header of the Wii disc or partition.
        '''
        # set things up
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

    def parse_volume_info(self):
        '''Return a parsed version of the `Volume (Partitions) Information <https://wiibrew.org/wiki/Wii_disc#Partitions_information>`_ of the Wii disc.

        Returns:
            `list` of `dict`: A parsed version of the Volume (Partitions) Information of the Wii disc.
        '''
        # set things up
        data = self.get_volume_info()
        out = [dict(), dict(), dict(), dict()]

        # parse raw Volume (Partitions) Information data
        out[0]['num_partitions'] = unpack('>I', data[0 : 4])[0]        # Number of Volume 0 Partitions
        out[0]['table_offset'] =   unpack('>I', data[4 : 8])[0]   << 2 # Volume 0 Info Table Offset
        out[1]['num_partitions'] = unpack('>I', data[8 : 12])[0]       # Number of Volume 1 Partitions
        out[1]['table_offset'] =   unpack('>I', data[12 : 16])[0] << 2 # Volum2 1 Info Table Offset
        out[2]['num_partitions'] = unpack('>I', data[16 : 20])[0]      # Number of Volume 2 Partitions
        out[2]['table_offset'] =   unpack('>I', data[20 : 24])[0] << 2 # Volume 2 Info Table Offset
        out[3]['num_partitions'] = unpack('>I', data[24 : 28])[0]      # Number of Volume 3 Partitions
        out[3]['table_offset'] =   unpack('>I', data[28 : 32])[0] << 2 # Volume 3 Info Table Offset

        # return final parsed data
        return out

    def parse_partition_tables(self):
        '''Return a parsed version of the `Partition Tables <https://wiibrew.org/wiki/Wii_disc#Partition_table_entry>`_ of the Wii disc.

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

    def parse_ticket(data):
        '''Return a parsed version of a `Ticket <https://wiibrew.org/wiki/Ticket>`_ of the Wii disc.

        Args:
            `data` (`bytes`): The raw Ticket data.

        Returns:
            `dict`: A parsed version of a Ticket of the Wii disc.
        '''
        # set things up
        out = dict()

        # parse Signed Blob Header: https://wiibrew.org/wiki/Ticket#Signed_blob_header
        out['signature_type'] =        data[0x0000 : 0x0004] # Signature Type (0x10001 for RSA-2048)
        out['signature_by_cert_key'] = data[0x0004 : 0x0104] # Signature by a Certificate's Key
        out['padding_module_64'] =     data[0x0104 : 0x0140] # Padding Module 64

        # parse v0 Ticket: https://wiibrew.org/wiki/Ticket#Signed_blob_header
        out['signature_issuer'] =           data[0x0140 : 0x0180]                  # Signature Issuer
        out['ecdh'] =                       data[0x0180 : 0x01BC]                  # ECDH Data (used to generate one-time key during install of console specific titles)
        out['ticket_format_version'] =      data[0x01BC]                           # Ticket Format Version
        out['offsets_0x01BD_0x01BE'] =      data[0x01BD : 0x01BF]                  # Reserved
        out['title_key'] =                  data[0x01BF : 0x01CF]                  # Title Key (encrypted by Common Key)
        out['offset_0x01CF'] =              data[0x01CF]                           # Unknown
        out['ticket_id'] =                  data[0x01D0 : 0x01D8]                  # Ticket ID (used as Initialization Vector (IV) for title key decryption of console specific titles)
        out['console_id'] =                 data[0x01D8 : 0x01DC]                  # Console ID (NG ID in console specific titles: https://wiibrew.org/wiki/Hardware/OTP)
        out['title_id'] =                   data[0x01DC : 0x01E4]                  # Title ID (used as Initialization Vector (IV) for AES-CBC encryption)
        out['offsets_0x01E4_0x01E5'] =      data[0x01E4 : 0x01E6]                  # Unknown (usually 0xFFFF)
        out['ticket_title_version'] =       unpack('>H', data[0x01E6 : 0x01E8])[0] # Ticket Title Version
        out['permitted_titles_mask'] =      data[0x01E8 : 0x01EC]                  # Permitted Titles Mask
        out['permit_mask'] =                data[0x01EC : 0x01F0]                  # Permit Mask (disk title is ANDed with inverse of this mask to see if result matches Permitted Titles Mask)
        out['title_export_allowed'] =       data[0x01F0]                           # Title Export allowed using PRNG key (1 = allowed, 0 = not allowed)
        out['common_key_index'] =           data[0x01F1]                           # Common Key Index (0 = Common Key, 1 = Korean Key, 2 = Wii U Wii Mode)
        out['offsets_0x01F2_0x01F4'] =      data[0x01F2 : 0x01F5]                  # Unknown
        out['offsets_0x01F5_0x0221'] =      data[0x01F5 : 0x0222]                  # Unknown
        out['content_access_permissions'] = data[0x0222 : 0x0262]                  # Content Access Permissions (1 bit for each content)
        out['offsets_0x0262_0x0263'] =      data[0x0262 : 0x0264]                  # Padding (always 0s)
        out['limit_type_1'] =               unpack('>I', data[0x0264 : 0x0268])[0] # Limit Type 1 (0 = disable, 1 = time limit (minutes), 3 = disable, 4 = launch count limit)
        out['max_usage_1'] =                unpack('>I', data[0x0268 : 0x026C])[0] # Maximum Usage 1 (depending on limit type)
        out['limit_type_2'] =               unpack('>I', data[0x026C : 0x0270])[0] # Limit Type 2
        out['max_usage_2'] =                unpack('>I', data[0x0270 : 0x0274])[0] # Maximum Usage 2
        out['limit_type_3'] =               unpack('>I', data[0x0274 : 0x0278])[0] # Limit Type 3
        out['max_usage_3'] =                unpack('>I', data[0x0278 : 0x027C])[0] # Maximum Usage 3
        out['limit_type_4'] =               unpack('>I', data[0x027C : 0x0280])[0] # Limit Type 4
        out['max_usage_4'] =                unpack('>I', data[0x0280 : 0x0284])[0] # Maximum Usage 4
        out['limit_type_5'] =               unpack('>I', data[0x0284 : 0x0288])[0] # Limit Type 5
        out['max_usage_5'] =                unpack('>I', data[0x0288 : 0x028C])[0] # Maximum Usage 5
        out['limit_type_6'] =               unpack('>I', data[0x028C : 0x0290])[0] # Limit Type 6
        out['max_usage_6'] =                unpack('>I', data[0x0290 : 0x0294])[0] # Maximum Usage 6
        out['limit_type_7'] =               unpack('>I', data[0x0294 : 0x0298])[0] # Limit Type 7
        out['max_usage_7'] =                unpack('>I', data[0x0298 : 0x029C])[0] # Maximum Usage 7
        out['limit_type_8'] =               unpack('>I', data[0x029C : 0x02A0])[0] # Limit Type 8
        out['max_usage_8'] =                unpack('>I', data[0x02A0 : 0x02A4])[0] # Maximum Usage 8

        # parse v1 Ticket: https://wiibrew.org/wiki/Ticket#v1_ticket
        if len(data) > 0x02A4:
            out['v1_header_version'] =         unpack('>H', data[0x02A4 : 0x02A6])[0] # v1 Ticket Header Version
            out['v1_header_size'] =            unpack('>H', data[0x02A6 : 0x02A8])[0] # v1 Ticket Header Size
            out['v1_ticket_size'] =            unpack('>I', data[0x02A8 : 0x02AC])[0] # v1 Ticket Size (0x14?)
            out['v1_section_headers_offset'] = unpack('>I', data[0x02AC : 0x02B0])[0] # v1 Offset of Section Headers
            out['v1_section_headers_count'] =  unpack('>H', data[0x02B0 : 0x02B2])[0] # v1 Number of Section Headers
            out['v1_section_headers_size'] =   unpack('>H', data[0x02B2 : 0x02B4])[0] # v1 Size of Each Section Header (0x14?)
            out['v1_misc_flags'] =             data[0x02B4 : 0x02B8]                  # v1 Miscellaneous Flags

        # clean strings
        for k in ['signature_issuer']:
            try:
                out[k] = clean_string(out[k])
            except:
                warn("Unable to parse Ticket '%s' as string: %s" % (k, out[k]))

        # return final parsed data
        return out

    def __iter__(self):
        # import PyCryptodome within WiiFS to allow people to use the other NiemaFS classes without it
        from Crypto.Cipher import AES

        # parse each partition table
        for volume_num, parsed_partition_table in enumerate(self.parse_partition_tables()):
            volume_path = Path('Volume %d' % volume_num)
            yield (volume_path, None, None)

            # parse each partition in the partition table
            for partition_num, partition in enumerate(parsed_partition_table):
                # load partition header
                try:
                    partition_type = PARTITION_TYPE[partition['type']]
                except:
                    partition_type = 'type%d' % partition['type']
                partition_header = self.read_file(partition['offset'], 0x02C0)

                # parse partition header: ticket
                ticket = partition_header[0x0000 : 0x02A4]
                parsed_ticket = WiiFS.parse_ticket(ticket)
                aes = AES.new(COMMON_KEY[parsed_ticket['common_key_index']], AES.MODE_CBC, parsed_ticket['title_id'] + (b'\x00'*8))
                decrypt_key = aes.decrypt(parsed_ticket['title_key'])

                # parse partition header: TMD
                tmd_size =   unpack('>I', partition_header[0x02A4 : 0x02A8])[0]
                tmd_offset = unpack('>I', partition_header[0x02A8 : 0x02AC])[0] << 2
                tmd = self.read_file(tmd_offset, tmd_size)

                # parse partition header: cert chain
                cert_chain_size =   unpack('>I', partition_header[0x02AC : 0x02B0])[0]
                cert_chain_offset = unpack('>I', partition_header[0x02B0 : 0x02B4])[0] << 2
                cert_chain = self.read_file(cert_chain_offset, cert_chain_size)

                # parse partition header: H3 table
                h3_table_offset = unpack('>I', partition_header[0x02B4 : 0x02B8])[0] << 2 # size is always 0x18000
                h3_table = self.read_file(h3_table_offset, 0x18000)

                # parse partition header: partition data location
                partition_data_offset = unpack('>I', partition_header[0x02B8 : 0x02BC])[0] << 2
                partition_data_size =   unpack('>I', partition_header[0x02BC : 0x02C0])[0] << 2

                # decrypt partition data: https://wiibrew.org/wiki/Wii_disc#Partition_Data
                data_start_offset = partition['offset'] + partition_data_offset
                data_end_offset = data_start_offset + partition_data_size
                if WiiFS.parse_header(self.get_header())['disable_disc_encryption'] == 0:
                    data_decrypted = b''
                    for cluster_offset in range(data_start_offset, data_end_offset, 0x8000):
                        cluster_data_encrypted = self.read_file(cluster_offset, 0x8000)
                        aes = AES.new(decrypt_key, AES.MODE_CBC, cluster_data_encrypted[0x3D0 : 0x3E0])
                        data_decrypted += aes.decrypt(cluster_data_encrypted[0x0400:])
                        if len(data_decrypted) > 0x00690000: # TODO DELETE
                            break # TODO DELETE
                else:
                    data_decrypted = self.read_file(data_start_offset, partition_data_size)

                # yield partition header data
                partition_header = WiiFS.parse_header(data_decrypted[0x0000 : 0x0420])
                partition_path = volume_path / ('Partition %d (%s) (%s%s) (%s)' % (partition_num, partition_type.capitalize(), partition_header['game_code'], partition_header['maker_code'], partition_header['game_name']))
                yield (partition_path, None, None)
                partition_header_path = partition_path / 'partition_header'
                yield (partition_header_path / 'ticket.bin', None, ticket)
                yield (partition_header_path / 'tmd.bin', None, tmd)
                yield (partition_header_path / 'cert.bin', None, cert_chain)
                yield (partition_header_path / 'h3.bin', None, h3_table)

                # parse decrypted data, similar to GameCube: https://github.com/niemasd/NiemaFS/blob/ffee20d1816de4f78cfabd9e16ca8038b2dabc07/niemafs/gcm.py#L204-L220
                fst_offset = unpack('>I', data_decrypted[0x0424 : 0x0428])[0] << 2 # Offset of FST
                file_entries = [GcmFS.parse_fst_entry(data_decrypted[fst_offset : fst_offset + 0x0C])] # root directory entry
                num_entries = file_entries[0]['length']
                string_table_start = 0x0C * num_entries
                string_table = data_decrypted[string_table_start:]
                file_entries += [GcmFS.parse_fst_entry(data_decrypted[i:i+0x0C]) for i in range(0x0C, string_table_start, 0x0C)] # rest of file entries
                print(file_entries)
