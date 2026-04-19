from __future__ import annotations

from machines import BaseMachine, CGB, DMG, GameBoyMachineBase, M6502MachineBase, VIC20NTSC, VIC20PAL
from machines.z80 import CPC6128, CPC664, MasterSystem2, Spectrum128K, Spectrum48K, SpectrumPlus2


def _make_gameboy_rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0x0134:0x013A] = b"FAMILY"
    return bytes(rom)


def test_z80_family_machines_still_inherit_from_base_machine():
    machine = Spectrum48K(bytes([0x00]) * 0x4000)

    assert isinstance(machine, BaseMachine)
    assert machine.input_keymap_name == "spectrum48k"


def test_cpc664_uses_base_machine_family():
    machine = CPC664(bytes([0x00]) * 0x4000)

    assert isinstance(machine, BaseMachine)
    assert machine.machine_id == "cpc664"


def test_cpc6128_uses_base_machine_family():
    machine = CPC6128(bytes([0x00]) * 0x4000)

    assert isinstance(machine, BaseMachine)
    assert machine.machine_id == "cpc6128"


def test_spectrum128k_uses_base_machine_family():
    machine = Spectrum128K(bytes([0x00]) * 0x8000)

    assert isinstance(machine, BaseMachine)
    assert machine.machine_id == "spectrum128k"
    assert machine.input_keymap_name == "spectrum128k"


def test_spectrumplus2_uses_base_machine_family():
    machine = SpectrumPlus2(bytes([0x00]) * 0x8000)

    assert isinstance(machine, BaseMachine)
    assert machine.machine_id == "spectrumplus2"
    assert machine.input_keymap_name == "spectrum128k"


def test_mastersystem2_uses_base_machine_family():
    machine = MasterSystem2(bytes(range(256)) * 256)

    assert isinstance(machine, BaseMachine)
    assert machine.machine_id == "mastersystem2"


def test_gameboy_family_uses_gameboy_base():
    machine = DMG(_make_gameboy_rom())

    assert isinstance(machine, GameBoyMachineBase)
    assert isinstance(machine, BaseMachine)


def test_gameboy_color_family_uses_gameboy_base():
    machine = CGB(_make_gameboy_rom())

    assert isinstance(machine, GameBoyMachineBase)
    assert isinstance(machine, BaseMachine)
    assert machine.bus.read8(0xFF4D) == 0x7E
    assert machine.bus.read8(0xFF4F) == 0xFE
    assert machine.bus.read8(0xFF70) == 0xF9


def test_base_machine_read_state_write_state_roundtrip():
    machine = DMG(_make_gameboy_rom())
    machine.tstates = 123
    machine.frame_counter = 7
    machine.frame_tstates = 45
    machine.cpu.A = 0x42

    state = machine.read_state()

    other = DMG(_make_gameboy_rom())
    other.write_state(state)

    assert other.tstates == 123
    assert other.frame_counter == 7
    assert other.frame_tstates == 45
    assert other.cpu.A == 0x42


def test_m6502_family_anchor_is_exposed_from_top_level_machines_package():
    assert M6502MachineBase.__name__ == "M6502MachineBase"


def test_vic20_uses_m6502_family_base():
    machine = VIC20NTSC(
        bytes([0xEA]) * 0x2000,
        bytes([0xEA]) * 0x1FFC + bytes([0x00, 0xE0, 0x00, 0xE0]),
        bytes([0xEA]) * 0x1000,
    )

    assert isinstance(machine, M6502MachineBase)
    assert isinstance(machine, BaseMachine)


def test_vic20pal_uses_m6502_family_base():
    machine = VIC20PAL(
        bytes([0xEA]) * 0x2000,
        bytes([0xEA]) * 0x1FFC + bytes([0x00, 0xE0, 0x00, 0xE0]),
        bytes([0xEA]) * 0x1000,
    )

    assert isinstance(machine, M6502MachineBase)
    assert isinstance(machine, BaseMachine)
