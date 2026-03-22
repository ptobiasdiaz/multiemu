from __future__ import annotations

from typing import Protocol


class MemoryDevice(Protocol):
    def read(self, addr: int) -> int:
        ...

    def write(self, addr: int, value: int) -> None:
        ...


class M6502Bus:
    def __init__(self):
        self._mapped: list[tuple[int, int, MemoryDevice]] = []
        self.irq_pending = False
        self.nmi_pending = False

    def map_block(self, start: int, device: MemoryDevice, *, size: int | None = None) -> None:
        if size is None:
            size = getattr(device, "size", None)
        if size is None:
            raise ValueError("hay que indicar size o usar un device con atributo size")
        start &= 0xFFFF
        end = (start + int(size) - 1) & 0xFFFF
        if end < start:
            raise ValueError("no se soportan rangos que crucen 0xFFFF")
        self._mapped.append((start, end, device))

    def _find_device(self, addr: int) -> tuple[int, MemoryDevice] | None:
        addr &= 0xFFFF
        for start, end, device in reversed(self._mapped):
            if start <= addr <= end:
                return start, device
        return None

    def read8(self, addr: int) -> int:
        resolved = self._find_device(addr)
        if resolved is None:
            return 0xFF
        start, device = resolved
        return device.read((addr - start) & 0xFFFF) & 0xFF

    def write8(self, addr: int, value: int) -> None:
        resolved = self._find_device(addr)
        if resolved is None:
            return
        start, device = resolved
        device.write((addr - start) & 0xFFFF, value & 0xFF)

    def read16(self, addr: int) -> int:
        lo = self.read8(addr)
        hi = self.read8((addr + 1) & 0xFFFF)
        return lo | (hi << 8)

    def request_irq(self) -> None:
        self.irq_pending = True

    def clear_irq(self) -> None:
        self.irq_pending = False

    def request_nmi(self) -> None:
        self.nmi_pending = True

    def pull_nmi(self) -> bool:
        pending = self.nmi_pending
        self.nmi_pending = False
        return pending
