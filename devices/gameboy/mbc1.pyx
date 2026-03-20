# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""MBC1 support for Game Boy cartridges with bank switching."""

from __future__ import annotations


cdef class MBC1:
    """Implements the basic ROM banking behavior of the MBC1 mapper."""

    ROM_BANK_SIZE = 0x4000
    RAM_BANK_SIZE = 0x2000
    RAM_SIZE_BY_CODE = {
        0x00: 0,
        0x01: 0x800,
        0x02: 0x2000,
        0x03: 0x8000,
        0x04: 0x20000,
        0x05: 0x10000,
    }

    cdef public bytes rom_data
    cdef public int rom_bank_count, ram_size
    cdef public bytearray ram
    cdef public bint ram_enabled
    cdef public int lower_bank_bits, upper_bank_bits, bank_mode

    def __init__(self, bytes rom_data, *, int ram_size_code=0x00):
        self.rom_data = rom_data
        self.rom_bank_count = max(1, len(rom_data) // self.ROM_BANK_SIZE)
        self.ram_size = self.RAM_SIZE_BY_CODE.get(ram_size_code, 0)
        self.ram = bytearray(self.ram_size)
        self.ram_enabled = False
        self.lower_bank_bits = 1
        self.upper_bank_bits = 0
        self.bank_mode = 0

    cpdef void reset(self):
        self.ram_enabled = False
        self.lower_bank_bits = 1
        self.upper_bank_bits = 0
        self.bank_mode = 0

    cdef inline int _normalize_bank(self, int bank):
        bank %= self.rom_bank_count
        if bank == 0 and self.rom_bank_count > 1:
            bank = 1
        return bank

    cdef inline int _current_low_region_bank(self):
        if self.bank_mode == 0:
            return 0
        return self._normalize_bank((self.upper_bank_bits & 0x03) << 5)

    cdef inline int _current_high_region_bank(self):
        cdef int bank = (self.lower_bank_bits & 0x1F) | ((self.upper_bank_bits & 0x03) << 5)
        if (bank & 0x1F) == 0:
            bank |= 0x01
        return self._normalize_bank(bank)

    cdef inline int _current_ram_bank(self):
        cdef int bank_count
        if self.bank_mode == 0 or self.ram_size == 0:
            return 0
        bank_count = max(1, self.ram_size // self.RAM_BANK_SIZE)
        return (self.upper_bank_bits & 0x03) % bank_count

    cpdef int read(self, int addr):
        cdef int bank, offset
        addr &= 0xFFFF
        if 0x0000 <= addr < 0x4000:
            bank = self._current_low_region_bank()
            offset = bank * self.ROM_BANK_SIZE + addr
            return self.rom_data[offset] if offset < len(self.rom_data) else 0xFF
        if 0x4000 <= addr < 0x8000:
            bank = self._current_high_region_bank()
            offset = bank * self.ROM_BANK_SIZE + (addr - 0x4000)
            return self.rom_data[offset] if offset < len(self.rom_data) else 0xFF
        if 0xA000 <= addr < 0xC000:
            if not self.ram_enabled or self.ram_size == 0:
                return 0xFF
            bank = self._current_ram_bank()
            offset = bank * self.RAM_BANK_SIZE + (addr - 0xA000)
            return self.ram[offset] if offset < len(self.ram) else 0xFF
        return 0xFF

    cpdef void write(self, int addr, int value):
        cdef int bank, offset
        addr &= 0xFFFF
        value &= 0xFF
        if 0x0000 <= addr < 0x2000:
            self.ram_enabled = (value & 0x0F) == 0x0A
        elif 0x2000 <= addr < 0x4000:
            self.lower_bank_bits = value & 0x1F
            if self.lower_bank_bits == 0:
                self.lower_bank_bits = 1
        elif 0x4000 <= addr < 0x6000:
            self.upper_bank_bits = value & 0x03
        elif 0x6000 <= addr < 0x8000:
            self.bank_mode = value & 0x01
        elif 0xA000 <= addr < 0xC000:
            if not self.ram_enabled or self.ram_size == 0:
                return
            bank = self._current_ram_bank()
            offset = bank * self.RAM_BANK_SIZE + (addr - 0xA000)
            if offset < len(self.ram):
                self.ram[offset] = value
