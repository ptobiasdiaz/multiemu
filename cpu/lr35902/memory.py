"""Memory helpers for the LR35902/Game Boy line."""

from __future__ import annotations


class LR35902Memory:
    """Thin helpers around an LR35902 bus instance."""

    def __init__(self, bus):
        self.bus = bus

    def read8(self, addr: int) -> int:
        return self.bus.read8(addr)

    def write8(self, addr: int, value: int) -> None:
        self.bus.write8(addr, value)

    def read16(self, addr: int) -> int:
        return self.bus.read16(addr)

    def write16(self, addr: int, value: int) -> None:
        self.bus.write16(addr, value)
