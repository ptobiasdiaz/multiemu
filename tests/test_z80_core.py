from __future__ import annotations

from cpu.z80 import RAMBlock, Z80Bus, Z80Core
from cpu.z80.bus import MemoryDevice


class EchoDevice(MemoryDevice):
    def __init__(self):
        self.last = 0

    def read(self, addr):
        return self.last

    def write(self, addr, value):
        self.last = value & 0xFF


def test_z80_can_read_back_from_memory_mapped_device():
    bus = Z80Bus()
    cpu = Z80Core(bus)

    ram = RAMBlock(0xC000)
    bus.map_block(0x0000, ram)

    echo = EchoDevice()
    bus.map_device(0xC000, 0x4000, echo)

    program = bytes([
        0x3E, 0x42,             # LD A,42h
        0x32, 0x00, 0xC0,       # LD (C000h),A
        0x3A, 0x00, 0xC0,       # LD A,(C000h)
        0x76,                   # HALT
    ])
    ram.load(0, program)

    cpu.run_cycles(100)
    snap = cpu.snapshot()

    assert echo.last == 0x42
    assert snap["A"] == 0x42
    assert snap["halted"] is True


def test_z80_run_cycles_keeps_counting_clock_while_halted():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)
    ram.load(0, bytes([0x76]))  # HALT

    used = cpu.run_cycles(20)

    assert used == 20
    assert cpu.snapshot()["halted"] is True
