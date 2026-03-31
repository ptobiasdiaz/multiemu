from __future__ import annotations

from machines import DMG, LR35902MachineBase, M6502MachineBase, SingleCPUMachineBase, VIC20NTSC, VIC20PAL, Z80MachineBase
from machines.z80 import Spectrum48K


def _make_gameboy_rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0x0134:0x013A] = b"FAMILY"
    return bytes(rom)


def test_z80_family_machines_still_inherit_from_single_cpu_base():
    machine = Spectrum48K(bytes([0x00]) * 0x4000)

    assert isinstance(machine, Z80MachineBase)
    assert isinstance(machine, SingleCPUMachineBase)


def test_gameboy_family_uses_lr35902_family_base():
    machine = DMG(_make_gameboy_rom())

    assert isinstance(machine, LR35902MachineBase)
    assert isinstance(machine, SingleCPUMachineBase)


def test_m6502_family_anchor_is_exposed_from_top_level_machines_package():
    assert M6502MachineBase.__name__ == "M6502MachineBase"


def test_vic20_uses_m6502_family_base():
    machine = VIC20NTSC(
        bytes([0xEA]) * 0x2000,
        bytes([0xEA]) * 0x1FFC + bytes([0x00, 0xE0, 0x00, 0xE0]),
        bytes([0xEA]) * 0x1000,
    )

    assert isinstance(machine, M6502MachineBase)
    assert isinstance(machine, SingleCPUMachineBase)


def test_vic20pal_uses_m6502_family_base():
    machine = VIC20PAL(
        bytes([0xEA]) * 0x2000,
        bytes([0xEA]) * 0x1FFC + bytes([0x00, 0xE0, 0x00, 0xE0]),
        bytes([0xEA]) * 0x1000,
    )

    assert isinstance(machine, M6502MachineBase)
    assert isinstance(machine, SingleCPUMachineBase)
