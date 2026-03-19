from __future__ import annotations

from cpu.z80.bus import MemoryDevice


class EchoDevice(MemoryDevice):
    def __init__(self):
        self.last = 0

    def read(self, addr):
        return self.last

    def write(self, addr, value):
        self.last = value & 0xFF


def test_memory_device_echoes_last_written_value():
    device = EchoDevice()

    device.write(0x1234, 0x1AB)

    assert device.read(0x5678) == 0xAB
