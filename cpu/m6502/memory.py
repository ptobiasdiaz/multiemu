from __future__ import annotations


class RAMBlock:
    def __init__(self, size: int):
        self.size = size
        self.data = bytearray(size)

    def read(self, addr: int) -> int:
        if 0 <= addr < self.size:
            return self.data[addr]
        return 0xFF

    def write(self, addr: int, value: int) -> None:
        if 0 <= addr < self.size:
            self.data[addr] = value & 0xFF

    def load(self, addr: int, data: bytes) -> None:
        end = addr + len(data)
        if addr < 0 or end > self.size:
            raise ValueError("rango fuera de RAM")
        self.data[addr:end] = data

    def peek(self, addr: int) -> int:
        return self.read(addr)


class ROMBlock:
    def __init__(self, size: int):
        self.size = size
        self.data = bytearray([0xFF] * size)

    def read(self, addr: int) -> int:
        if 0 <= addr < self.size:
            return self.data[addr]
        return 0xFF

    def write(self, addr: int, value: int) -> None:
        return

    def load_bytes(self, data: bytes, *, offset: int = 0) -> None:
        end = offset + len(data)
        if offset < 0 or end > self.size:
            raise ValueError("rango fuera de ROM")
        self.data[offset:end] = data

    def peek(self, addr: int) -> int:
        return self.read(addr)
