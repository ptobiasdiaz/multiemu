from __future__ import annotations

from machines.z80 import CPC6128


def test_cpc6128_exposes_expected_identity():
    machine = CPC6128(bytes([0x00]) * 0x4000)

    assert machine.machine_id == "cpc6128"
    assert machine.display_name == "Amstrad CPC 6128 (experimental)"
    assert machine.RAM_SIZE == 0x20000
    assert machine.frame_width == machine.video.frame_width
    assert machine.frame_height == machine.video.frame_height


def test_cpc6128_can_mount_basic_and_amsdos_rom_banks():
    machine = CPC6128(
        bytes([0xAA]) * 0x4000,
        basic_rom_data=bytes([0xCC]) * 0x4000,
        amsdos_rom_data=bytes([0xDD]) * 0x4000,
    )

    assert machine.peek(0x0000) == 0xAA
    assert machine.upper_rom_banks[0].peek(0) == 0xCC
    assert machine.upper_rom_banks[7].peek(0) == 0xDD


def test_cpc6128_ram_banking_changes_visible_16k_page():
    machine = CPC6128(bytes([0x00]) * 0x4000)

    machine.ram.load(0x04000, b"\x11")
    machine.ram.load(0x10000, b"\x44")

    assert machine.peek(0x4000) == 0x11

    machine._port_write(0x7F00, 0xC4)

    assert machine.ram_bank_configuration == 4
    assert machine.peek(0x4000) == 0x44
