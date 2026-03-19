from __future__ import annotations

from devices.cpc_render import (
    build_horizontal_display_map as build_horizontal_display_map_accel,
    build_vertical_display_map as build_vertical_display_map_accel,
    compose_display_row as compose_display_row_accel,
    render_frame_rgb24_from_ram as render_frame_rgb24_from_ram_accel,
)
from devices import AY38912
from devices.cpc_crtc import HD6845
from machines.z80 import CPC464, Spectrum48K
from tests.fallbacks.ay38912_reference import AY38912 as AY38912Reference
from tests.fallbacks.cpc_render_reference import (
    build_horizontal_display_map as build_horizontal_display_map_reference,
    build_vertical_display_map as build_vertical_display_map_reference,
    compose_display_row as compose_display_row_reference,
    render_frame_rgb24_from_ram as render_frame_rgb24_from_ram_reference,
)
from tests.fallbacks.cpc_chip_references import (
    CPCGateArray as CPCGateArrayReference,
    HD6845 as HD6845Reference,
    Intel8255 as Intel8255Reference,
)
from tests.fallbacks.cpc_video_reference import CPCVideo as CPCVideoReference
from tests.fallbacks.ula_reference import Spectrum48KULA as Spectrum48KULAReference


def test_spectrum_ula_accel_matches_reference_renderer():
    machine = Spectrum48K(bytes([0x00]) * 0x4000)
    machine.border_color = 6
    machine.poke(0x4000, 0b10101010)
    machine.poke(0x4001, 0b01010101)
    machine.poke(0x5800, 0b0101_1011)
    machine.poke(0x5801, 0b1100_0101)

    reference_ula = Spectrum48KULAReference(machine)
    reference_ula.flash_phase = machine.ula.flash_phase

    assert machine.ula.render_frame() == reference_ula.render_frame()


def test_cpc_render_accel_matches_reference_renderer():
    machine = CPC464(bytes([0x00]) * 0x4000)

    machine._port_write(0x7F00, 0b00000001)
    machine._port_write(0x7F00, 0b01001100)
    machine._port_write(0x7F00, 0b00000010)
    machine._port_write(0x7F00, 0b01010101)
    machine.poke(0xC000, 0b10100101)
    machine.poke(0xC001, 0b01011010)

    video = machine.video
    border = machine.gate_array.HARDWARE_PALETTE[machine.frame_border_hardware_color]
    pen_rgb_map = [machine.gate_array.get_pen_rgb(pen) for pen in range(16)]
    total_left, total_top = video._get_total_raster_origin()

    horizontal_map_accel = build_horizontal_display_map_accel(
        video._get_total_raster_width(),
        video._get_pixels_per_character(),
        machine.crtc.horizontal_total,
        video._get_visible_char_count(),
        video._get_display_start_char(),
    )
    horizontal_map_reference = build_horizontal_display_map_reference(
        video._get_total_raster_width(),
        video._get_pixels_per_character(),
        machine.crtc.horizontal_total,
        video._get_visible_char_count(),
        video._get_display_start_char(),
    )
    vertical_map_accel = build_vertical_display_map_accel(
        video._get_frame_scanline_count(),
        machine.crtc.raster_height,
        video._get_visible_raster_height(),
        machine.crtc.vertical_total,
        machine.crtc.vertical_total_adjust,
        video._get_visible_row_count(),
        video._get_display_start_row(),
        video._get_vsync_start_line(),
        video._get_vsync_height(),
    )
    vertical_map_reference = build_vertical_display_map_reference(
        video._get_frame_scanline_count(),
        machine.crtc.raster_height,
        video._get_visible_raster_height(),
        machine.crtc.vertical_total,
        machine.crtc.vertical_total_adjust,
        video._get_visible_row_count(),
        video._get_display_start_row(),
        video._get_vsync_start_line(),
        video._get_vsync_height(),
    )

    assert horizontal_map_accel == horizontal_map_reference
    assert vertical_map_accel == vertical_map_reference

    row_bytes = video._get_display_row_bytes(0, 0)
    assert compose_display_row_accel(
        row_bytes,
        horizontal_map_accel,
        total_left,
        machine.frame_width,
        border,
        machine.frame_gate_mode,
        pen_rgb_map,
    ) == compose_display_row_reference(
        row_bytes,
        horizontal_map_reference,
        total_left,
        machine.frame_width,
        border,
        machine.frame_gate_mode,
        pen_rgb_map,
    )

    assert render_frame_rgb24_from_ram_accel(
        machine.ram,
        machine.frame_display_start_address,
        machine.crtc.horizontal_displayed,
        video._get_visible_char_count(),
        video._get_visible_raster_height(),
        horizontal_map_accel,
        vertical_map_accel,
        total_left,
        total_top,
        machine.frame_width,
        machine.frame_height,
        border,
        machine.frame_gate_mode,
        pen_rgb_map,
    ) == render_frame_rgb24_from_ram_reference(
        machine.ram,
        machine.frame_display_start_address,
        machine.crtc.horizontal_displayed,
        video._get_visible_char_count(),
        video._get_visible_raster_height(),
        horizontal_map_reference,
        vertical_map_reference,
        total_left,
        total_top,
        machine.frame_width,
        machine.frame_height,
        border,
        machine.frame_gate_mode,
        pen_rgb_map,
    )


def test_cpc_video_accel_matches_reference_video_class():
    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0x7F00, 0b00000001)
    machine._port_write(0x7F00, 0b01001100)
    machine.poke(0xC000, 0b01011010)

    reference_video = CPCVideoReference(machine)
    reference_video.render_frame()

    assert machine.video._get_active_display_origin() == reference_video._get_active_display_origin()
    assert machine.video._decode_crtc_scanline(0) == reference_video._decode_crtc_scanline(0)
    assert machine.video.render_frame() == reference_video._render_crtc_frame_rgb24()
    assert machine.video.framebuffer_rgb24 == reference_video.framebuffer_rgb24


def test_cpc_gate_array_accel_matches_reference_chip():
    machine = CPC464(bytes([0x00]) * 0x4000, basic_rom_data=bytes([0x00]) * 0x4000)
    reference = CPCGateArrayReference(machine)

    for value in (0b00000001, 0b01001100, 0b00010000, 0b01010101, 0b10001101):
        machine.gate_array.write(value)
        reference.write(value)

    machine.gate_array.begin_scanline(True)
    reference.begin_scanline(True)
    machine.gate_array.end_scanline()
    reference.end_scanline()

    assert machine.gate_array.selected_pen == reference.selected_pen
    assert machine.gate_array.border_hardware_color == reference.border_hardware_color
    assert machine.gate_array.pen_colors == reference.pen_colors
    assert machine.gate_array.mode == reference.mode
    assert machine.gate_array.get_border_rgb() == reference.get_border_rgb()
    assert machine.gate_array.pop_pending_interrupt() == reference.pop_pending_interrupt()


def test_hd6845_accel_matches_reference_chip():
    accel = HD6845()
    reference = HD6845Reference()

    for register_index, value in ((0, 31), (1, 40), (2, 12), (7, 28), (12, 0x20), (13, 0x10)):
        accel.select_register(register_index)
        accel.write_selected(value)
        reference.select_register(register_index)
        reference.write_selected(value)

    assert accel.registers == reference.registers
    assert accel.horizontal_total == reference.horizontal_total
    assert accel.vertical_total == reference.vertical_total
    assert accel.raster_height == reference.raster_height
    assert accel.display_start_address == reference.display_start_address


def test_intel8255_accel_matches_reference_chip():
    machine = CPC464(bytes([0x00]) * 0x4000)
    reference = Intel8255Reference(machine)

    for value in (0x55, 0xC0, 0x82, 0x0F):
        machine.ppi.write_port_a(value)
        reference.write_port_a(value)
        machine.ppi.write_port_c(value)
        reference.write_port_c(value)
        machine.ppi.write_control(value)
        reference.write_control(value)

    assert machine.ppi.port_a_latch == reference.port_a_latch
    assert machine.ppi.port_c_latch == reference.port_c_latch
    assert machine.ppi.selected_keyboard_line == reference.selected_keyboard_line
    assert machine.ppi.psg_function == reference.psg_function
    assert machine.ppi.read_port_c() == reference.read_port_c()


def test_ay38912_accel_matches_reference_chip():
    state = {"port_a": 0xE7, "port_b": 0x3C, "written_a": None, "written_b": None}

    accel = AY38912(
        clock_hz=1_000_000,
        sample_rate=8_000,
        port_a_read=lambda: state["port_a"],
        port_a_write=lambda value: state.__setitem__("written_a", value),
        port_b_read=lambda: state["port_b"],
        port_b_write=lambda value: state.__setitem__("written_b", value),
        port_a_read_through_output=True,
    )
    reference = AY38912Reference(
        clock_hz=1_000_000,
        sample_rate=8_000,
        port_a_read=lambda: state["port_a"],
        port_a_write=lambda value: state.__setitem__("written_a", value),
        port_b_read=lambda: state["port_b"],
        port_b_write=lambda value: state.__setitem__("written_b", value),
        port_a_read_through_output=True,
    )

    for register_index, value in (
        (0, 2),
        (1, 0),
        (6, 3),
        (7, 0x80),
        (8, 0x10),
        (11, 1),
        (12, 0),
        (13, 0x0E),
        (14, 0x5A),
        (15, 0xA7),
    ):
        accel.select_register(register_index)
        accel.write_selected(value)
        reference.select_register(register_index)
        reference.write_selected(value)

    accel.select_register(14)
    reference.select_register(14)

    assert accel.read_selected() == reference.read_selected()
    assert accel.registers == reference.registers
    assert accel.port_a_is_input == reference.port_a_is_input
    assert accel.port_b_is_input == reference.port_b_is_input
    assert accel.render_samples(64) == reference.render_samples(64)
