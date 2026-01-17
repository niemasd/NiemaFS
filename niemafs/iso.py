#! /usr/bin/env python
'''
Handle ISO 9660 file systems
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from pathlib import Path
from struct import unpack

# constants
ISO9660_PVD_MAGIC_WORD = bytes(ord(c) for c in 'CD001') # https://wiki.osdev.org/ISO_9660#Volume_Descriptors
MAGIC_WORD_SEARCH_SIZE = 50000 # magic word probably in first 50 KB; increase this if fail to find

def parse_dec_datetime(data):
    '''Parse a date/time in the `ISO 9660 Primary Volume Descriptor (PVD) date/time format <https://wiki.osdev.org/ISO_9660#Date/time_format>`_ as a Python `datetime` object.

    Args:
        `data` (`bytes`): A date/time (exactly 17 bytes) in the ISO 9660 PVD date/time format.

    Returns:
        `datetime`: A Python `datetime` object.
    '''
    if len(data) != 17:
        raise ValueError("ISO 9660 PVD date/time must be exactly 17 bytes: %s" % data)
    raise NotImplementedError("TODO https://wiki.osdev.org/ISO_9660#Date/time_format") # TODO

class IsoFS(FileSystem):
    '''Class to represent an `ISO 9660 <https://wiki.osdev.org/ISO_9660>`_ optical disc'''
    def __init__(self, file_obj, path=None):
        if file_obj is None:
            raise ValueError("file_obj must be a file-like")
        super().__init__(path=path, file_obj=file_obj)
        self.sector_size = None
        self.system_area = None
        self.volume_descriptors = dict() # keys = Volume Descriptor Type codes, values = bytes: https://wiki.osdev.org/ISO_9660#Volume_Descriptor_Type_Codes

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
        boot_record = self.get_boot_record()
        if boot_record is None:
            return None
        return {
            'type_code':              boot_record[0],                       # should always be 0
            'identifier':             boot_record[1:6].decode().rstrip(),   # should always be "CD001"
            'version':                boot_record[6],                       # should always be 1?
            'boot_system_identifier': boot_record[7:39].decode().rstrip(),  # ID of the system which can act on and boot the system from the boot record
            'boot_identifier':        boot_record[39:71].decode().rstrip(), # ID of the boot system defined in the rest of this descriptor
            'boot_system_use':        boot_record[71:],                     # Custom - used by the boot system
        }

    def parse_primary_volume_descriptor(self):
        '''Return a parsed version of the `Primary Volume Descriptor (PVD) <https://wiki.osdev.org/ISO_9660#The_Primary_Volume_Descriptor>`_ of the ISO.

        Returns:
            `dict`: A parsed version of the Primary Volume Descriptor (PVD) of the ISO, or `None` if the ISO does not have one.
        '''
        pvd = self.get_primary_volume_descriptor()
        if pvd is None:
            return None
        return {
            'type_code':                      pvd[0],                           # should always be 1
            'identifier':                     pvd[1:6].decode().rstrip(),       # should always be "CD001"
            'version':                        pvd[6],                           # should always be 1?
            'offset_7':                       pvd[7],                           # should always be 0
            'system_identifier':              pvd[8:40].decode().rstrip(),      # Name of the system that can act upon sectors 0x00-0x0F for the volume
            'volume_identifier':              pvd[40:72].decode().rstrip(),     # Identification (label) of this volume
            'offsets_72_79':                  pvd[72:80],                       # should always be all 0s
            'volume_space_size_LE':           unpack('<I', pvd[80:84])[0],      # Volume Space Size (little-endian)
            'volume_space_size_BE':           unpack('>I', pvd[84:88])[0],      # Volume Space Size (big-endian) (should be equal to previous)
            'offsets_88_119':                 pvd[88:120],                      # should always be all 0s
            'volume_set_size_LE':             unpack('<H', pvd[120:122])[0],    # Volume Set Size (little-endian)
            'volume_set_size_BE':             unpack('>H', pvd[122:124])[0],    # Volume Set Size (big-endian) (should be equal to previous)
            'volume_sequence_number_LE':      unpack('<H', pvd[124:126])[0],    # Volume Sequence Number (little-endian)
            'volume_sequence_number_BE':      unpack('>H', pvd[126:128])[0],    # Volume Sequence Number (big-endian) (should be equal to previous)
            'logical_block_size_LE':          unpack('<H', pvd[128:130])[0],    # Logical Block Size (little-endian)
            'logical_block_size_BE':          unpack('>H', pvd[130:132])[0],    # Logical Block Size (big-endian) (should be equal to previous)
            'path_table_size_LE':             unpack('<I', pvd[132:136])[0],    # Path Table Size (little-endian)
            'path_table_size_BE':             unpack('>I', pvd[136:140])[0],    # Path Table Size (big-endian) (should be equal to previous)
            'location_L_path_table':          unpack('<I', pvd[140:144])[0],    # Location of Type-L Path Table
            'location_optional_L_path_table': unpack('<I', pvd[144:148])[0],    # Location of Optional Type-L Path Table
            'location_M_path_table':          unpack('>I', pvd[148:152])[0],    # Location of Type-M Path Table
            'location_optional_M_path_table': unpack('>I', pvd[152:156])[0],    # Location of Optional Type-M Path Table
            'root_directory_entry':           pvd[156:190],                     # Directory Entry for Root Directory
            'volume_set_identifier':          pvd[190:318].decode().rstrip(),   # Volume Set Identifier
            'publisher_identifier':           pvd[318:446].decode().rstrip(),   # Publisher Identifier
            'data_preparer_identifier':       pvd[446:574].decode().rstrip(),   # Data Preparer Identifier
            'application_identifier':         pvd[574:702].decode().rstrip(),   # Application Identifier
            'copyright_file_identifier':      pvd[702:739].decode().rstrip(),   # Copyright File Identifier
            'abstract_file_identifier':       pvd[739:776].decode().rstrip(),   # Abstract File Identifier
            'bibliographic_file_identifier':  pvd[776:813].decode().rstrip(),   # Bibliographic File Identifier
            'volume_creation_datetime':       parse_dec_datetime(pvd[813:830]), # Volume Creation Date and Time
        } # TODO FINISH REST OF PVD: https://wiki.osdev.org/ISO_9660#The_Primary_Volume_Descriptor

    def __iter__(self):
        print(self.parse_primary_volume_descriptor())
        raise NotImplementedError("TODO NEED TO IMPLEMENT")
