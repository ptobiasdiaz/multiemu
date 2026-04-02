from __future__ import annotations

from cpu.z80 import PythonPortHandler, RAMBlock, Z80Bus, Z80Core
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


def test_z80_read_state_write_state_roundtrip():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    state = {
        "A": 0x12,
        "F": 0x34,
        "B": 0x56,
        "C": 0x78,
        "D": 0x9A,
        "E": 0xBC,
        "H": 0xDE,
        "L": 0xF0,
        "A2": 0x11,
        "F2": 0x22,
        "B2": 0x33,
        "C2": 0x44,
        "D2": 0x55,
        "E2": 0x66,
        "H2": 0x77,
        "L2": 0x88,
        "IX": 0x1357,
        "IY": 0x2468,
        "I": 0x99,
        "R": 0xAA,
        "PC": 0x4000,
        "SP": 0xC000,
        "halted": True,
        "iff1": True,
        "iff2": False,
        "im": 2,
        "ei_pending": True,
    }
    cpu.write_state(state)
    state = cpu.read_state()

    other = Z80Core(Z80Bus())
    other.write_state(state)

    assert other.read_state() == state


def test_z80_memory_read_state_write_state_roundtrip():
    block = RAMBlock(0x20)
    block.load(0, bytes(range(0x20)))
    state = block.read_state()

    other = RAMBlock(0x20)
    other.write_state(state)

    assert other.read_state() == state


def test_z80_run_cycles_keeps_counting_clock_while_halted():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)
    ram.load(0, bytes([0x76]))  # HALT

    used = cpu.run_cycles(20)

    assert used == 20
    assert cpu.snapshot()["halted"] is True


def test_z80_ini_reads_from_port_into_memory_and_updates_registers():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)

    reads = []

    def read_cb(port):
        reads.append(port)
        return 0x5A

    bus.set_port_handler(0x34, PythonPortHandler(read_cb=read_cb))
    ram.load(0, bytes([
        0x06, 0x01,       # LD B,01h
        0x0E, 0x34,       # LD C,34h
        0x21, 0x00, 0x02, # LD HL,0200h
        0xED, 0xA2,       # INI
        0x76,             # HALT
    ]))

    cpu.run_cycles(100)
    snap = cpu.snapshot()

    assert reads == [0x0134]
    assert ram.peek(0x0200) == 0x5A
    assert snap["B"] == 0x00
    assert snap["C"] == 0x34
    assert snap["HL"] == 0x0201


def test_z80_otir_writes_all_bytes_to_port_until_b_reaches_zero():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)

    writes = []

    def write_cb(port, value):
        writes.append((port, value))

    bus.set_port_handler(0x78, PythonPortHandler(write_cb=write_cb))
    ram.load(0, bytes([
        0x06, 0x03,       # LD B,03h
        0x0E, 0x78,       # LD C,78h
        0x21, 0x00, 0x02, # LD HL,0200h
        0xED, 0xB3,       # OTIR
        0x76,             # HALT
    ]))
    ram.load(0x0200, bytes([0x11, 0x22, 0x33]))

    cpu.run_cycles(200)
    snap = cpu.snapshot()

    assert writes == [(0x0378, 0x11), (0x0278, 0x22), (0x0178, 0x33)]
    assert snap["B"] == 0x00
    assert snap["HL"] == 0x0203
    assert snap["halted"] is True


def test_z80_indr_reads_all_bytes_backwards_until_b_reaches_zero():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)

    values = iter([0xA1, 0xB2])

    def read_cb(port):
        return next(values)

    bus.set_port_handler(0x44, PythonPortHandler(read_cb=read_cb))
    ram.load(0, bytes([
        0x06, 0x02,       # LD B,02h
        0x0E, 0x44,       # LD C,44h
        0x21, 0x01, 0x02, # LD HL,0201h
        0xED, 0xBA,       # INDR
        0x76,             # HALT
    ]))

    cpu.run_cycles(200)
    snap = cpu.snapshot()

    assert ram.peek(0x0201) == 0xA1
    assert ram.peek(0x0200) == 0xB2
    assert snap["B"] == 0x00
    assert snap["HL"] == 0x01FF
    assert snap["halted"] is True


def test_z80_dd_68_loads_ixl_from_b():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)
    ram.load(0, bytes([
        0x06, 0x34,       # LD B,34h
        0xDD, 0x21, 0x78, 0x56,  # LD IX,5678h
        0xDD, 0x68,       # LD IXL,B
        0x76,             # HALT
    ]))

    cpu.run_cycles(100)
    snap = cpu.snapshot()

    assert snap["B"] == 0x34
    assert snap["IX"] == 0x5634
    assert snap["halted"] is True


def test_z80_fd_61_loads_iyh_from_c():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)
    ram.load(0, bytes([
        0x0E, 0x9A,       # LD C,9Ah
        0xFD, 0x21, 0x78, 0x56,  # LD IY,5678h
        0xFD, 0x61,       # LD IYH,C
        0x76,             # HALT
    ]))

    cpu.run_cycles(100)
    snap = cpu.snapshot()

    assert snap["C"] == 0x9A
    assert snap["IY"] == 0x9A78
    assert snap["halted"] is True


def test_z80_dd_e3_exchanges_ix_with_word_at_sp():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x2000)
    bus.map_block(0x0000, ram)
    ram.load(0, bytes([
        0x31, 0x00, 0x10,             # LD SP,1000h
        0xDD, 0x21, 0x78, 0x56,       # LD IX,5678h
        0xDD, 0xE3,                   # EX (SP),IX
        0x76,                         # HALT
    ]))
    ram.load(0x1000, bytes([0x34, 0x12]))

    cpu.run_cycles(100)
    snap = cpu.snapshot()

    assert snap["IX"] == 0x1234
    assert ram.peek(0x1000) == 0x78
    assert ram.peek(0x1001) == 0x56
    assert snap["halted"] is True


def test_z80_dd_prefix_ignores_unaffected_opcode():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)
    ram.load(0, bytes([
        0x3E, 0x12,             # LD A,12h
        0xDD, 0x47,             # DD-prefixed LD B,A -> prefix ignored
        0x76,                   # HALT
    ]))

    cpu.run_cycles(100)
    snap = cpu.snapshot()

    assert snap["A"] == 0x12
    assert snap["B"] == 0x12
    assert snap["halted"] is True


def test_z80_ed_ed_behaves_as_undocumented_nop():
    bus = Z80Bus()
    cpu = Z80Core(bus)
    ram = RAMBlock(0x1000)
    bus.map_block(0x0000, ram)
    ram.load(0, bytes([
        0x06, 0x34,       # LD B,34h
        0xED, 0xED,       # undocumented ED opcode -> NOP
        0x78,             # LD A,B
        0x76,             # HALT
    ]))

    cpu.run_cycles(100)
    snap = cpu.snapshot()

    assert snap["A"] == 0x34
    assert snap["B"] == 0x34
    assert snap["PC"] == 0x0006
    assert snap["halted"] is True
