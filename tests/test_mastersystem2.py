from __future__ import annotations

import pytest

from chipsets import SMSVDPReference
from machines.z80 import MasterSystem2
from multiemu.debug_session import DebugSession
from frontend.input_events import InputEvent, JOYSTICK_FIRE, JOYSTICK_FIRE_2, JOYSTICK_RIGHT


def _make_test_rom() -> bytes:
    rom = bytearray(0x10000)
    for bank in range(4):
        base = bank * 0x4000
        rom[base:base + 0x4000] = bytes([bank]) * 0x4000
    return bytes(rom)


def test_mastersystem2_initial_bank_mapping_reads_expected_pages():
    machine = MasterSystem2(_make_test_rom())

    assert machine.peek(0x0000) == 0
    assert machine.peek(0x4000) == 1
    assert machine.peek(0x8000) == 2


def test_mastersystem2_can_boot_from_bios_source_without_cart():
    machine = MasterSystem2(None, bios_data=_make_test_rom())

    assert machine.active_rom_source == "bios"
    assert machine.peek(0x0000) == 0
    assert machine.peek(0x4000) == 1


def test_mastersystem2_large_bios_is_split_into_firmware_and_built_in():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x23]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    assert len(machine.bios_data) == 0x8000
    assert len(machine.built_in_data) == 0x18000
    assert machine.peek(0x0000) == 0x10
    assert machine.peek(0x4000) == 0x11
    assert machine.peek(0x8000) == 0x22


def test_mastersystem2_bios_mode_maps_slot_2_from_built_in_banks():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x23]) * 0x4000
    bios[0x10000:0x14000] = bytes([0x24]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    machine.poke(0xFFFF, 2)
    assert machine.peek(0x8000) == 0x22

    machine.poke(0xFFFF, 3)
    assert machine.peek(0x8000) == 0x23

    machine.poke(0xFFFF, 4)
    assert machine.peek(0x8000) == 0x24


def test_mastersystem2_bios_mode_treats_slot_2_page_as_absolute_internal_bank_number():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x23]) * 0x4000
    bios[0x10000:0x14000] = bytes([0x24]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    machine.poke(0xFFFF, 0x82)

    assert machine.frame_page_2 == 0x82
    assert machine.peek(0x8000) == 0x22


def test_mastersystem2_bios_mode_treats_slot_1_page_as_absolute_internal_bank_number():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x23]) * 0x4000
    bios[0x10000:0x14000] = bytes([0x24]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    machine.poke(0xFFFE, 0x83)

    assert machine.frame_page_1 == 0x83
    assert machine.peek(0x4000) == 0x23


def test_mastersystem2_bank_registers_switch_visible_rom_pages():
    machine = MasterSystem2(_make_test_rom())

    machine.poke(0xFFFD, 3)
    machine.poke(0xFFFE, 2)
    machine.poke(0xFFFF, 1)

    assert machine.peek(0x0000) == 0
    assert machine.peek(0x0400) == 3
    assert machine.peek(0x4000) == 2
    assert machine.peek(0x8000) == 1


def test_mastersystem2_sega_mapper_keeps_first_kb_fixed_to_bank_0():
    machine = MasterSystem2(_make_test_rom())

    machine.poke(0xFFFD, 3)

    assert machine.peek(0x0000) == 0
    assert machine.peek(0x03FF) == 0
    assert machine.peek(0x0400) == 3


def test_mastersystem2_mapper_register_writes_also_remain_visible_in_ram():
    machine = MasterSystem2(_make_test_rom())

    machine.poke(0xFFFC, 0xAA)
    machine.poke(0xFFFD, 0x03)
    machine.poke(0xFFFE, 0x02)
    machine.poke(0xFFFF, 0x01)

    assert machine.peek(0xFFFC) == 0xAA
    assert machine.peek(0xFFFD) == 0x03
    assert machine.peek(0xFFFE) == 0x02
    assert machine.peek(0xFFFF) == 0x01
    assert machine.frame_page_0 == 3
    assert machine.frame_page_1 == 2
    assert machine.frame_page_2 == 1


def test_mastersystem2_ram_is_writable_and_mirrored():
    machine = MasterSystem2(_make_test_rom())

    machine.poke(0xC000, 0x12)
    machine.poke(0xDFFF, 0x34)

    assert machine.peek(0xC000) == 0x12
    assert machine.peek(0xE000) == 0x12
    assert machine.peek(0xDFFF) == 0x34


def test_mastersystem2_state_roundtrip_restores_ram_and_paging():
    machine = MasterSystem2(_make_test_rom())
    machine.poke(0xC000, 0x56)
    machine.poke(0xFFFD, 2)
    machine.poke(0xFFFE, 3)
    machine.poke(0xFFFF, 1)

    state = machine.read_state()

    other = MasterSystem2(_make_test_rom())
    other.write_state(state)

    assert other.peek(0xC000) == 0x56
    assert other.frame_page_0 == 2
    assert other.frame_page_1 == 3
    assert other.frame_page_2 == 1


def test_mastersystem2_state_rejects_different_cart_rom():
    machine = MasterSystem2(_make_test_rom())
    state = machine.read_state()
    other_rom = bytearray(_make_test_rom())
    other_rom[0x4000] ^= 0xFF
    other = MasterSystem2(bytes(other_rom))

    with pytest.raises(ValueError, match="cart SHA256 distinto"):
        other.write_state(state)


def test_mastersystem2_debug_devices_expose_ram_mapper_and_cartridge():
    machine = MasterSystem2(_make_test_rom())
    session = DebugSession(machine)

    devices = {device["id"]: device for device in session.list_devices()}

    assert devices["cartridge"]["writable"] is False
    assert devices["mapper"]["kind"] == "memory"
    assert devices["ram"]["kind"] == "memory"

    ram_state = session.get_device_state("ram")
    ram_state["data"][0x10] = 0x5A
    session.set_device_state("ram", ram_state)
    assert machine.peek(0xC010) == 0x5A

    mapper_state = session.get_device_state("mapper")
    mapper_state["frame_page_1"] = 3
    session.set_device_state("mapper", mapper_state)
    assert machine.frame_page_1 == 3

    cartridge_state = session.get_device_state("cartridge")
    assert cartridge_state["cart_size"] == len(_make_test_rom())
    assert cartridge_state["cart_sha256"] == machine.read_state()["cart_sha256"]


def _vdp_set_register(machine: MasterSystem2, register: int, value: int) -> None:
    machine._port_write(0xBF, value)
    machine._port_write(0xBF, 0x80 | (register & 0x0F))


def _vdp_set_address(machine: MasterSystem2, addr: int, code: int) -> None:
    machine._port_write(0xBF, addr & 0xFF)
    machine._port_write(0xBF, ((addr >> 8) & 0x3F) | ((code & 0x03) << 6))


def test_mastersystem2_vdp_register_write_through_control_port():
    machine = MasterSystem2(_make_test_rom())

    _vdp_set_register(machine, 2, 0x0E)

    assert machine.vdp.registers[2] == 0x0E


def test_mastersystem2_vdp_vram_write_and_read_through_data_port():
    machine = MasterSystem2(_make_test_rom())

    _vdp_set_address(machine, 0x0123, 0x01)
    machine._port_write(0xBE, 0x5A)

    _vdp_set_address(machine, 0x0123, 0x00)
    value = machine._port_read(0xBE)

    assert value == 0x5A


def test_mastersystem2_vdp_cram_affects_rendered_background_tile():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 1, 0x40)

    # CRAM entry 1 -> bright blue-ish.
    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    # Tile 0 row 0..7, pixel 0 set to colour 1.
    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    # Name table entry 0 -> tile 0.
    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()

    assert frame[0:3] != b"\x00\x00\x00"


def test_mastersystem2_vdp_positive_scroll_shifts_background_right():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 1, 0x40)
    _vdp_set_register(machine, 8, 0x01)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
    for row in range(8):
        _vdp_set_address(machine, 0x20 + row * 4, 0x01)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x01)
    machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()

    assert frame[0:3] == b"\x00\x00\x00"
    assert frame[1 * 3: 1 * 3 + 3] != b"\x00\x00\x00"


def test_mastersystem2_vdp_scroll_remains_stable_across_tile_boundary():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 1, 0x40)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
    for row in range(8):
        _vdp_set_address(machine, 0x20 + row * 4, 0x01)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x01)
    machine._port_write(0xBE, 0x00)

    _vdp_set_register(machine, 8, 0x07)
    frame_7 = machine.render_frame()
    _vdp_set_register(machine, 8, 0x08)
    frame_8 = machine.render_frame()

    assert frame_7[0:3] == b"\x00\x00\x00"
    assert frame_7[7 * 3: 7 * 3 + 3] != b"\x00\x00\x00"
    assert frame_8[7 * 3: 7 * 3 + 3] == b"\x00\x00\x00"
    assert frame_8[8 * 3: 8 * 3 + 3] != b"\x00\x00\x00"


def test_mastersystem2_vdp_can_lock_top_two_rows_from_horizontal_scroll_when_enabled():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 0, 0x40)
    _vdp_set_register(machine, 1, 0x40)
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 8, 0x01)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()
    top_pixel = frame[0:3]
    lower_pixel = frame[(16 * machine.SCREEN_WIDTH + 0) * 3: (16 * machine.SCREEN_WIDTH + 0) * 3 + 3]

    assert top_pixel != b"\x00\x00\x00"
    assert lower_pixel == b"\x00\x00\x00"


def test_mastersystem2_vdp_latches_horizontal_scroll_per_scanline():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x40)
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 8, 0x00)

    machine.vdp.begin_frame()
    scanline_tstates = machine.TSTATES_PER_FRAME // machine.vdp.TOTAL_SCANLINES
    machine.vdp.run_until(scanline_tstates * 16)
    _vdp_set_register(machine, 8, 0x08)
    machine.vdp.run_until(machine.vdp.VBLANK_TSTATE + 1)

    assert machine.vdp._line_scroll_x[0] == 0
    assert machine.vdp._line_scroll_x[16] == 0
    assert machine.vdp._line_scroll_x[17] == 0x08
    assert machine.vdp._render_line_scroll_x[0] == 0
    assert machine.vdp._render_line_scroll_x[17] == 0x08


def test_mastersystem2_vdp_line_interrupt_remains_pending_until_cpu_accepts_it():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 0, 0x10)
    _vdp_set_register(machine, 10, 0x00)
    machine.cpu.write_state({"PC": 0x1234, "SP": 0xD000, "iff1": False, "iff2": False, "im": 1})

    machine.vdp.begin_frame()
    machine.vdp.run_until(machine.vdp._scanline_tstates)

    assert machine.cpu.snapshot()["PC"] == 0x1234

    machine.cpu.write_state({"iff1": True, "iff2": True})
    machine.vdp._service_interrupt()

    assert machine.cpu.snapshot()["PC"] == 0x0038


def test_mastersystem2_vdp_status_flags_persist_until_control_read():
    machine = MasterSystem2(_make_test_rom())

    machine.vdp.status = 0x80
    machine.vdp.begin_frame()

    assert machine.vdp.status & 0x80
    assert machine.vdp.read_control() & 0x80
    assert machine.vdp.status & 0x80 == 0


def test_mastersystem2_vdp_masks_leftmost_8_pixels_when_enabled():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 0, 0x20)
    _vdp_set_register(machine, 1, 0x40)
    _vdp_set_register(machine, 2, 0x0E)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()
    assert frame[0:3] == b"\x00\x00\x00"
    assert frame[8 * 3: 8 * 3 + 3] != b"\x00\x00\x00"




def test_mastersystem2_vdp_positive_vertical_scroll_moves_background_down():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 1, 0x40)
    _vdp_set_register(machine, 9, 0x01)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    _vdp_set_address(machine, 0x0000, 0x01)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    for row in range(1, 8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()
    assert frame[0:3] == b"\x00\x00\x00"


def test_mastersystem2_vdp_vertical_scroll_lock_affects_rightmost_8_tile_columns():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 0, 0x80)
    _vdp_set_register(machine, 1, 0x40)
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 9, 0x01)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    _vdp_set_address(machine, 0x0000, 0x01)
    machine._port_write(0xBE, 0xFF)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    for row in range(1, 8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    for tile_y in range(28):
        _vdp_set_address(machine, name_base + tile_y * 32 * 2, 0x01)
        for _ in range(32):
            machine._port_write(0xBE, 0x00)
            machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()
    unlocked_col = 23 * 8
    locked_col = 24 * 8

    assert frame[unlocked_col * 3: unlocked_col * 3 + 3] == b"\x00\x00\x00"
    assert frame[locked_col * 3: locked_col * 3 + 3] != b"\x00\x00\x00"


def test_mastersystem2_vdp_blanks_when_display_is_disabled():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 2, 0x0E)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    assert machine.render_frame()[0:3] == b"\x00\x00\x00"


def test_mastersystem2_vdp_renders_basic_sprite():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)  # display on + 8x16 sprite bit path harmless here
    _vdp_set_register(machine, 5, 0x7E)

    # Sprite palette entry 1.
    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x03)

    # Pattern 0, first row: leftmost pixel colour 1.
    _vdp_set_address(machine, 0x0000, 0x01)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    # y table
    _vdp_set_address(machine, sat_base, 0x01)
    machine._port_write(0xBE, 0x00)  # sprite appears at y=1
    machine._port_write(0xBE, 0xD0)  # end marker
    # x/tile table
    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    machine._port_write(0xBE, 0x00)  # x
    machine._port_write(0xBE, 0x00)  # tile

    frame = machine.render_frame()

    assert frame[(1 * machine.SCREEN_WIDTH + 0) * 3: (1 * machine.SCREEN_WIDTH + 0) * 3 + 3] != b"\x00\x00\x00"


def test_mastersystem2_vdp_lower_sprite_index_has_priority():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)
    _vdp_set_register(machine, 5, 0x7E)

    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x03)
    _vdp_set_address(machine, 0x0012, 0x03)
    machine._port_write(0xBE, 0x30)

    _vdp_set_address(machine, 0x0000, 0x01)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    _vdp_set_address(machine, 0x0020, 0x01)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)

    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x01)

    frame = machine.render_frame()
    pixel = frame[(1 * machine.SCREEN_WIDTH + 0) * 3: (1 * machine.SCREEN_WIDTH + 0) * 3 + 3]

    assert pixel == bytes(machine.vdp._cram_color(0x11))


def test_mastersystem2_vdp_bg_priority_hides_sprite():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 5, 0x7E)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x03)
    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x30)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x10)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)
    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()
    pixel = frame[(1 * machine.SCREEN_WIDTH + 0) * 3: (1 * machine.SCREEN_WIDTH + 0) * 3 + 3]

    assert pixel == bytes(machine.vdp._cram_color(0x01))


def test_mastersystem2_vdp_sets_vblank_status_and_interrupts_when_enabled():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x20)

    machine.vdp.begin_frame()
    machine.vdp.run_until(machine.vdp.VBLANK_TSTATE - 1)
    assert machine.vdp.interrupt_fired is False
    assert machine.vdp.status & 0x80 == 0

    machine.vdp.run_until(machine.vdp.VBLANK_TSTATE + 1)
    status = machine._port_read(0xBF)

    assert status & 0x80 == 0x80
    assert machine.vdp.interrupt_fired is True
    assert machine.vdp.status & 0x80 == 0


def test_mastersystem2_vdp_renders_from_vblank_latched_state():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x40)
    _vdp_set_register(machine, 2, 0x0E)

    _vdp_set_address(machine, 0x0001, 0x03)
    machine._port_write(0xBE, 0x30)
    _vdp_set_address(machine, 0x0002, 0x03)
    machine._port_write(0xBE, 0x03)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        _vdp_set_address(machine, 0x20 + row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    machine.vdp.begin_frame()
    machine.vdp.run_until(machine.vdp.VBLANK_TSTATE + 1)

    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x01)
    machine._port_write(0xBE, 0x00)

    machine.vdp.end_frame()
    pixel = machine.vdp.framebuffer_rgb24[0:3]

    assert pixel == bytes(machine.vdp._cram_color(0x01))


def test_mastersystem2_vdp_triggers_line_interrupt_when_enabled():
    class _CPU:
        def __init__(self):
            self.calls = 0

        def interrupt(self):
            self.calls += 1

    class _Machine:
        TSTATES_PER_FRAME = MasterSystem2.TSTATES_PER_FRAME

        def __init__(self):
            self.cpu = _CPU()

    machine = _Machine()
    vdp = SMSVDPReference(machine)
    vdp.registers[0] = 0x10
    vdp.registers[10] = 0x00
    vdp.begin_frame()
    first_scanline_tstates = machine.TSTATES_PER_FRAME // vdp.TOTAL_SCANLINES
    vdp.run_until(first_scanline_tstates)

    assert machine.cpu.calls == 1


def test_mastersystem2_vdp_reloads_line_interrupt_counter():
    class _CPU:
        def __init__(self):
            self.calls = 0

        def interrupt(self):
            self.calls += 1

    class _Machine:
        TSTATES_PER_FRAME = MasterSystem2.TSTATES_PER_FRAME

        def __init__(self):
            self.cpu = _CPU()

    machine = _Machine()
    vdp = SMSVDPReference(machine)
    vdp.registers[0] = 0x10
    vdp.registers[10] = 0x01
    vdp.begin_frame()
    scanline_tstates = machine.TSTATES_PER_FRAME // vdp.TOTAL_SCANLINES
    vdp.run_until(scanline_tstates * 5)

    assert machine.cpu.calls == 2


def test_mastersystem2_vdp_line_counter_continues_past_visible_area_without_extra_irqs():
    class _CPU:
        def __init__(self):
            self.calls = 0

        def interrupt(self):
            self.calls += 1

    class _Machine:
        TSTATES_PER_FRAME = MasterSystem2.TSTATES_PER_FRAME

        def __init__(self):
            self.cpu = _CPU()

    machine = _Machine()
    vdp = SMSVDPReference(machine)
    vdp.registers[0] = 0x10
    vdp.registers[10] = 0x00
    vdp.begin_frame()
    late_scanline_tstates = (machine.TSTATES_PER_FRAME // vdp.TOTAL_SCANLINES) * 212
    vdp.run_until(late_scanline_tstates)

    assert machine.cpu.calls >= vdp.FRAME_HEIGHT
    assert vdp._line_interrupt_pending
    assert vdp._frame_interrupt_pending
    assert not (vdp.registers[1] & 0x20)
    vdp.read_control()
    assert not vdp._line_interrupt_pending
    assert not vdp._frame_interrupt_pending
    assert vdp._line_irq_counter != 0x00


def test_mastersystem2_vdp_sets_sprite_collision_flag():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)
    _vdp_set_register(machine, 5, 0x7E)

    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x03)
    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)
    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    machine.render_frame()

    assert machine.vdp.status & 0x20 == 0x20


def test_mastersystem2_vdp_sprite_zoom_doubles_rendered_width():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x43)  # display enabled + sprite zoom
    _vdp_set_register(machine, 5, 0x7E)

    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x03)
    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)
    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()
    pixel0 = frame[(1 * machine.SCREEN_WIDTH + 0) * 3: (1 * machine.SCREEN_WIDTH + 0) * 3 + 3]
    pixel1 = frame[(1 * machine.SCREEN_WIDTH + 1) * 3: (1 * machine.SCREEN_WIDTH + 1) * 3 + 3]

    assert pixel0 == bytes(machine.vdp._cram_color(0x11))
    assert pixel1 == bytes(machine.vdp._cram_color(0x11))


def test_mastersystem2_vdp_sets_sprite_overflow_flag_after_eight_sprites_per_line():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)
    _vdp_set_register(machine, 5, 0x7E)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    for _ in range(9):
        machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)

    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    for index in range(9):
        machine._port_write(0xBE, (index * 8) & 0xFF)
        machine._port_write(0xBE, 0x00)

    machine.render_frame()

    assert machine.vdp.status & 0x40 == 0x40


def test_mastersystem2_vdp_stops_sprite_list_at_d0_terminator():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)
    _vdp_set_register(machine, 5, 0x7E)

    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x03)
    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    machine._port_write(0xBE, 0x00)   # sprite 0 y
    machine._port_write(0xBE, 0xD0)   # terminator
    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    machine._port_write(0xBE, 0x00)   # sprite 0 x
    machine._port_write(0xBE, 0x00)   # sprite 0 tile
    machine._port_write(0xBE, 0x08)   # sprite 1 x, should be ignored
    machine._port_write(0xBE, 0x00)   # sprite 1 tile

    frame = machine.render_frame()
    pixel0 = frame[(1 * machine.SCREEN_WIDTH + 0) * 3: (1 * machine.SCREEN_WIDTH + 0) * 3 + 3]
    pixel8 = frame[(1 * machine.SCREEN_WIDTH + 8) * 3: (1 * machine.SCREEN_WIDTH + 8) * 3 + 3]

    assert pixel0 == bytes(machine.vdp._cram_color(0x11))
    assert pixel8 == b"\x00\x00\x00"


def test_mastersystem2_vdp_keeps_first_eight_sprites_per_line():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)
    _vdp_set_register(machine, 5, 0x7E)

    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x03)
    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    for _ in range(9):
        machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)

    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    for index in range(9):
        machine._port_write(0xBE, (index * 8) & 0xFF)
        machine._port_write(0xBE, 0x00)

    frame = machine.render_frame()
    pixel56 = frame[(1 * machine.SCREEN_WIDTH + 56) * 3: (1 * machine.SCREEN_WIDTH + 56) * 3 + 3]
    pixel64 = frame[(1 * machine.SCREEN_WIDTH + 64) * 3: (1 * machine.SCREEN_WIDTH + 64) * 3 + 3]

    assert pixel56 == bytes(machine.vdp._cram_color(0x11))
    assert pixel64 == b"\x00\x00\x00"


def test_mastersystem2_exposes_vdp_counters_on_7e_7f():
    machine = MasterSystem2(_make_test_rom())

    machine.vdp.run_until(machine.vdp.VBLANK_TSTATE)

    assert 0 <= machine._port_read(0x7E) <= 0xFF
    assert 0 <= machine._port_read(0x7F) <= 0xFF


def test_mastersystem2_de_df_are_independent_latches():
    machine = MasterSystem2(_make_test_rom())

    machine._port_write(0xDE, 0x07)
    machine._port_write(0xDF, 0x92)

    assert machine._port_read(0xDE) == 0x07
    assert machine._port_read(0xDF) == 0x92
    assert machine.memory_control == 0x00
    assert machine.io_control == 0x0F


def test_mastersystem2_memory_control_cb_leaves_open_bus_without_cart():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x23]) * 0x4000
    bios[0x10000:0x14000] = bytes([0x24]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    assert machine.peek(0x0000) == 0x10
    assert machine.peek(0x4000) == 0x11
    assert machine.peek(0x8000) == 0x22

    machine._port_write(0x3E, 0xCB)

    assert machine.active_rom_source == "none"
    assert machine.peek(0x0000) == 0xFF
    assert machine.peek(0x4000) == 0xFF
    assert machine.peek(0x8000) == 0xFF


def test_mastersystem2_memory_control_prefers_cart_when_present():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x23]) * 0x4000
    cart = bytearray(0x10000)
    cart[0x0000:0x4000] = bytes([0x30]) * 0x4000
    cart[0x4000:0x8000] = bytes([0x31]) * 0x4000
    cart[0x8000:0xC000] = bytes([0x32]) * 0x4000

    machine = MasterSystem2(bytes(cart), bios_data=bytes(bios))

    machine._port_write(0x3E, 0xCB)

    assert machine.active_rom_source == "cart"
    assert machine.peek(0x0000) == 0x30
    assert machine.peek(0x4000) == 0x31
    assert machine.peek(0x8000) == 0x32


def test_mastersystem2_memory_control_ab_also_selects_cart_when_present():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    cart = bytearray(0x10000)
    cart[0x0000:0x4000] = bytes([0x30]) * 0x4000
    cart[0x4000:0x8000] = bytes([0x31]) * 0x4000
    cart[0x8000:0xC000] = bytes([0x32]) * 0x4000

    machine = MasterSystem2(bytes(cart), bios_data=bytes(bios))

    machine._port_write(0x3E, 0xAB)

    assert machine.active_rom_source == "cart"


def test_mastersystem2_bios_mode_uses_absolute_slot2_bank_numbering():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x20]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x21]) * 0x4000
    bios[0x10000:0x14000] = bytes([0x22]) * 0x4000
    bios[0x14000:0x18000] = bytes([0x23]) * 0x4000
    bios[0x18000:0x1C000] = bytes([0x24]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    machine.poke(0xFFFF, 3)

    assert machine.active_rom_source == "bios"
    assert machine.peek(0x0000) == 0x10
    assert machine.peek(0x4000) == 0x11
    assert machine.peek(0x8000) == 0x21


def test_mastersystem2_state_roundtrip_preserves_bios_slot2_bank_numbering():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x20]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x21]) * 0x4000
    bios[0x10000:0x14000] = bytes([0x22]) * 0x4000
    bios[0x14000:0x18000] = bytes([0x23]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))
    machine.poke(0xFFFF, 5)

    state = machine.read_state()

    other = MasterSystem2(None, bios_data=bytes(bios))
    other.write_state(state)

    assert other.active_rom_source == "bios"
    assert other.frame_page_2 == 5
    assert other.peek(0x0000) == 0x10
    assert other.peek(0x4000) == 0x11
    assert other.peek(0x8000) == 0x23


def test_mastersystem2_state_roundtrip_preserves_bios_slot1_bank_numbering():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x20]) * 0x4000
    bios[0xC000:0x10000] = bytes([0x21]) * 0x4000
    bios[0x10000:0x14000] = bytes([0x22]) * 0x4000
    bios[0x14000:0x18000] = bytes([0x23]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))
    machine.poke(0xFFFE, 5)

    state = machine.read_state()

    other = MasterSystem2(None, bios_data=bytes(bios))
    other.write_state(state)

    assert other.active_rom_source == "bios"
    assert other.frame_page_1 == 5
    assert other.peek(0x0000) == 0x10
    assert other.peek(0x4000) == 0x23
    assert other.peek(0x8000) == 0x20


def test_mastersystem2_memory_control_e3_keeps_bios_selected():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    machine._port_write(0x3E, 0xE3)

    assert machine.active_rom_source == "bios"
    assert machine.peek(0x0000) == 0x10
    assert machine.peek(0x4000) == 0x11


def test_mastersystem2_memory_control_eb_exposes_open_bus_when_no_slot_selected():
    bios = bytearray(0x20000)
    bios[0x0000:0x4000] = bytes([0x10]) * 0x4000
    bios[0x4000:0x8000] = bytes([0x11]) * 0x4000
    bios[0x8000:0xC000] = bytes([0x22]) * 0x4000

    machine = MasterSystem2(None, bios_data=bytes(bios))

    machine._port_write(0x3E, 0xEB)

    assert machine.active_rom_source == "none"
    assert machine.peek(0x0000) == 0xFF
    assert machine.peek(0x4000) == 0xFF
    assert machine.peek(0x8000) == 0xFF


def test_mastersystem2_writes_psg_and_produces_audio_samples():
    machine = MasterSystem2(_make_test_rom())

    machine._port_write(0x7F, 0x80 | 0x00 | 0x01)
    machine._port_write(0x7F, 0x00)
    machine._port_write(0x7F, 0x90 | 0x00)
    machine._finish_frame()

    exact = machine._audio_samples_per_frame_exact
    assert len(machine.audio_samples) in {int(exact), int(exact) + 1}
    assert any(sample != 0 for sample in machine.audio_samples)


def test_mastersystem2_audio_sample_count_tracks_exact_frame_rate():
    machine = MasterSystem2(_make_test_rom(), audio_sample_rate=44_100)

    total = 0
    frames = 120
    for _ in range(frames):
        machine._begin_frame()
        machine._finish_frame()
        total += len(machine.audio_samples)

    expected = round(machine._audio_samples_per_frame_exact * frames)
    assert abs(total - expected) <= 1


def test_mastersystem2_key_matrix_updates_pad1_port_bits():
    machine = MasterSystem2(_make_test_rom())

    machine.handle_input_event(InputEvent("key_matrix", 0, 0, True))  # up
    machine.handle_input_event(InputEvent("key_matrix", 1, 0, True))  # button 1
    machine.handle_input_event(InputEvent("key_matrix", 1, 1, True))  # button 2

    assert machine._port_read(0xDC) & 0x01 == 0
    assert machine._port_read(0xDC) & 0x10 == 0
    assert machine._port_read(0xDC) & 0x20 == 0


def test_mastersystem2_joystick_event_updates_pad1_port_bits():
    machine = MasterSystem2(_make_test_rom())

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_RIGHT, True))
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_FIRE, True))
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_FIRE_2, True))

    assert machine._port_read(0xDC) & 0x08 == 0
    assert machine._port_read(0xDC) & 0x10 == 0
    assert machine._port_read(0xDC) & 0x20 == 0


def test_mastersystem2_io_control_affects_tr_th_lines():
    machine = MasterSystem2(_make_test_rom())

    machine._port_write(0x3F, 0x0D)  # TH-A output low
    assert machine._port_read(0xDD) & 0x40 == 0

    machine._port_write(0x3F, 0x2D)  # TH-A output high
    assert machine._port_read(0xDD) & 0x40 == 0x40


def test_mastersystem2_io_control_affects_tr_a_line_on_port_dc():
    machine = MasterSystem2(_make_test_rom())

    machine._port_write(0x3F, 0x0E)  # TR-A output low
    assert machine._port_read(0xDC) & 0x20 == 0

    machine._port_write(0x3F, 0x1E)  # TR-A output high
    assert machine._port_read(0xDC) & 0x20 == 0x20


def test_mastersystem2_th_transition_latches_h_counter():
    machine = MasterSystem2(_make_test_rom())
    machine.vdp.begin_frame()
    machine.vdp.run_until(machine.vdp._scanline_tstates // 2)

    machine._port_write(0x3F, 0x0D)  # TH-A output low
    assert machine._port_read(0x7F) == 0x00

    machine._port_write(0x3F, 0x2D)  # TH-A output high
    assert machine._port_read(0x7F) != 0x00


def _build_reference_equivalence_fixture() -> MasterSystem2:
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x42)
    _vdp_set_register(machine, 2, 0x0E)
    _vdp_set_register(machine, 5, 0x7E)
    _vdp_set_register(machine, 8, 0x07)
    _vdp_set_register(machine, 9, 0x03)

    for offset, value in (
        (0x0001, 0x30),
        (0x0011, 0x03),
        (0x0012, 0x21),
    ):
        _vdp_set_address(machine, offset, 0x03)
        machine._port_write(0xBE, value)

    for row in range(8):
        _vdp_set_address(machine, row * 4, 0x01)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)
        _vdp_set_address(machine, 0x20 + row * 4, 0x01)
        machine._port_write(0xBE, 0x81)
        machine._port_write(0xBE, 0x80)
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, 0x00)

    name_base = machine.vdp._name_table_base()
    _vdp_set_address(machine, name_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x10)
    machine._port_write(0xBE, 0x01)
    machine._port_write(0xBE, 0x0E)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)
    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x01)

    return machine


def _assert_vdp_matches_reference(machine: MasterSystem2) -> None:
    reference = SMSVDPReference(machine)
    reference.write_state(machine.vdp.read_state())
    assert machine.vdp.render_frame() == reference.render_frame()
    assert machine.vdp.status == reference.status


def test_mastersystem2_vdp_matches_python_reference_renderer():
    machine = _build_reference_equivalence_fixture()
    _assert_vdp_matches_reference(machine)


def test_mastersystem2_vdp_matches_reference_with_left_mask_enabled():
    machine = _build_reference_equivalence_fixture()
    _vdp_set_register(machine, 0, 0x20)
    _assert_vdp_matches_reference(machine)


def test_mastersystem2_vdp_matches_reference_with_top_rows_hscroll_lock():
    machine = _build_reference_equivalence_fixture()
    _vdp_set_register(machine, 0, 0x40)
    _vdp_set_register(machine, 8, 0x05)
    _assert_vdp_matches_reference(machine)


def test_mastersystem2_vdp_matches_reference_across_scroll_boundary():
    machine = _build_reference_equivalence_fixture()
    _vdp_set_register(machine, 8, 0x08)
    _assert_vdp_matches_reference(machine)


def test_mastersystem2_vdp_matches_reference_with_negative_wrapped_map_x():
    machine = _build_reference_equivalence_fixture()
    _vdp_set_register(machine, 8, 0x1F)

    _assert_vdp_matches_reference(machine)


def test_mastersystem2_vdp_matches_reference_with_sprite_zoom_enabled():
    machine = _build_reference_equivalence_fixture()
    _vdp_set_register(machine, 1, 0x43)
    _assert_vdp_matches_reference(machine)


def test_mastersystem2_vdp_matches_reference_with_sprite_collision_and_overflow():
    machine = MasterSystem2(_make_test_rom())
    _vdp_set_register(machine, 1, 0x43)
    _vdp_set_register(machine, 5, 0x7E)

    _vdp_set_address(machine, 0x0011, 0x03)
    machine._port_write(0xBE, 0x03)
    _vdp_set_address(machine, 0x0012, 0x03)
    machine._port_write(0xBE, 0x30)

    _vdp_set_address(machine, 0x0000, 0x01)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    _vdp_set_address(machine, 0x0020, 0x01)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x80)
    machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0x00)

    sat_base = machine.vdp._sprite_attribute_base()
    _vdp_set_address(machine, sat_base, 0x01)
    for _ in range(9):
        machine._port_write(0xBE, 0x00)
    machine._port_write(0xBE, 0xD0)

    _vdp_set_address(machine, sat_base + 0x80, 0x01)
    for index in range(9):
        machine._port_write(0xBE, 0x00)
        machine._port_write(0xBE, index & 0x01)

    _assert_vdp_matches_reference(machine)
