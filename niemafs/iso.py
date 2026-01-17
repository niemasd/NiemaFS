#! /usr/bin/env python
'''
Handle ISO 9660 file systems
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from datetime import datetime
from pathlib import Path
from struct import unpack
from warnings import warn

# constants
ISO9660_PVD_MAGIC_WORD = bytes(ord(c) for c in 'CD001') # https://wiki.osdev.org/ISO_9660#Volume_Descriptors
MAGIC_WORD_SEARCH_SIZE = 50000 # magic word probably in first 50 KB; increase this if fail to find

class IsoFS(FileSystem):
    '''Class to represent an `ISO 9660 <https://wiki.osdev.org/ISO_9660>`_ optical disc'''
    def __init__(self, file_obj, path=None):
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.sector_size = None
        self.system_area = None
        self.volume_descriptors = dict() # keys = Volume Descriptor Type codes, values = bytes: https://wiki.osdev.org/ISO_9660#Volume_Descriptor_Type_Codes

    def clean_string(s):
        '''Clean an ISO 9660 string by right-stripping 0x00 and spaces

        Args:
            `s` (`bytes`): The ISO 9660 string to clean

        Returns:
            `str`: The cleaned string
        '''
        return s.rstrip(b'\x00').decode().rstrip()

    def tz_offset_to_datetime_str(x):
        '''Convert an ISO 9660 timezone offset to a `datetime` format string

        Args:
            `x` (`int`): The ISO 9660 timezone offset.

        Returns:
            `str`: The `datetime` format string.
        '''
        tz_offset_hours = (x / 4) - 12
        tz_offset_sign = '-' if tz_offset_hours < 0 else '+'
        tz_offset_hh = str(abs(int(tz_offset_hours))).zfill(2)
        tz_offset_mm = str(int((abs(tz_offset_hours) % 1) * 60)).zfill(2)
        return '%s%s%s' % (tz_offset_sign, tz_offset_hh, tz_offset_mm)

    def parse_pvd_datetime(data):
        '''Parse a date/time in the `ISO 9660 Primary Volume Descriptor (PVD) date/time format <https://wiki.osdev.org/ISO_9660#Date/time_format>`_.

        Args:
            `data` (`bytes`): A date/time (exactly 17 bytes) in the ISO 9660 PVD date/time format.

        Returns:
            `datetime`: A Python `datetime` object.
        '''
        if len(data) != 17:
            raise ValueError("ISO 9660 PVD date/time must be exactly 17 bytes: %s" % data)
        dt_str = ''.join(str(v) if v < 48 else chr(v) for v in data[0:16]) + '0000' # chr(48) == '0'
        tz_offset_str = IsoFS.tz_offset_to_datetime_str(data[16])
        try:
            return datetime.strptime(dt_str + tz_offset_str, '%Y%m%d%H%M%S%f%z')
        except ValueError:
            return datetime.strptime(dt_str, '%Y%m%d%H%M%S%f') # timezone is sometimes messed up

    def parse_directory_datetime(data):
        '''Parse a date/time in the `ISO 9660 directory record date/time format <https://wiki.osdev.org/ISO_9660#Directories>.`_

        Args:
            `data` (`bytes`): A date/time (exactly 7 bytes) in the ISO 9660 directory record date/time format.

        Returns:
            `datetime`: A Python `datetime` object.
        '''
        dt_str = str(data[0] + 1900) + ''.join(str(x).zfill(2) for x in data[1:6])
        tz_offset_str = IsoFS.tz_offset_to_datetime_str(data[6])
        try:
            return datetime.strptime(dt_str + tz_offset_str, '%Y%m%d%H%M%S%f%z')
        except ValueError:
            return datetime.strptime(dt_str, '%Y%m%d%H%M%S%f') # timezone is sometimes messed up

    def parse_directory_record(data):
        '''Parse an `ISO 9660 directory record <https://wiki.osdev.org/ISO_9660#Directories>`_.

        Args:
            `data` (`bytes`): The raw bytes of the directory record.

        Returns:
            `dict`: The parsed directory record.
        '''
        # parse directory record data
        out = dict()
        out['directory_record_length'] =          data[0]                              # should be equal to len(data)
        out['extended_attribute_record_length'] = data[1]                              # extended attribute record length
        out['data_location_LE'] =                 unpack('<I', data[2:6])[0]           # location (LBA) of data (little-endian)
        out['data_location_BE'] =                 unpack('>I', data[6:10])[0]          # location (LBA) of data (big-endian) (should be equal to previous)
        out['data_length_LE'] =                   unpack('<I', data[10:14])[0]         # length of data (little-endian)
        out['data_length_BE'] =                   unpack('>I', data[14:18])[0]         # length of data (big-endian) (should be equal to previous)
        out['datetime'] =                         data[18:25]                          # recording date and time
        out['file_flags'] =                       data[25]                             # file flags
        out['interleave_file_unit_size'] =        data[26]                             # file unit size for files recorded in interleaved mode (otherwise 0)
        out['interleave_gap_size'] =              data[27]                             # gap size for files recorded in interleaved mode (otherwise 0)
        out['volume_sequence_number_LE'] =        unpack('<H', data[28:30])[0]         # volume this extent is recorded on (little-endian)
        out['volume_sequence_number_BE'] =        unpack('>H', data[30:32])[0]         # volume this extent is recorded on (big-endian) (should be equal to previous)
        out['filename_length'] =                  data[32]                             # length of filename (terminated with ';1' where 1 is file version number)
        out['filename'] =                         data[33 : 33+out['filename_length']] # filename (terminated with ';1' where 1 is file version number)
        # I'm skipping "padding field" and "system use" since they're not useful to me and non-trivial to code

        # parse file flags
        out['file_flags'] = {
            'is_hidden':                         bool(out['file_flags'] & 0b00000001),
            'is_directory':                      bool(out['file_flags'] & 0b00000010),
            'is_associated_file':                bool(out['file_flags'] & 0b00000100),
            'format_in_extended_attribute':      bool(out['file_flags'] & 0b00001000),
            'permissions_in_extended_attribute': bool(out['file_flags'] & 0b00010000),
            'reserved_5':                        bool(out['file_flags'] & 0b00100000),
            'reserved_6':                        bool(out['file_flags'] & 0b01000000),
            'not_final_directory':               bool(out['file_flags'] & 0b10000000),
        }

        # clean strings
        for k in ['filename']:
            try:
                out[k] = IsoFS.clean_string(out[k])
            except:
                warn("Unable to parse Directory Record '%s' as string: %s" % (k, out[k]))

        # parse date-times
        for k in ['datetime']:
            try:
                out[k] = IsoFS.parse_directory_datetime(out[k])
            except:
                warn("Unable to parse Directory Record '%s' as date-time: %s" % (k, out[k]))

        # return final parsed data
        return out

    def get_sector_size(self):
        '''Return the sector size of this ISO in bytes (usually 2048).

        Returns:
            `int`: The sector size of this ISO in bytes.
        '''
        if self.sector_size is None:
            start_offset = self.file.tell()
            self.file.seek(0)
            chunk = self.file.read(MAGIC_WORD_SEARCH_SIZE)
            self.file.seek(start_offset)
            magic_word_offset = chunk.find(ISO9660_PVD_MAGIC_WORD)
            if magic_word_offset == -1:
                raise ValueError("Failed to find ISO 9660 magic word 'CD001' in first %d bytes" % MAGIC_WORD_SEARCH_SIZE)
            self.sector_size = (magic_word_offset - 1) // 16
        return self.sector_size

    def get_system_area(self):
        '''Return the System Area (sectors 0x00-0x0F = first 16 sectors) of the ISO.

        Returns:
            `bytes`: The System Area (sectors 0x00-0x0F = first 16 sectors) of the ISO.
        '''
        if self.system_area is None:
            start_offset = self.file.tell()
            self.file.seek(0)
            self.system_area = self.file.read(16 * self.get_sector_size())
            self.file.seek(start_offset)
        return self.system_area

    def get_volume_descriptors(self):
        '''Return the Volume Descriptors of the ISO. 

        Returns:
            `dict`: Keys are `Volume Descriptor Type codes <https://wiki.osdev.org/ISO_9660#Volume_Descriptor_Type_Codes>`_, and values are `bytes` of the corresponding volume descriptor.
        '''
        if len(self.volume_descriptors) == 0:
            start_offset = self.file.tell()
            self.file.seek(16 * self.get_sector_size())
            while True:
                next_volume_descriptor = self.file.read(self.get_sector_size())
                self.volume_descriptors[next_volume_descriptor[0]] = next_volume_descriptor
                if next_volume_descriptor[0] == 255: # Volume Descriptor Set Terminator
                    break
            self.file.seek(start_offset)
        return self.volume_descriptors

    def get_boot_record(self):
        '''Return the Boot Record (Volume Descriptor code 0) of the ISO.

        Returns:
            `bytes`: The Boot Record (Volume Descriptor code 0) of the ISO, or `None` if the ISO does not have one.
        '''
        try:
            return self.get_volume_descriptors()[0]
        except KeyError:
            return None

    def get_primary_volume_descriptor(self):
        '''Return the Primary Volume Descriptor (PVD; Volume Descriptor code 1) of the ISO.

        Returns:
            `bytes`: The Primary Volume Descriptor (PVD; Volume Descriptor code 1) of the ISO, or `None` if the ISO does not have one.
        '''
        try:
            return self.get_volume_descriptors()[1]
        except KeyError:
            return None

    def get_supplementary_volume_descriptor(self):
        '''Return the Supplementary Volume Descriptor (Volume Descriptor code 2) of the ISO.

        Returns:
            `bytes`: The Supplementary Volume Descriptor (Volume Descriptor code 2) of the ISO, or `None` if the ISO does not have one.
        '''
        try:
            return self.get_volume_descriptors()[2]
        except KeyError:
            return None

    def get_volume_partition_descriptor(self):
        '''Return the Volume Partition Descriptor (Volume Descriptor code 3) of the ISO.

        Returns:
            `bytes`: The Volume Partition Descriptor (Volume Descriptor code 3) of the ISO, or `None` if the ISO does not have one.
        '''
        try:
            return self.get_volume_descriptors()[3]
        except KeyError:
            return None

    def get_volume_descriptor_set_terminator(self):
        '''Return the Volume Descriptor Set Terminator (Volume Descriptor code 0xFF = 255) of the ISO.

        Returns:
            `bytes`: The Volume Descriptor Set Terminator (Volume Descriptor code 0xFF = 255) of the ISO, or `None` if the ISO does not have one.
        '''
        try:
            return self.get_volume_descriptors()[255]
        except KeyError:
            raise ValueError("ISO does not have a Volume Descriptor Set Terminator")

    def parse_boot_record(self):
        '''Return a parsed version of the `Boot Record <https://wiki.osdev.org/ISO_9660#The_Boot_Record>`_ of the ISO.

        Returns:
            `dict`: A parsed version of the Boot Record of the ISO, or `None` if the ISO does not have one.
        '''
        # set things up
        br = self.get_boot_record()
        if br is None:
            return None
        out = dict()

        # parse raw Boot Record data
        out['type_code'] =              br[0]     # should always be 0
        out['identifier'] =             br[1:6]   # should always be "CD001"
        out['version'] =                br[6]     # should always be 1?
        out['boot_system_identifier'] = br[7:39]  # ID of the system which can act on and boot the system from the boot record
        out['boot_identifier'] =        br[39:71] # ID of the boot system defined in the rest of this descriptor
        out['boot_system_use'] =        br[71:]   # Custom - used by the boot system

        # clean strings
        for k in ['identifier', 'boot_system_identifier', 'boot_identifier']:
            try:
                out[k] = IsoFS.clean_string(out[k])
            except:
                warn("Unable to parse Boot Record '%s' as string: %s" % (k, out[k]))

        # return final parsed data
        return out

    def parse_primary_volume_descriptor(self):
        '''Return a parsed version of the `Primary Volume Descriptor (PVD) <https://wiki.osdev.org/ISO_9660#The_Primary_Volume_Descriptor>`_ of the ISO.

        Returns:
            `dict`: A parsed version of the Primary Volume Descriptor (PVD) of the ISO, or `None` if the ISO does not have one.
        '''
        # set things up
        pvd = self.get_primary_volume_descriptor()
        if pvd is None:
            return None
        out = dict()

        # parse raw PVD data
        out['type_code'] =                      pvd[0]                        # should always be 1
        out['identifier'] =                     pvd[1:6]                      # should always be "CD001"
        out['version'] =                        pvd[6]                        # should always be 1?
        out['offset_7'] =                       pvd[7]                        # should always be 0
        out['system_identifier'] =              pvd[8:40]                     # Name of the system that can act upon sectors 0x00-0x0F for the volume
        out['volume_identifier'] =              pvd[40:72]                    # Identification (label) of this volume
        out['offsets_72_79'] =                  pvd[72:80]                    # should always be all 0s
        out['volume_space_size_LE'] =           unpack('<I', pvd[80:84])[0]   # Volume Space Size (little-endian)
        out['volume_space_size_BE'] =           unpack('>I', pvd[84:88])[0]   # Volume Space Size (big-endian) (should be equal to previous)
        out['offsets_88_119'] =                 pvd[88:120]                   # should always be all 0s
        out['volume_set_size_LE'] =             unpack('<H', pvd[120:122])[0] # Volume Set Size (little-endian)
        out['volume_set_size_BE'] =             unpack('>H', pvd[122:124])[0] # Volume Set Size (big-endian) (should be equal to previous)
        out['volume_sequence_number_LE'] =      unpack('<H', pvd[124:126])[0] # Volume Sequence Number (little-endian)
        out['volume_sequence_number_BE'] =      unpack('>H', pvd[126:128])[0] # Volume Sequence Number (big-endian) (should be equal to previous)
        out['logical_block_size_LE'] =          unpack('<H', pvd[128:130])[0] # Logical Block Size (little-endian)
        out['logical_block_size_BE'] =          unpack('>H', pvd[130:132])[0] # Logical Block Size (big-endian) (should be equal to previous)
        out['path_table_size_LE'] =             unpack('<I', pvd[132:136])[0] # Path Table Size (little-endian)
        out['path_table_size_BE'] =             unpack('>I', pvd[136:140])[0] # Path Table Size (big-endian) (should be equal to previous)
        out['location_L_path_table'] =          unpack('<I', pvd[140:144])[0] # Location of Type-L Path Table
        out['location_optional_L_path_table'] = unpack('<I', pvd[144:148])[0] # Location of Optional Type-L Path Table
        out['location_M_path_table'] =          unpack('>I', pvd[148:152])[0] # Location of Type-M Path Table
        out['location_optional_M_path_table'] = unpack('>I', pvd[152:156])[0] # Location of Optional Type-M Path Table
        out['root_directory_entry'] =           pvd[156:190]                  # Directory Entry for Root Directory
        out['volume_set_identifier'] =          pvd[190:318]                  # Volume Set Identifier
        out['publisher_identifier'] =           pvd[318:446]                  # Publisher Identifier
        out['data_preparer_identifier'] =       pvd[446:574]                  # Data Preparer Identifier
        out['application_identifier'] =         pvd[574:702]                  # Application Identifier
        out['copyright_file_identifier'] =      pvd[702:739]                  # Copyright File Identifier
        out['abstract_file_identifier'] =       pvd[739:776]                  # Abstract File Identifier
        out['bibliographic_file_identifier'] =  pvd[776:813]                  # Bibliographic File Identifier
        out['volume_creation_datetime'] =       pvd[813:830]                  # Volume Creation Date and Time
        out['volume_modification_datetime'] =   pvd[830:847]                  # Volume Modification Date and Time
        out['volume_expiration_datetime'] =     pvd[847:864]                  # Volume Expiration Date and Time
        out['volume_effective_datetime'] =      pvd[864:881]                  # Volume Effective Date and Time
        out['file_structure_version'] =         pvd[881]                      # File Structure Version (should always be 1)
        out['offset_882'] =                     pvd[882]                      # should always be 0
        out['application_used'] =               pvd[883:1395]                 # Application Used (not defined by ISO 9660)
        out['reserved'] =                       pvd[1395:2048]                # Reserved by ISO
        out['error_detection_correction'] =     pvd[2048:]                    # Error Detection and Correction (EDAC) codes (if sector size > 2048)

        # clean strings
        for k in ['identifier', 'system_identifier', 'volume_identifier', 'volume_set_identifier', 'publisher_identifier', 'data_preparer_identifier', 'application_identifier', 'copyright_file_identifier', 'abstract_file_identifier', 'bibliographic_file_identifier']:
            try:
                out[k] = IsoFS.clean_string(out[k])
            except:
                warn("Unable to parse Primary Volume Descriptor '%s' as string: %s" % (k, out[k]))

        # parse date-times
        for k in ['volume_creation_datetime', 'volume_modification_datetime', 'volume_expiration_datetime', 'volume_effective_datetime']:
            try:
                out[k] = IsoFS.parse_pvd_datetime(out[k])
            except:
                warn("Unable to parse PVD '%s' as date-time: %s" % (k, out[k]))

        # parse root directory entry (this must succeed to be able to parse files in this ISO)
        out['root_directory_entry'] = IsoFS.parse_directory_record(out['root_directory_entry'])

        # return final parsed data
        return out

    def parse_volume_descriptor_set_terminator(self):
        '''Return a parsed version of the `Volume Descriptor Set Terminator <https://wiki.osdev.org/ISO_9660#Volume_Descriptor_Set_Terminator>`_ of the ISO.

        Returns:
            `dict`: A parsed version of the Volume Descriptor Set Terminator of the ISO, or `None` if the ISO does not have one.
        '''
        # set things up
        vdst = self.get_volume_descriptor_set_terminator()
        if vdst is None:
            return None
        out = dict()

        # parse raw VDST data
        out['type_code'] =  vdst[0]   # should always be 255
        out['identifier'] = vdst[1:6] # should always be "CD001"
        out['version'] =    vdst[6]   # should always be 1
        out['unused'] =     vdst[7:]  # remaining bytes are not part of ISO 9660

        # clean strings
        for k in ['identifier']:
            try:
                out[k] = IsoFS.clean_string(out[k])
            except:
                warn("Unable to parse Volume Descriptor Set Terminator '%s' as string: %s" % (k, out[k]))

        # return final parsed data
        return out

    def __iter__(self):
        # load root directory entry from PVD
        start_offset = self.file.tell()
        pvd = self.parse_primary_volume_descriptor()
        to_visit = [(Path(''), pvd['root_directory_entry'])] # (Path, directory entry) tuples

        # perform search starting from root directory (only contains directories, not files)
        while len(to_visit) != 0:
            # handle current directory
            curr_path, curr_directory_entry = to_visit.pop()
            if curr_path != Path(''):
                yield (curr_path, curr_directory_entry['datetime'], None)

            # parse directory data for this directory entry for sub-files/directories
            self.file.seek(curr_directory_entry['data_location_LE'] * self.sector_size)
            curr_data = self.file.read(curr_directory_entry['data_length_LE'])
            ind = 0
            while True:
                # load next entry if not at end of this directory
                next_len = curr_data[ind]
                if next_len == 0:
                    break
                next_entry = IsoFS.parse_directory_record(curr_data[ind:ind+next_len])
                next_entry_fn = next_entry['filename']

                # next entry is a directory (add it to `to_visit`)
                if next_entry['file_flags']['is_directory']:
                    if next_entry_fn not in {'', '\x01'}: # ignore '.' (current) and '..' (parent)
                        to_visit.append((curr_path / next_entry_fn, next_entry))

                # next entry is a file (yield it)
                else:
                    self.file.seek(next_entry['data_location_LE'] * self.sector_size)
                    next_data = self.file.read(next_entry['data_length_LE'])
                    yield (curr_path / next_entry_fn, next_entry['datetime'], next_data)
                ind += next_len
        self.file.seek(start_offset)
