"""MBC2 support for Game Boy cartridges with 4-bit internal RAM."""

from __future__ import annotations


class MBC2:
    """Implements the common MBC2 banking behavior."""

    ROM_BANK_SIZE = 0x4000
    RAM_SIZE = 0x200

    def __init__(self, rom_data: bytes):
        self.rom_data = rom_data
        self.rom_bank_count = max(1, len(rom_data) // self.ROM_BANK_SIZE)
        self.ram = bytearray(self.RAM_SIZE)
        self.reset()

    def reset(self) -> None:
        self.ram_enabled = False
        self.rom_bank = 1

    def _normalize_rom_bank(self, bank: int) -> int:
        bank &= 0x0F
        bank %= self.rom_bank_count
        if bank == 0 and self.rom_bank_count > 1:
            bank = 1
        return bank

    def read(self, addr: int) -> int:
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

    def write(self, addr: int, value: int) -> None:
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
