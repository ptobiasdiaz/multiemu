from __future__ import annotations

from machines.z80 import CPC664


def test_cpc664_exposes_expected_identity():
    machine = CPC664(bytes([0x00]) * 0x4000)

    assert machine.machine_id == "cpc664"
    assert machine.display_name == "Amstrad CPC 664 (experimental)"
    assert machine.frame_width == machine.video.frame_width
    assert machine.frame_height == machine.video.frame_height


def test_cpc664_can_mount_basic_and_amsdos_rom_banks():
    machine = CPC664(
        bytes([0xAA]) * 0x4000,
        basic_rom_data=bytes([0xCC]) * 0x4000,
        amsdos_rom_data=bytes([0xDD]) * 0x4000,
    )

    assert machine.peek(0x0000) == 0xAA
    assert machine.upper_rom_banks[0].peek(0) == 0xCC
    assert machine.upper_rom_banks[7].peek(0) == 0xDD
