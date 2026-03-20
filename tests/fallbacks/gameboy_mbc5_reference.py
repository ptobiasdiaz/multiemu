"""MBC5 support for Game Boy cartridges with ROM/RAM banking."""

from __future__ import annotations


class MBC5:
    """Implements the common MBC5 banking behavior."""

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
        self.reset()

    def reset(self) -> None:
        self.ram_enabled = False
        self.rom_bank_low = 1
        self.rom_bank_high = 0
        self.ram_bank = 0

    def _current_rom_bank(self) -> int:
        bank = ((self.rom_bank_high & 0x01) << 8) | self.rom_bank_low
        return bank % self.rom_bank_count if self.rom_bank_count > 0 else 0

    def _current_ram_bank(self) -> int:
        if self.ram_size == 0:
            return 0
        bank_count = max(1, self.ram_size // self.RAM_BANK_SIZE)
        return (self.ram_bank & 0x0F) % bank_count

    def read(self, addr: int) -> int:
        addr &= 0xFFFF
        if 0x0000 <= addr < 0x4000:
            return self.rom_data[addr] if addr < len(self.rom_data) else 0xFF

        if 0x4000 <= addr < 0x8000:
            bank = self._current_rom_bank()
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
            return
        if 0x2000 <= addr < 0x3000:
            self.rom_bank_low = value
            return
        if 0x3000 <= addr < 0x4000:
            self.rom_bank_high = value & 0x01
            return
        if 0x4000 <= addr < 0x6000:
            self.ram_bank = value & 0x0F
            return
        if 0xA000 <= addr < 0xC000:
            if not self.ram_enabled or self.ram_size == 0:
                return
            bank = self._current_ram_bank()
            offset = bank * self.RAM_BANK_SIZE + (addr - 0xA000)
            if offset < len(self.ram):
                self.ram[offset] = value
