"""MBC1 support for Game Boy cartridges with bank switching."""

from __future__ import annotations


class MBC1:
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

    def __init__(self, rom_data: bytes, *, ram_size_code: int = 0x00):
        self.rom_data = rom_data
        self.rom_bank_count = max(1, len(rom_data) // self.ROM_BANK_SIZE)
        self.ram_size = self.RAM_SIZE_BY_CODE.get(ram_size_code, 0)
        self.ram = bytearray(self.ram_size)
        self.ram_enabled = False
        self.lower_bank_bits = 1
        self.upper_bank_bits = 0
        self.bank_mode = 0

    def reset(self) -> None:
        self.ram_enabled = False
        self.lower_bank_bits = 1
        self.upper_bank_bits = 0
        self.bank_mode = 0

    def _normalize_bank(self, bank: int) -> int:
        bank %= self.rom_bank_count
        if bank == 0 and self.rom_bank_count > 1:
            bank = 1
        return bank

    def _current_low_region_bank(self) -> int:
        if self.bank_mode == 0:
            return 0
        return self._normalize_bank((self.upper_bank_bits & 0x03) << 5)

    def _current_high_region_bank(self) -> int:
        bank = (self.lower_bank_bits & 0x1F) | ((self.upper_bank_bits & 0x03) << 5)
        if (bank & 0x1F) == 0:
            bank |= 0x01
        return self._normalize_bank(bank)

    def _current_ram_bank(self) -> int:
        if self.bank_mode == 0 or self.ram_size == 0:
            return 0
        bank_count = max(1, self.ram_size // self.RAM_BANK_SIZE)
        return (self.upper_bank_bits & 0x03) % bank_count

    def read(self, addr: int) -> int:
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

    def write(self, addr: int, value: int) -> None:
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
