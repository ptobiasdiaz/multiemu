# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""MBC2 support for Game Boy cartridges with 4-bit internal RAM."""

from __future__ import annotations


cdef class MBC2:
    """Implements the common MBC2 banking behavior."""

    ROM_BANK_SIZE = 0x4000
    RAM_SIZE = 0x200

    cdef public bytes rom_data
    cdef public int rom_bank_count, rom_bank
    cdef public bytearray ram
    cdef public bint ram_enabled

    def __init__(self, bytes rom_data):
        self.rom_data = rom_data
        self.rom_bank_count = max(1, len(rom_data) // self.ROM_BANK_SIZE)
        self.ram = bytearray(self.RAM_SIZE)
        self.reset()

    cpdef void reset(self):
        self.ram_enabled = False
        self.rom_bank = 1

    cdef inline int _normalize_rom_bank(self, int bank):
        bank &= 0x0F
        bank %= self.rom_bank_count
        if bank == 0 and self.rom_bank_count > 1:
            bank = 1
        return bank

    cpdef int read(self, int addr):
        cdef int bank, offset
        addr &= 0xFFFF
        if 0x0000 <= addr < 0x4000:
            return self.rom_data[addr] if addr < len(self.rom_data) else 0xFF
        if 0x4000 <= addr < 0x8000:
            bank = self._normalize_rom_bank(self.rom_bank)
            offset = bank * self.ROM_BANK_SIZE + (addr - 0x4000)
            return self.rom_data[offset] if offset < len(self.rom_data) else 0xFF
        if 0xA000 <= addr < 0xC000:
            if not self.ram_enabled:
                return 0xFF
            offset = (addr - 0xA000) & 0x01FF
            return 0xF0 | (self.ram[offset] & 0x0F)
        return 0xFF

    cpdef void write(self, int addr, int value):
        cdef int offset
        addr &= 0xFFFF
        value &= 0xFF
        if 0x0000 <= addr < 0x4000:
            if addr & 0x0100:
                self.rom_bank = self._normalize_rom_bank(value)
            else:
                self.ram_enabled = (value & 0x0F) == 0x0A
            return
        if 0xA000 <= addr < 0xC000:
            if not self.ram_enabled:
                return
            offset = (addr - 0xA000) & 0x01FF
            self.ram[offset] = value & 0x0F
