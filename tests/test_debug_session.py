from __future__ import annotations

from multiemu.debug_session import DebugSession


class _DummyCPU:
    def __init__(self):
        self._state = {"PC": 0x1000, "A": 0x12}

    def step(self):
        self._state["PC"] += 1
        return 4

    def snapshot(self):
        return dict(self._state)

    def read_state(self):
        return dict(self._state)

    def write_state(self, state):
        self._state = dict(state)


class _DummyBus:
    def __init__(self):
        self.mem = bytearray(range(256))

    def read8(self, addr):
        return self.mem[addr & 0xFF]

    def write8(self, addr, value):
        self.mem[addr & 0xFF] = value & 0xFF

    def read_state(self):
        return {"data": list(self.mem)}

    def write_state(self, state):
        self.mem[:] = bytes(state["data"])


class _DummyMachine:
    TSTATES_PER_FRAME = 8

    def __init__(self):
        self.cpu = _DummyCPU()
        self.bus = _DummyBus()
        self.tstates = 0
        self.frame_tstates = 0
        self.frame_counter = 0
        self._begun = 0
        self._finished = 0

    def _begin_frame(self):
        self._begun += 1

    def _finish_frame(self):
        self._finished += 1
        self.frame_counter += 1

    def _run_devices_until(self, tstates):
        return None

    def read_state(self):
        return {
            "tstates": self.tstates,
            "frame_tstates": self.frame_tstates,
            "frame_counter": self.frame_counter,
            "cpu": self.cpu.read_state(),
            "bus": self.bus.read_state(),
        }

    def write_state(self, state):
        self.tstates = state["tstates"]
        self.frame_tstates = state["frame_tstates"]
        self.frame_counter = state["frame_counter"]
        self.cpu.write_state(state["cpu"])
        self.bus.write_state(state["bus"])


def test_debug_session_reads_and_writes_machine_state():
    machine = _DummyMachine()
    session = DebugSession(machine)

    state = session.read_state()
    state["cpu"]["A"] = 0x99
    state["tstates"] = 40
    state["bus"]["data"][0x10] = 0x77
    session.write_state(state)

    assert session.read_state()["cpu"]["A"] == 0x99
    assert machine.tstates == 40
    assert machine.bus.read8(0x10) == 0x77


def test_debug_session_step_crosses_frame_boundary():
    machine = _DummyMachine()
    session = DebugSession(machine)

    session.step()
    session.step()

    assert session.frame_completed is True
    assert machine.frame_counter == 1


def test_debug_session_prefers_explicit_machine_device_ids():
    machine = _DummyMachine()

    def _debug_devices():
        return [
            {"id": "machine", "obj": machine, "kind": "machine", "label": "Machine", "writable": True},
            {"id": "cpu", "obj": machine.cpu, "kind": "cpu", "label": "CPU", "writable": True},
            {"id": "vic", "obj": machine.bus, "kind": "chip", "label": "Fake VIC", "writable": True},
        ]

    machine.debug_devices = _debug_devices
    session = DebugSession(machine)

    devices = session.list_devices()

    assert [device["id"] for device in devices] == ["machine", "cpu", "vic"]
    assert devices[2]["label"] == "Fake VIC"


def test_debug_session_uses_machine_debug_devices_from_real_machine():
    from machines.gameboy import DMG

    rom = bytearray(0x8000)
    rom[0x0134:0x013A] = b"DBGROM"
    rom[0x0147] = 0x00
    machine = DMG(bytes(rom))
    session = DebugSession(machine)

    ids = [device["id"] for device in session.list_devices()]

    assert ids[:3] == ["machine", "cpu", "bus"]
    assert "interrupts" in ids
    assert "timer" in ids
    assert "dma" in ids


def test_debug_session_lists_extended_gameboy_devices_with_state():
    from machines.gameboy import CGB

    rom = bytearray(0x8000)
    rom[0x0134:0x013A] = b"CGBDBG"
    rom[0x0143] = 0xC0
    rom[0x0147] = 0x1B
    machine = CGB(bytes(rom))
    session = DebugSession(machine)

    ids = {device["id"] for device in session.list_devices()}

    assert "cartridge" in ids
    assert "ppu" in ids
    assert "apu" in ids


def test_debug_session_lists_extended_spectrum_devices_with_state():
    from machines.z80 import Spectrum48K

    machine = Spectrum48K(bytes([0] * 0x4000))
    session = DebugSession(machine)

    ids = {device["id"] for device in session.list_devices()}

    assert "ula" in ids
