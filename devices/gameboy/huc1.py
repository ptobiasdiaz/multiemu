"""HuC1 support for Game Boy cartridges with IR mode and banking."""

from __future__ import annotations


class HuC1:
    """Implements HuC1 ROM/RAM banking and IR register selection."""

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
        self.rom_bank = 1
        self.ram_bank = 0
        self.ir_mode = False
        self.ir_transmitter_on = False
        self.ir_light_detected = False

    def reset(self) -> None:
        self.rom_bank = 1
        self.ram_bank = 0
        self.ir_mode = False
        self.ir_transmitter_on = False
        self.ir_light_detected = False

    def _normalize_rom_bank(self, bank: int) -> int:
        bank &= 0x3F
        if bank == 0 and self.rom_bank_count > 1:
            bank = 1
        bank %= self.rom_bank_count
        if bank == 0 and self.rom_bank_count > 1:
            bank = 1
        return bank

    def _current_ram_bank(self) -> int:
        if self.ram_size == 0:
            return 0
        bank_count = max(1, self.ram_size // self.RAM_BANK_SIZE)
        return self.ram_bank % bank_count

    def read(self, addr: int) -> int:
        addr &= 0xFFFF
        if 0x0000 <= addr < 0x4000:
            return self.rom_data[addr] if addr < len(self.rom_data) else 0xFF

        if 0x4000 <= addr < 0x8000:
            bank = self._normalize_rom_bank(self.rom_bank)
            offset = bank * self.ROM_BANK_SIZE + (addr - 0x4000)
            return self.rom_data[offset] if offset < len(self.rom_data) else 0xFF

        if 0xA000 <= addr < 0xC000:
            if self.ir_mode:
                return 0xC1 if self.ir_light_detected else 0xC0
            if self.ram_size == 0:
                return 0xFF
            bank = self._current_ram_bank()
            offset = bank * self.RAM_BANK_SIZE + (addr - 0xA000)
            return self.ram[offset] if offset < len(self.ram) else 0xFF

        return 0xFF

    def write(self, addr: int, value: int) -> None:
        addr &= 0xFFFF
        value &= 0xFF
        if 0x0000 <= addr < 0x2000:
            self.ir_mode = value == 0x0E
        elif 0x2000 <= addr < 0x4000:
            self.rom_bank = value & 0x3F
            if self.rom_bank == 0:
                self.rom_bank = 1
        elif 0x4000 <= addr < 0x6000:
            self.ram_bank = value & 0x03
        elif 0x6000 <= addr < 0x8000:
            return
        elif 0xA000 <= addr < 0xC000:
            if self.ir_mode:
                self.ir_transmitter_on = (value & 0x01) != 0
                return
            if self.ram_size == 0:
                return
            bank = self._current_ram_bank()
            offset = bank * self.RAM_BANK_SIZE + (addr - 0xA000)
            if offset < len(self.ram):
                self.ram[offset] = value
