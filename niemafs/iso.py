#! /usr/bin/env python
'''
Handle ISO (9660) file systems for optical discs: https://wiki.osdev.org/ISO_9660
'''

# NiemaFS imports
from niemafs.common import FileSystem

# imports
from pathlib import Path

# constants
ISO9660_PVD_MAGIC_WORD = bytes(ord(c) for c in 'CD001') # https://wiki.osdev.org/ISO_9660#Volume_Descriptors
MAGIC_WORD_SEARCH_SIZE = 50000 # magic word probably in first 50 KB; increase this if fail to find

class IsoFS(FileSystem):
    '''Class to represent an ISO (9660) optical disc'''
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
            `dict`: Keys are Volume Descriptor Type codes, and values are `bytes` of the corresponding volume descriptor. https://wiki.osdev.org/ISO_9660#Volume_Descriptor_Type_Codes
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

    def __iter__(self):
        print(self.get_volume_descriptor_set_terminator())
        raise NotImplementedError("TODO NEED TO IMPLEMENT")
