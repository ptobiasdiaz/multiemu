"""Cartridge helpers for Game Boy ROMs."""

from __future__ import annotations

from .gameboy_mbc1_reference import MBC1
from .gameboy_mbc2_reference import MBC2
from .gameboy_mbc3_reference import MBC3
from .gameboy_mbc5_reference import MBC5
from .gameboy_huc1_reference import HuC1


CARTRIDGE_TYPES = {
    0x00: "ROM_ONLY",
    0x01: "MBC1",
    0x02: "MBC1+RAM",
    0x03: "MBC1+RAM+BATTERY",
    0x05: "MBC2",
    0x06: "MBC2+BATTERY",
    0x0F: "MBC3+TIMER+BATTERY",
    0x10: "MBC3+TIMER+RAM+BATTERY",
    0x11: "MBC3",
    0x12: "MBC3+RAM",
    0x13: "MBC3+RAM+BATTERY",
    0x19: "MBC5",
    0x1A: "MBC5+RAM",
    0x1B: "MBC5+RAM+BATTERY",
    0x1C: "MBC5+RUMBLE",
    0x1D: "MBC5+RUMBLE+RAM",
    0x1E: "MBC5+RUMBLE+RAM+BATTERY",
    0xFF: "HuC1+RAM+BATTERY",
}


class GameBoyCartridge:
    """Represents a Game Boy cartridge and its header/ROM data."""

    TITLE_START = 0x0134
    TITLE_END = 0x0143
    TYPE_ADDR = 0x0147
    ROM_SIZE_ADDR = 0x0148
    RAM_SIZE_ADDR = 0x0149

    def __init__(self, rom_data: bytes):
        if len(rom_data) < 0x150:
            raise ValueError("ROM de Game Boy invalida: cabecera demasiado corta")
        self.rom_data = bytes(rom_data)
        self.title = self._decode_title()
        self.cartridge_type = self.rom_data[self.TYPE_ADDR]
        self.cartridge_type_name = CARTRIDGE_TYPES.get(self.cartridge_type, f"0x{self.cartridge_type:02X}")
        self.rom_size_code = self.rom_data[self.ROM_SIZE_ADDR]
        self.ram_size_code = self.rom_data[self.RAM_SIZE_ADDR]
        self.mapper = self._build_mapper()

    def _decode_title(self) -> str:
        raw = self.rom_data[self.TITLE_START : self.TITLE_END + 1]
        raw = raw.split(b"\x00", 1)[0]
        if not raw:
            return ""
        return raw.decode("ascii", errors="replace").strip()

    def supports_rom_only(self) -> bool:
        return self.cartridge_type == 0x00

    def supports_mbc1(self) -> bool:
        return self.cartridge_type in {0x01, 0x02, 0x03}

    def supports_huc1(self) -> bool:
        return self.cartridge_type == 0xFF

    def supports_mbc2(self) -> bool:
        return self.cartridge_type in {0x05, 0x06}

    def supports_mbc3(self) -> bool:
        return self.cartridge_type in {0x0F, 0x10, 0x11, 0x12, 0x13}

    def supports_mbc5(self) -> bool:
        return self.cartridge_type in {0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E}

    def _build_mapper(self):
        if self.supports_rom_only():
            return None
        if self.supports_mbc1():
            return MBC1(self.rom_data, ram_size_code=self.ram_size_code)
        if self.supports_huc1():
            return HuC1(self.rom_data, ram_size_code=self.ram_size_code)
        if self.supports_mbc2():
            return MBC2(self.rom_data)
        if self.supports_mbc3():
            return MBC3(self.rom_data, ram_size_code=self.ram_size_code)
        if self.supports_mbc5():
            return MBC5(self.rom_data, ram_size_code=self.ram_size_code)
        raise ValueError(f"tipo de cartucho aun no soportado: {self.cartridge_type_name}")

    def read(self, addr: int) -> int:
        if self.mapper is not None:
            return self.mapper.read(addr)
        if 0 <= addr < len(self.rom_data):
            return self.rom_data[addr]
        return 0xFF

    def write(self, addr: int, value: int) -> None:
        if self.mapper is not None:
            self.mapper.write(addr, value)
