"""Serial port stub for the original Game Boy."""

from __future__ import annotations


class GameBoySerialPort:
    """Models SB/SC with conservative DMG post-boot defaults."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.sb = 0x00
        self.sc = 0x00

    def read_sb(self) -> int:
        return self.sb

    def write_sb(self, value: int) -> None:
        self.sb = value & 0xFF

    def read_sc(self) -> int:
        return 0x7E | (self.sc & 0x81)

    def write_sc(self, value: int) -> None:
        self.sc = value & 0x81
