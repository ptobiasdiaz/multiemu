from __future__ import annotations

"""Smoke coverage for the first-pass CPC 464 machine model."""

from frontend.input_events import InputEvent
from machines.z80 import CPC464


def _pixel_at_rgb24(packed: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    pixel_offset = ((y * width) + x) * 3
    return tuple(packed[pixel_offset:pixel_offset + 3])


def test_cpc464_lower_rom_is_visible_but_writes_hit_underlying_ram():
    machine = CPC464(bytes([0xAA]) * 0x4000)

    assert machine.peek(0x0000) == 0xAA

    machine.poke(0x0000, 0x55)

    assert machine.peek(0x0000) == 0xAA
    machine.set_rom_configuration(lower_rom_enabled=False)
    assert machine.peek(0x0000) == 0x55


def test_cpc464_upper_rom_visibility_can_be_toggled():
    machine = CPC464(bytes([0x00]) * 0x4000, basic_rom_data=bytes([0xCC]) * 0x4000)

    assert machine.peek(0xC000) == 0xCC

    machine.poke(0xC000, 0x33)
    machine.set_rom_configuration(upper_rom_enabled=False)

    assert machine.peek(0xC000) == 0x33


def test_cpc464_gate_array_rom_configuration_changes_memory_visibility():
    machine = CPC464(bytes([0xAA]) * 0x4000, basic_rom_data=bytes([0xCC]) * 0x4000)

    machine.poke(0x0000, 0x11)
    machine.poke(0xC000, 0x22)

    machine._port_write(0x7F00, 0b10001101)

    assert machine.gate_array.mode == 1
    assert machine.lower_rom_enabled is False
    assert machine.upper_rom_enabled is False
    assert machine.peek(0x0000) == 0x11
    assert machine.peek(0xC000) == 0x22


def test_cpc464_gate_array_border_colour_reaches_rgb24_output():
    machine = CPC464(bytes([0x00]) * 0x4000)

    machine._port_write(0x7F00, 0b00010000)  # Select border
    machine._port_write(0x7F00, 0b01001100)  # Bright Red
    packed = machine.render_frame()

    assert machine.gate_array.border_hardware_color == 12
    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.gate_array.get_border_rgb()


def test_cpc464_crtc_register_write_changes_display_start_address():
    machine = CPC464(bytes([0x00]) * 0x4000)

    machine._port_write(0xBC00, 12)
    machine._port_write(0xBD00, 0x20)
    machine._port_write(0xBC00, 13)
    machine._port_write(0xBD00, 0x10)

    assert machine.crtc.display_start_address == 0x2010


def test_cpc464_display_line_base_address_matches_default_screen_layout():
    """The default CPC screen layout should start at &C000 and bank by raster."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    assert machine.video._get_display_line_base_address(0, 0) == 0xC000
    assert machine.video._get_display_line_base_address(0, 1) == 0xC800
    assert machine.video._get_display_line_base_address(1, 0) == 0xC050


def test_cpc464_crtc_ma_ra_mapping_matches_video_page_layout():
    """MA/RA translation should follow the CPC Gate Array memory layout."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    assert machine.video._map_crtc_address_to_ram(0x3000, 0) == 0xC000
    assert machine.video._map_crtc_address_to_ram(0x3001, 0) == 0xC002
    assert machine.video._map_crtc_address_to_ram(0x3000, 7) == 0xF800
    assert machine.video._map_crtc_address_to_ram(0x0000, 0) == 0x0000


def test_cpc464_mode1_render_uses_video_ram_and_palette():
    machine = CPC464(bytes([0x00]) * 0x4000)

    # Select pen 1 and give it bright red.
    machine._port_write(0x7F00, 0b00000001)
    machine._port_write(0x7F00, 0b01001100)

    # Select pen 2 and give it bright blue.
    machine._port_write(0x7F00, 0b00000010)
    machine._port_write(0x7F00, 0b01010101)

    # With the default CRTC start at &C000, this byte becomes four mode 1
    # pixels with pen sequence 2, 1, 2, 1.
    machine.poke(0xC000, 0b10100101)
    packed = machine.render_frame()
    origin_x, origin_y = machine.video._get_active_display_origin()

    assert _pixel_at_rgb24(packed, machine.frame_width, origin_x + 0, origin_y) == machine.gate_array.get_pen_rgb(2)
    assert _pixel_at_rgb24(packed, machine.frame_width, origin_x + 1, origin_y) == machine.gate_array.get_pen_rgb(1)
    assert _pixel_at_rgb24(packed, machine.frame_width, origin_x + 2, origin_y) == machine.gate_array.get_pen_rgb(2)
    assert _pixel_at_rgb24(packed, machine.frame_width, origin_x + 3, origin_y) == machine.gate_array.get_pen_rgb(1)


def test_cpc464_render_exposes_rgb24_framebuffer_for_frontends():
    machine = CPC464(bytes([0x00]) * 0x4000)

    machine._port_write(0x7F00, 0b00000001)
    machine._port_write(0x7F00, 0b01001100)
    machine.poke(0xC000, 0b01011010)
    packed = machine.render_frame()
    origin_x, origin_y = machine.video._get_active_display_origin()

    assert isinstance(packed, bytes)
    assert len(packed) == machine.frame_width * machine.frame_height * 3
    assert _pixel_at_rgb24(packed, machine.frame_width, origin_x, origin_y) == machine.gate_array.get_pen_rgb(1)


def test_cpc464_display_row_bytes_wrap_within_the_same_raster_bank():
    """Visible scanlines should wrap by MA, not by linear RAM spill."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    machine.poke(0xC7FC, 0x11)
    machine.poke(0xC7FD, 0x22)
    machine.poke(0xC7FE, 0x33)
    machine.poke(0xC7FF, 0x44)
    machine.poke(0xC000, 0x55)
    machine.poke(0xC001, 0x66)
    machine.poke(0xC002, 0x77)
    machine.poke(0xC003, 0x88)
    machine.poke(0xC800, 0x99)
    machine.poke(0xC801, 0xAA)

    row_bytes = machine.video._get_display_row_bytes(0, 0, display_start_address=0x33FE)

    assert row_bytes[:8] == [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]
    assert row_bytes[:6] != [0x11, 0x22, 0x33, 0x44, 0x99, 0xAA]


def test_cpc464_render_centres_active_area_inside_border():
    """The first-pass CPC renderer should expose a visible border area."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    packed = machine.render_frame()
    origin_x, origin_y = machine.video._get_active_display_origin()

    assert len(packed) == machine.FRAME_WIDTH * machine.FRAME_HEIGHT * 3
    assert origin_x > 0
    assert origin_y > 0
    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.gate_array.get_border_rgb()
    assert machine.video._get_total_raster_origin()[1] < 0
    assert origin_y == 20


def test_cpc464_active_origin_tracks_crtc_sync_positions():
    """CRTC sync registers should move the rendered active area."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    origin_before = machine.video._get_active_display_origin()

    machine._port_write(0xBC00, 2)
    machine._port_write(0xBD00, 50)
    machine._port_write(0xBC00, 7)
    machine._port_write(0xBD00, 28)

    origin_after = machine.video._get_active_display_origin()

    assert origin_after[0] > origin_before[0]
    assert origin_after[1] != origin_before[1]


def test_cpc464_horizontal_visible_window_uses_wrapped_crtc_character_space():
    """Horizontal placement should wrap relative to HSYNC inside the raster."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    assert machine.video._get_visible_char_count() == 40
    assert machine.video._get_display_start_char() == 10
    assert machine.video._get_active_x_offset_in_raster() == 80

    machine._port_write(0xBC00, 2)
    machine._port_write(0xBD00, 10)

    assert machine.video._get_display_start_char() == 38
    assert machine.video._get_active_x_offset_in_raster() == 304


def test_cpc464_visible_width_clamps_to_horizontal_total():
    """The visible width should not exceed the CRTC total character count."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 0)
    machine._port_write(0xBD00, 31)
    machine._port_write(0xBC00, 1)
    machine._port_write(0xBD00, 40)

    assert machine.crtc.horizontal_total == 32
    assert machine.crtc.horizontal_displayed == 40
    assert machine.video._get_visible_char_count() == 32
    assert machine.video._get_visible_width() == 256
    assert machine.video._get_video_bytes_per_row() == 64


def test_cpc464_map_raster_x_to_display_pixel_handles_horizontal_wrap():
    """Raster X coordinates should map through the wrapped visible character window."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 2)
    machine._port_write(0xBD00, 10)

    assert machine.video._get_display_start_char() == 38
    assert machine.video._map_crtc_char_to_display_char(38) == 0
    assert machine.video._map_crtc_char_to_display_char(39) == 1
    assert machine.video._map_crtc_char_to_display_char(0) == 26
    assert machine.video._map_crtc_char_to_display_char(37) is None
    assert machine.video._map_raster_x_to_display_pixel(304) == 0
    assert machine.video._map_raster_x_to_display_pixel(311) == 7
    assert machine.video._map_raster_x_to_display_pixel(0) == 208
    assert machine.video._map_raster_x_to_display_pixel(48) == 256


def test_cpc464_render_splits_visible_pixels_across_frame_edges_when_window_wraps():
    """A wrapped visible window should render at both raster edges, not as one block."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 2)
    machine._port_write(0xBD00, 10)
    machine._port_write(0x7F00, 0b00000001)
    machine._port_write(0x7F00, 0b01001100)
    machine.load_ram(0xC000, bytes([0x0F]) * 0x50)

    packed = machine.render_frame()
    border = machine.gate_array.get_border_rgb()
    pen1 = machine.gate_array.get_pen_rgb(1)
    origin_y = machine.video._get_active_display_origin()[1]

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, origin_y) == pen1
    assert _pixel_at_rgb24(packed, machine.frame_width, 63, origin_y) == pen1
    assert _pixel_at_rgb24(packed, machine.frame_width, 64, origin_y) == border
    assert _pixel_at_rgb24(packed, machine.frame_width, 255, origin_y) == border
    assert _pixel_at_rgb24(packed, machine.frame_width, 304, origin_y) == pen1
    assert _pixel_at_rgb24(packed, machine.frame_width, 383, origin_y) == pen1


def test_cpc464_vsync_window_is_derived_from_crtc_registers():
    """The CPC frame loop should expose VSYNC using the programmed CRTC pulse."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    assert machine.video._get_frame_scanline_count() == 312
    assert machine.video._get_vsync_start_line() == 240
    assert machine.video._get_vsync_height() == 8
    assert machine.video._is_vsync_scanline(239) is False
    assert machine.video._is_vsync_scanline(240) is True
    assert machine.video._is_vsync_scanline(247) is True
    assert machine.video._is_vsync_scanline(248) is False


def test_cpc464_gate_array_interrupt_fires_every_52_lines():
    """The CPC Gate Array should request INT every 52 HSYNC-equivalent lines."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    for _ in range(51):
        machine.gate_array.end_scanline()
        assert machine.gate_array.pop_pending_interrupt() is False

    machine.gate_array.end_scanline()

    assert machine.gate_array.pop_pending_interrupt() is True
    assert machine.gate_array.interrupt_line_counter == 0


def test_cpc464_gate_array_vsync_resets_counter_after_two_lines_without_irq_below_bit5():
    """VSYNC should clear the HSYNC counter after two lines when bit 5 is clear."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine.gate_array.interrupt_line_counter = 12

    machine.gate_array.begin_scanline(True)
    machine.gate_array.end_scanline()
    assert machine.gate_array.interrupt_line_counter == 13
    assert machine.gate_array.pop_pending_interrupt() is False

    machine.gate_array.begin_scanline(True)
    machine.gate_array.end_scanline()

    assert machine.gate_array.interrupt_line_counter == 0
    assert machine.gate_array.pop_pending_interrupt() is False


def test_cpc464_gate_array_vsync_can_raise_irq_when_counter_bit5_is_set():
    """VSYNC should trigger an IRQ after two lines if the counter reached bit 5."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine.gate_array.interrupt_line_counter = 40

    machine.gate_array.begin_scanline(True)
    machine.gate_array.end_scanline()
    machine.gate_array.begin_scanline(True)
    machine.gate_array.end_scanline()

    assert machine.gate_array.pop_pending_interrupt() is True
    assert machine.gate_array.interrupt_line_counter == 0


def test_cpc464_decode_crtc_scanline_tracks_raw_row_and_raster():
    """Raw scanline decoding should follow the CRTC row/raster progression."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    assert machine.video._decode_crtc_scanline(0) == (0, 0)
    assert machine.video._decode_crtc_scanline(39) == (4, 7)
    assert machine.video._decode_crtc_scanline(40) == (5, 0)
    assert machine.video._decode_crtc_scanline(240) == (30, 0)


def test_cpc464_decode_display_scanline_maps_visible_raster_to_char_rows():
    """Visible raster lines should map to the expected character row/raster."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    assert machine.video._decode_display_scanline(39) is None
    assert machine.video._decode_display_scanline(40) == (0, 0)
    assert machine.video._decode_display_scanline(41) == (0, 1)
    assert machine.video._decode_display_scanline(48) == (1, 0)


def test_cpc464_decode_crtc_scanline_keeps_full_r9_height_for_timing():
    """CRTC timing should honour rasters above 7 even if they are not visible."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 9)
    machine._port_write(0xBD00, 9)

    assert machine.crtc.raster_height == 10
    assert machine.video._decode_crtc_scanline(8) == (0, 8)
    assert machine.video._decode_crtc_scanline(9) == (0, 9)
    assert machine.video._decode_crtc_scanline(10) == (1, 0)


def test_cpc464_decode_display_scanline_hides_rasters_above_visible_gate_array_limit():
    """The Gate Array still exposes only 8 visible rasters per character row."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 9)
    machine._port_write(0xBD00, 9)

    assert machine.video._get_visible_raster_height() == 8
    assert machine.video._decode_display_scanline(49) is None
    assert machine.video._decode_display_scanline(50) == (0, 0)
    assert machine.video._decode_display_scanline(57) == (0, 7)
    assert machine.video._decode_display_scanline(58) is None


def test_cpc464_display_start_row_wraps_when_visible_window_crosses_frame_end():
    """If R7 < R6, the visible CRTC rows should wrap across the frame boundary."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 6)
    machine._port_write(0xBD00, 10)
    machine._port_write(0xBC00, 7)
    machine._port_write(0xBD00, 4)

    assert machine.crtc.vertical_total == 39
    assert machine.video._get_visible_row_count() == 10
    assert machine.video._get_display_start_row() == 33
    assert machine.video._map_crtc_row_to_display_row(33) == 0
    assert machine.video._map_crtc_row_to_display_row(38) == 5
    assert machine.video._map_crtc_row_to_display_row(0) == 6
    assert machine.video._map_crtc_row_to_display_row(3) == 9
    assert machine.video._map_crtc_row_to_display_row(4) is None


def test_cpc464_decode_display_scanline_handles_wrapped_visible_rows():
    """Visible scanline decoding should keep working when the window wraps."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 6)
    machine._port_write(0xBD00, 10)
    machine._port_write(0xBC00, 7)
    machine._port_write(0xBD00, 4)

    assert machine.video._decode_display_scanline(0) == (6, 0)
    assert machine.video._decode_display_scanline(24) == (9, 0)
    assert machine.video._decode_display_scanline(32) is None
    assert machine.video._decode_display_scanline(264) == (0, 0)


def test_cpc464_map_raster_y_to_display_scanline_handles_wrapped_visible_rows():
    """Raster-space Y should map into a linear visible scanline index."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 6)
    machine._port_write(0xBD00, 10)
    machine._port_write(0xBC00, 7)
    machine._port_write(0xBD00, 4)

    assert machine.video._map_raster_y_to_display_scanline(0) == 48
    assert machine.video._map_raster_y_to_display_scanline(24) == 72
    assert machine.video._map_raster_y_to_display_scanline(32) is None
    assert machine.video._map_raster_y_to_display_scanline(264) == 0


def test_cpc464_active_y_offset_uses_wrapped_raster_position():
    """Vertical active origin should track the wrapped display start row."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 6)
    machine._port_write(0xBD00, 10)
    machine._port_write(0xBC00, 7)
    machine._port_write(0xBD00, 4)

    assert machine.video._get_display_start_row() == 33
    assert machine.video._get_active_y_offset_in_raster() == 264


def test_cpc464_vsync_start_wraps_when_r7_exceeds_vertical_total():
    """VSYNC position should wrap in CRTC row space, not spill past the frame."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 7)
    machine._port_write(0xBD00, 40)

    assert machine.crtc.vertical_total == 39
    assert machine.video._get_vsync_start_line() == 8
    assert machine.video._is_vsync_scanline(8) is True
    assert machine.video._is_vsync_scanline(7) is False


def test_cpc464_vertical_total_adjust_extends_frame_but_not_visible_scanlines():
    """R5 should add timing scanlines without exposing extra displayed rasters."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0xBC00, 5)
    machine._port_write(0xBD00, 3)

    assert machine.video._get_frame_scanline_count() == 315
    assert machine.video._decode_crtc_scanline(312) == (38, 8)
    assert machine.video._decode_crtc_scanline(314) == (38, 10)
    assert machine.video._decode_display_scanline(312) is None
    assert machine.video._decode_display_scanline(314) is None


def test_cpc464_render_uses_frame_latched_display_start_address():
    """Mid-frame changes to R12/R13 should not tear the text scroll render."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine.frame_display_start_address = 0x3000
    machine.line_display_start_addresses[40] = 0x3040

    assert (
        machine.video._get_display_line_base_address(
            0,
            0,
            display_start_address=machine.frame_display_start_address,
        )
        == 0xC000
    )


def test_cpc464_render_uses_frame_latched_gate_array_state():
    """Visible render should stay stable if GA state changes mid-frame."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine.frame_gate_mode = 1
    machine.frame_border_hardware_color = 12
    machine.line_gate_modes[40] = 0
    machine.line_border_colours[40] = 20
    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 0) == machine.gate_array.HARDWARE_PALETTE[12]


def test_cpc464_render_keeps_border_visible_across_hsync_timing_region():
    """Sync pulses affect timing, but the visible frame should still show border."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0x7F00, 0b00010000)  # Select border
    machine._port_write(0x7F00, 0b01001100)  # Bright Red
    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 367, 0) == machine.gate_array.get_border_rgb()
    assert _pixel_at_rgb24(packed, machine.frame_width, 368, 0) == machine.gate_array.get_border_rgb()
    assert _pixel_at_rgb24(packed, machine.frame_width, 383, 0) == machine.gate_array.get_border_rgb()


def test_cpc464_render_keeps_border_visible_during_vsync_timing_lines():
    """VSYNC is not directly visible as a black bar in the final monitor image."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine._port_write(0x7F00, 0b00010000)  # Select border
    machine._port_write(0x7F00, 0b01001100)  # Bright Red
    packed = machine.render_frame()

    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 239) == machine.gate_array.get_border_rgb()
    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 240) == machine.gate_array.get_border_rgb()
    assert _pixel_at_rgb24(packed, machine.frame_width, 0, 247) == machine.gate_array.get_border_rgb()


def test_cpc464_keyboard_matrix_updates_from_input_events():
    machine = CPC464(bytes([0x00]) * 0x4000)

    machine.handle_input_event(InputEvent(kind="key_matrix", control_a=8, control_b=5, active=True))

    assert machine.read_keyboard_line(8) == 0xDF


def test_cpc464_keyboard_can_be_read_through_ppi_and_psg():
    machine = CPC464(bytes([0x00]) * 0x4000)
    machine.clear_input_state()
    machine.handle_input_event(InputEvent(kind="key_matrix", control_a=8, control_b=5, active=True))

    machine._port_write(0xF400, 14)      # PSG register 14 = keyboard port
    machine._port_write(0xF600, 0xC8)    # Select PSG register, keyboard line 8
    machine._port_write(0xF700, 0x92)    # PPI config: Port A input, Port B input, Port C output
    machine._port_write(0xF600, 0x48)    # Read PSG register 14 from keyboard line 8

    assert machine._port_read(0xF400) == 0xDF


def test_cpc464_psg_register_selection_works_when_port_a_is_written_last():
    machine = CPC464(bytes([0x00]) * 0x4000)
    machine.clear_input_state()
    machine.handle_input_event(InputEvent(kind="key_matrix", control_a=8, control_b=5, active=True))

    machine._port_write(0xF700, 0x92)    # PPI config: Port A input, Port B input, Port C output
    machine._port_write(0xF600, 0xC8)    # Select-register mode, keyboard line 8
    machine._port_write(0xF400, 14)      # Register number written after port C
    machine._port_write(0xF600, 0x48)    # Read mode

    assert machine._port_read(0xF400) == 0xDF


def test_cpc464_keyboard_reads_survive_firmware_switching_psg_port_a_to_output():
    """CPC firmware writes register 7 with port A as output during boot."""

    machine = CPC464(bytes([0x00]) * 0x4000)
    machine.clear_input_state()
    machine.handle_input_event(InputEvent(kind="key_matrix", control_a=8, control_b=5, active=True))

    machine.psg.select_register(7)
    machine.psg.write_selected(0x3F)

    machine._port_write(0xF400, 14)
    machine._port_write(0xF600, 0xC8)
    machine._port_write(0xF700, 0x92)
    machine._port_write(0xF600, 0x48)

    assert machine._port_read(0xF400) == 0xDF


def test_cpc464_runs_several_interrupts_per_frame():
    machine = CPC464(bytes([0x00]) * 0x4000, basic_rom_data=bytes([0x00]) * 0x4000)

    machine.run_frame()

    assert machine.interrupt_counter >= 5


def test_cpc464_pushes_psg_audio_into_the_machine_ring_buffer():
    """The CPC frontend path should receive AY audio rendered per frame."""

    machine = CPC464(bytes([0x00]) * 0x4000)

    machine.psg.select_register(0)
    machine.psg.write_selected(2)
    machine.psg.select_register(1)
    machine.psg.write_selected(0)
    machine.psg.select_register(8)
    machine.psg.write_selected(0x0F)

    machine.run_frame()

    assert machine.get_audio_buffered_samples() > 0
    samples = machine.pop_audio_samples(machine.get_audio_buffered_samples())
    assert any(sample != 0 for sample in samples)
