from cpu.z80 import Z80Bus, Z80Core, RAMBlock
from cpu.z80.bus import MemoryDevice


class EchoDevice(MemoryDevice):
    def __init__(self):
        self.last = 0

    def read(self, addr):
        return self.last

    def write(self, addr, value):
        self.last = value & 0xFF


bus = Z80Bus()
cpu = Z80Core(bus)

ram = RAMBlock(0xC000)
bus.map_block(0x0000, ram)

echo = EchoDevice()
bus.map_device(0xC000, 0x4000, echo)

program = bytes([
    0x3E, 0x42,             # LD A,42h
    0x32, 0x00, 0xC0,       # LD (C000h),A   -> device.write
    0x3A, 0x00, 0xC0,       # LD A,(C000h)   -> device.read
    0x76                    # HALT
])

ram.load(0, program)

cpu.run_cycles(100)
print(cpu.snapshot())
