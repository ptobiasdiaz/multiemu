from __future__ import annotations

from machines import M6502MachineBase
from machines.m6502 import VIC20, VIC20PAL
from frontend.input_events import InputEvent
from multiemu.machine_registry import get_machine_spec, instantiate_machine, parse_cli_rom_specs


def _make_vic20_rom(
    size: int,
    *,
    fill: int = 0xEA,
    reset_vector: int | None = None,
) -> bytes:
    rom = bytearray([fill] * size)
    if reset_vector is not None and size >= 0x2000:
        vector_offset = size - 4
        rom[vector_offset] = reset_vector & 0xFF
        rom[vector_offset + 1] = (reset_vector >> 8) & 0xFF
    return bytes(rom)


def _make_vic20_machine(**kwargs) -> VIC20:
    return VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        _make_vic20_rom(0x1000),
        **kwargs,
    )


def _make_vic20pal_machine(**kwargs) -> VIC20PAL:
    return VIC20PAL(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        _make_vic20_rom(0x1000),
        **kwargs,
    )


def _pixel_at_rgb24(packed: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    offset = (y * width + x) * 3
    return (packed[offset], packed[offset + 1], packed[offset + 2])


def test_vic20_machine_exposes_expected_geometry_and_family():
    machine = _make_vic20_machine()

    assert machine.machine_id == "vic20ntsc"
    assert machine.display_name == "Commodore VIC-20 NTSC (early scaffold)"
    assert isinstance(machine, M6502MachineBase)
    assert machine.frame_width == 200
    assert machine.frame_height == 234
    assert len(machine.framebuffer_rgb24) == machine.frame_width * machine.frame_height * 3


def test_vic20pal_machine_exposes_expected_geometry_and_family():
    machine = _make_vic20pal_machine()

    assert machine.machine_id == "vic20pal"
    assert machine.display_name == "Commodore VIC-20 PAL (early scaffold)"
    assert isinstance(machine, M6502MachineBase)
    assert machine.frame_width == 224
    assert machine.frame_height == 284
    assert machine.SCANLINES_PER_FRAME == 312
    assert machine.FRAMES_PER_SECOND == 50
    assert machine.VISIBLE_RASTER_START == 28
    assert len(machine.framebuffer_rgb24) == machine.frame_width * machine.frame_height * 3


def test_vic20_maps_basic_kernal_char_and_base_ram_blocks():
    machine = _make_vic20_machine()

    assert machine.cpu.PC == 0xE000
    assert machine.bus.read8(0x0000) == 0x00
    assert machine.bus.read8(0x1000) == 0x00
    assert machine.bus.read8(0x8000) == 0xEA
    assert machine.bus.read8(0xC000) == 0xEA
    assert machine.bus.read8(0xE000) == 0xEA
    assert machine.bus.read8(0x9000) == 0x05
    assert machine.bus.read8(0x9002) == 0x16
    assert machine.bus.read8(0x9005) == 0xC0
    assert machine.bus.read8(0x900F) == 0x1B
    assert machine.bus.read8(0x9110) == 0xFF
    assert machine.bus.read8(0x9120) == 0xFF
    assert machine.bus.read8(0x9400) == 0x00
    assert machine.bus.read8(0x9600) == 0x00
    assert machine.bus.read8(0x9800) == 0x00
    assert machine.bus.read8(0x9C00) == 0xFF


def test_vic20_optional_expansion_blocks_map_into_expected_addresses():
    blk1 = bytes([0x11]) * 0x2000
    blk2 = bytes([0x22]) * 0x2000
    blk3 = bytes([0x33]) * 0x2000
    blk5 = bytes([0x55]) * 0x2000
    machine = _make_vic20_machine(
        blk1_rom_data=blk1,
        blk2_rom_data=blk2,
        blk3_rom_data=blk3,
        blk5_rom_data=blk5,
    )

    assert machine.bus.read8(0x2000) == 0x11
    assert machine.bus.read8(0x4000) == 0x22
    assert machine.bus.read8(0x6000) == 0x33
    assert machine.bus.read8(0xA000) == 0x55


def test_vic20_color_ram_masks_writes_to_low_nibble():
    machine = _make_vic20_machine()

    machine.bus.write8(0x9400, 0xAF)

    assert machine.bus.read8(0x9400) == 0x0F
    assert machine.bus.read8(0x9600) == 0x0F
    assert machine.color_ram.peek(0x0000) == 0x0F


def test_vic20_via_lines_are_wired_to_nmi_and_irq():
    machine = _make_vic20_machine()

    machine.bus.write8(0x911E, 0xC0)
    machine.bus.write8(0x9114, 0x01)
    machine.bus.write8(0x9115, 0x00)
    machine.run_cycles(2)
    assert machine.bus.nmi_pending is True

    machine.bus.write8(0x912E, 0xC0)
    machine.bus.write8(0x9124, 0x01)
    machine.bus.write8(0x9125, 0x00)
    machine.run_cycles(2)
    assert machine.bus.irq_pending is True


def test_vic20_keyboard_matrix_is_visible_through_via2_rows_and_columns():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9122, 0xFF)  # port B outputs columns
    machine.bus.write8(0x9123, 0x00)  # port A inputs rows
    machine.handle_input_event(InputEvent(kind="key_matrix", control_a=2, control_b=4, active=True))

    machine.bus.write8(0x9120, 0xEF)  # select column 4 (active low)
    assert machine.bus.read8(0x9121) == 0xFB

    machine.bus.write8(0x9120, 0xF7)  # select a different column
    assert machine.bus.read8(0x9121) == 0xFF

    machine.handle_input_event(InputEvent(kind="key_matrix", control_a=2, control_b=4, active=False))
    machine.bus.write8(0x9120, 0xEF)
    assert machine.bus.read8(0x9121) == 0xFF


def test_vic20_joystick_is_visible_through_via1_and_via2_ports():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9113, 0x00)  # VIA1 port A inputs
    machine.bus.write8(0x9122, 0x00)  # VIA2 port B inputs

    machine.handle_input_event(InputEvent(kind="joystick", control_a=0, control_b=0x01, active=True))
    machine.handle_input_event(InputEvent(kind="joystick", control_a=0, control_b=0x02, active=True))
    machine.handle_input_event(InputEvent(kind="joystick", control_a=0, control_b=0x04, active=True))
    machine.handle_input_event(InputEvent(kind="joystick", control_a=0, control_b=0x10, active=True))
    machine.handle_input_event(InputEvent(kind="joystick", control_a=0, control_b=0x08, active=True))

    assert machine.bus.read8(0x9111) & 0x3C == 0x00  # up/down/left/fire on VIA1 port A
    assert machine.bus.read8(0x9120) & 0x80 == 0x00  # right on VIA2 port B bit 7


def test_vic20_render_frame_uses_screen_ram_and_character_rom():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x08:0x10] = bytes(
        [
            0b10000000,
            0b01000000,
            0b00100000,
            0b00010000,
            0b00001000,
            0b00000100,
            0b00000010,
            0b00000001,
        ]
    )
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9400, 0x05)
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x19)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())
    assert _pixel_at_rgb24(frame, machine.frame_width, 0, 0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (0, 160, 0)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 1, y0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 7, y0 + 7) == (0, 160, 0)


def test_vic20_render_frame_uses_vic_register_bases_for_screen_and_charset():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x808:0x810] = bytes(
        [
            0b11111111,
            0b10000001,
            0b10111101,
            0b10100101,
            0b10100101,
            0b10111101,
            0b10000001,
            0b11111111,
        ]
    )
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9002, 0x96)  # 22 columns + half-page screen bit
    machine.bus.write8(0x9003, 0x2E)  # 23 rows
    machine.bus.write8(0x9005, 0xF2)  # screen at 0x1E00, chars at 0x8800
    machine.bus.write8(0x900F, 0x1B)  # white background, cyan border
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9400, 0x02)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())
    assert _pixel_at_rgb24(frame, machine.frame_width, 0, 0) == (0, 240, 240)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (240, 0, 0)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 3, y0 + 3) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 2, y0 + 2) == (240, 0, 0)


def test_vic20_keeps_latched_fetch_contexts_available_after_run_frame():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x1B)
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9400, 0x02)

    machine.run_frame()

    scanline = next(
        y
        for y in range(machine.frame_height)
        if machine.vic.display_latched_contexts_for_scanline(
            y,
            machine.frame_width,
            machine.frame_height,
        )
    )
    contexts = machine.vic.display_latched_contexts_for_scanline(
        scanline,
        machine.frame_width,
        machine.frame_height,
    )

    assert contexts
    assert any(ctx[7] == 0x02 for ctx in contexts)
    assert all(ctx[8] != 0 for ctx in contexts)


def test_vic20_vic_read_state_write_state_roundtrip():
    machine = _make_vic20_machine()
    machine.run_frame()

    state = machine.vic.read_state()

    other = type(machine.vic)()
    other.write_state(state)

    assert other.read_state() == state


def test_vic20_vic_raster_advances_with_frame_progress():
    machine = _make_vic20_machine()

    assert machine.bus.read8(0x9004) == 0x00

    machine._begin_frame()
    machine.vic.run_cycles(
        machine.TSTATES_PER_FRAME // 2,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    mid_raster = machine.bus.read8(0x9004)
    mid_raster_lsb = (machine.bus.read8(0x9003) >> 7) & 0x01

    assert mid_raster > 0
    assert ((machine.vic.raster_line() >> 1) & 0xFF) == mid_raster
    assert (machine.vic.raster_line() & 0x01) == mid_raster_lsb

    machine.run_frame()
    after_frame_raster = machine.bus.read8(0x9004)

    assert 0 <= after_frame_raster < machine.frame_height


def test_vic20_vic_captures_color_registers_per_raster_line():
    machine = _make_vic20_machine()

    machine._begin_frame()
    scanline_cycles = (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + 1
    machine.vic.run_cycles(
        scanline_cycles,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    machine.bus.write8(0x900E, 0xA0)
    machine.bus.write8(0x900F, 0x58)
    machine.vic.run_cycles(
        machine.TSTATES_PER_FRAME // 2,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )

    assert machine.vic.screen_color_index_for_line(0) == 0x01
    assert machine.vic.auxiliary_color_index_for_line(0) == 0x00
    assert machine.vic.screen_color_index_for_line(machine.frame_height // 2) == 0x05
    assert machine.vic.auxiliary_color_index_for_line(machine.frame_height // 2) == 0x0A


def test_vic20_vic_captures_color_registers_within_a_scanline():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.bus.write8(0x900F, 0x18)
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 18)) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    machine.bus.write8(0x900F, 0x58)

    left_color = machine.vic.screen_color_index_for_line(18)
    split_x = machine.vic.cycle_pixel_x(17) + 1
    left_reg_e, left_reg_f = machine.vic.color_regs_for_position(18, max(machine.vic.display_xstart(), split_x - 1))
    right_reg_e, right_reg_f = machine.vic.color_regs_for_position(18, max(machine.vic.display_xstart(), split_x + 1))

    assert left_color == 0x01
    assert (left_reg_f >> 4) == 0x01
    assert (right_reg_f >> 4) == 0x05


def test_vic20_vic_late_color_change_after_visible_scanline_applies_to_next_line():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.bus.write8(0x900F, 0x18)
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + machine.vic.cycles_per_line() - 1,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    machine.bus.write8(0x900F, 0x58)

    assert machine.vic.screen_color_index_for_line(17) == 0x01
    assert machine.vic.screen_color_index_for_line(18) == 0x01
    assert machine.vic.screen_color_index_for_line(19) == 0x05


def test_vic20_vic_exposes_bg_border_spans_for_line():
    machine = _make_vic20_machine()
    machine._begin_frame()
    machine.bus.write8(0x900F, 0x18)
    machine.vic.run_cycles(
        machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 18),
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    machine.bus.write8(0x900F, 0x58)

    spans18 = machine.vic.bg_border_spans_for_line(18, machine.frame_width)
    spans19 = machine.vic.bg_border_spans_for_line(19, machine.frame_width)

    assert spans18 == [(0, machine.frame_width, 0x01, 0x00)]
    assert spans19 == [(0, machine.frame_width, 0x05, 0x00)]


def test_vic20_kernal_style_offsets_center_the_text_area_inside_the_frame():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)

    assert machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns()) == 24
    assert machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows()) == 48


def test_vic20_vic_exposes_visible_bounds_from_register_geometry():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)

    assert machine.vic.visible_bounds(
        machine.frame_width,
        machine.frame_height,
        machine.vic.screen_columns(),
        machine.vic.screen_rows(),
    ) == (24, 48, 200, 232)


def test_vic20_vic_maps_display_positions_to_cell_coordinates():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)

    assert machine.vic.cell_origin(3, 5, machine.frame_width, machine.frame_height) == (64, 72)
    assert machine.vic.display_cell_at_position(64, 72, machine.frame_width, machine.frame_height) == (3, 5, 0, 0)
    assert machine.vic.display_cell_at_position(71, 79, machine.frame_width, machine.frame_height) == (3, 5, 7, 7)
    assert machine.vic.display_cell_at_position(15, 15, machine.frame_width, machine.frame_height) is None


def test_vic20_vic_exposes_screen_color_and_glyph_addresses_for_cells():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9005, 0xF2)

    assert machine.vic.screen_address_for_cell(3, 5, machine.vic.screen_columns()) == 0x1E47
    assert machine.vic.color_address_for_cell(3, 5, machine.vic.screen_columns()) == 0x9647
    assert machine.vic.glyph_row_address_for_cell(0x01, 3) == 0x880B


def test_vic20_vic_exposes_visible_fetch_context_for_position():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF2)

    fetch = machine.vic.display_fetch_addresses_for_position(
        64,
        72,
        machine.frame_width,
        machine.frame_height,
        0x01,
    )

    assert fetch == (3, 5, 0, 0, 0x1E47, 0x9647, 0x8808)


def test_vic20_vic_exposes_fetch_slot_with_matrix_and_chargen_halves():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * 49) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )

    assert machine.vic.display_fetch_slot_for_position(40, 49, machine.frame_width, machine.frame_height) == (0, 0, 0, 1, 0)
    assert machine.vic.display_fetch_slot_for_position(44, 49, machine.frame_width, machine.frame_height) == (0, 0, 4, 1, 1)
    assert machine.vic.display_fetch_slot_for_position(48, 49, machine.frame_width, machine.frame_height) == (0, 1, 0, 1, 0)


def test_vic20_vic_exposes_fetch_cells_for_text_row():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)

    cells = machine.vic.display_fetch_cells_for_text_row(0, machine.frame_width, machine.frame_height)

    assert cells[0] == (0, 24, 48, 0x1A00, 0x9600)
    assert cells[1] == (1, 32, 48, 0x1A01, 0x9601)
    assert len(cells) == machine.vic.screen_columns()


def test_vic20_vic_exposes_fetch_cells_for_scanline():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * 49) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.frame_height,
    )

    cells = machine.vic.display_fetch_cells_for_scanline(49, machine.frame_width, machine.frame_height)

    assert cells[0] == (0, 0, 24, 1, 0x1A00, 0x9600)
    assert cells[1] == (0, 1, 32, 1, 0x1A01, 0x9601)
    assert len(cells) == machine.vic.screen_columns()


def test_vic20_vic_exposes_fetch_addresses_for_scanline_cell():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF2)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * 49) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.frame_height,
    )

    fetch = machine.vic.display_fetch_addresses_for_scanline_cell(
        49,
        machine.frame_width,
        machine.frame_height,
        1,
        0x01,
    )

    assert fetch == (0, 1, 32, 1, 0x1E01, 0x9601, 0x8809)


def test_vic20_vic_exposes_fetch_contexts_for_scanline():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF2)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * 49) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.frame_height,
    )

    contexts = machine.vic.display_fetch_contexts_for_scanline(
        49,
        machine.frame_width,
        machine.frame_height,
        [0x01, 0x02],
        [0x06, 0x07],
        [0xA5, 0x5A],
    )

    assert contexts[0] == (
            0, 0, 24, 1, 0x1E00, 0x9600, 0x01, 0x06, 0x8809, 0xA5, 0x00, 0x1B, 0, 0, 0x00, 0x1B, 0x00, 0x1B, 0x00, 0x1B
        )
    assert contexts[1] == (
        0, 1, 32, 1, 0x1E01, 0x9601, 0x02, 0x07, 0x8811, 0x5A, 0x00, 0x1B, 0, 0, 0x00, 0x1B, 0x00, 0x1B, 0x00, 0x1B
    )


def test_vic20_vic_exposes_effective_cell_mode():
    machine = _make_vic20_machine()

    assert machine.vic.effective_cell_mode(
        screen_code=0x81,
        color_nibble=0x02,
        reg_f=0x1B,
        char_height=8,
    ) == (True, False)

    assert machine.vic.effective_cell_mode(
        screen_code=0x01,
        color_nibble=0x0A,
        reg_f=0x18,
        char_height=8,
    ) == (False, True)


def test_vic20_vic_exposes_effective_pixel_color_index():
    machine = _make_vic20_machine()

    assert machine.vic.effective_pixel_color_index(
        screen_code=0x01,
        color_nibble=0x05,
        glyph_bits=0x80,
        reg_e=0x00,
        reg_f=0x18,
        pixel_x=0,
        char_height=8,
    ) == 0x05

    assert machine.vic.effective_pixel_color_index(
        screen_code=0x81,
        color_nibble=0x05,
        glyph_bits=0x80,
        reg_e=0x00,
        reg_f=0x18,
        pixel_x=0,
        char_height=8,
    ) == 0x01

    assert machine.vic.effective_pixel_color_index(
        screen_code=0x01,
        color_nibble=0x0A,
        glyph_bits=0x20,
        reg_e=0xB0,
        reg_f=0x1B,
        pixel_x=2,
        char_height=8,
    ) == 0x02


def test_vic20_vic_exposes_display_pixel_color_index_for_position():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)

    assert machine.vic.display_pixel_color_index_for_position(
        x=64,
        y=72,
        frame_width=machine.frame_width,
        frame_height=machine.frame_height,
        screen_code=0x01,
        color_nibble=0x05,
        glyph_bits=0x80,
        reg_e=0x00,
        reg_f=0x18,
        char_height=8,
    ) == 0x05

    assert machine.vic.display_pixel_color_index_for_position(
        x=15,
        y=15,
        frame_width=machine.frame_width,
        frame_height=machine.frame_height,
        screen_code=0x01,
        color_nibble=0x05,
        glyph_bits=0x80,
        reg_e=0x00,
        reg_f=0x18,
        char_height=8,
    ) is None


def test_vic20_vic_tracks_internal_display_window_and_area_state():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()

    assert machine.vic.display_xstart() == -1
    assert machine.vic.area_state() == "idle"

    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + 1,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )

    assert machine.vic.display_xstart() == 24
    assert machine.vic.display_xstop() == 199
    assert machine.vic.fetch_xstart() == 40
    assert machine.vic.fetch_xstop() == 199
    assert machine.vic.display_ystart() == 16
    assert machine.vic.display_ystop() == 231
    assert machine.vic.area_state() == "display"


def test_vic20_vic_applies_raster_color_events_only_inside_display_area():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    machine.bus.write8(0x900F, 0x58)

    border_reg_e, border_reg_f = machine.vic.color_regs_for_position(0, 0)
    split_x = machine.vic.cycle_pixel_x(17) + 1
    display_reg_e, display_reg_f = machine.vic.color_regs_for_position(17, max(32, split_x + 1))

    assert (border_reg_f >> 4) == 0x01
    assert (display_reg_f >> 4) == 0x05


def test_vic20_vic_fetch_window_starts_after_display_window_opens():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()

    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + 4,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    assert machine.vic.area_state() == "display"
    assert machine.vic.display_fetch_addresses_for_position(
        16,
        17,
        machine.frame_width,
        machine.frame_height,
        0x01,
    ) is None


def test_vic20_vic_foreground_changes_affect_the_first_character_in_phases():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 18)) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    machine.bus.write8(0x900F, 0x56)

    event_col = machine.vic._foreground_events[18][0][0]
    old_reg_e, old_reg_f = machine.vic.color_regs_for_position(18, machine.vic.fetch_xstart() + (event_col * 8))
    assert event_col == 2
    px0_e, px0_f = machine.vic.foreground_regs_for_cell_pixel(18, event_col, 0, old_reg_e, old_reg_f)
    px5_e, px5_f = machine.vic.foreground_regs_for_cell_pixel(18, event_col, 5, old_reg_e, old_reg_f)
    px7_e, px7_f = machine.vic.foreground_regs_for_cell_pixel(18, event_col, 7, old_reg_e, old_reg_f)

    assert (px0_f & 0x07) == 0x03
    assert ((px0_f & 0x08) == 0) is False
    assert (px5_f & 0x07) == 0x06
    assert (px7_f & 0x07) == 0x06

    half_flag, phase0_e, phase0_f, phase1_e, phase1_f, phase2_e, phase2_f = (
        machine.vic.foreground_reg_phase_values_for_cell(18, event_col, old_reg_e, old_reg_f)
    )
    if half_flag:
        assert ((px5_f & 0x08) == 0) is False
        assert ((px7_f & 0x08) == 0) is True
    else:
        assert ((px5_f & 0x08) == 0) is True
        assert ((px7_f & 0x08) == 0) is True
    assert machine.vic.foreground_phase_for_pixel(0, half_flag) == 0
    if half_flag:
        assert machine.vic.foreground_phase_for_pixel(5, half_flag) == 1
        assert machine.vic.foreground_phase_for_pixel(7, half_flag) == 2
    else:
        assert machine.vic.foreground_phase_for_pixel(5, half_flag) == 2
        assert machine.vic.foreground_phase_for_pixel(7, half_flag) == 2
    assert (phase0_f & 0x07) == 0x03
    assert ((phase0_f & 0x08) == 0) is False
    assert (phase1_f & 0x07) == 0x06
    assert (phase2_f & 0x07) == 0x06
    if half_flag:
        assert ((phase1_f & 0x08) == 0) is False
        assert ((phase2_f & 0x08) == 0) is True
    else:
        assert ((phase1_f & 0x08) == 0) is False
        assert ((phase2_f & 0x08) == 0) is True


def test_vic20_vic_foreground_changes_propagate_new_state_to_following_characters():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 18)) + 16,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    machine.bus.write8(0x900F, 0x56)

    event_col = machine.vic._foreground_events[18][0][0]
    reg_e, reg_f = machine.vic.color_regs_for_position(18, machine.vic.fetch_xstart() + ((event_col + 1) * 8))
    half_flag, phase0_e, phase0_f, phase1_e, phase1_f, phase2_e, phase2_f = (
        machine.vic.foreground_reg_phase_values_for_cell(18, event_col + 1, reg_e, reg_f)
    )

    assert half_flag == 0
    assert phase0_e == phase1_e == phase2_e
    assert phase0_f == phase1_f == phase2_f
    assert (phase2_f & 0x07) == 0x06
    assert ((phase2_f & 0x08) == 0) is True


def test_vic20_vic_pre_display_foreground_changes_do_not_create_partial_first_char_event():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + 1,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    assert machine.vic.area_state() == "display"

    machine.bus.write8(0x900F, 0x56)

    assert 17 not in machine.vic._foreground_events


def test_vic20_vic_marks_line_as_done_after_display_window():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + machine.vic.cycles_per_line() - 1,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )

    assert machine.vic.area_state() == "display"


def test_vic20_vic_post_fetch_foreground_changes_do_not_create_partial_event():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * (machine.VISIBLE_RASTER_START + 17)) + machine.vic.cycles_per_line() - 1,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.SCANLINES_PER_FRAME,
    )
    assert machine.vic.area_state() == "display"

    machine.bus.write8(0x900F, 0x56)

    assert 17 not in machine.vic._foreground_events


def test_vic20_vic_latches_geometry_for_the_current_frame():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine._begin_frame()
    machine.vic.run_cycles(
        (machine.vic.cycles_per_line() * 51) + 37,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.frame_height,
    )

    before = (
        machine.vic.display_xstart(),
        machine.vic.display_xstop(),
        machine.vic.fetch_xstart(),
        machine.vic.fetch_xstop(),
        machine.vic.display_ystart(),
        machine.vic.display_ystop(),
    )

    machine.bus.write8(0x9003, 0x1B)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9001, 0xAA)
    machine.bus.write8(0x9000, 0x05)
    machine.vic.run_cycles(
        1,
        cycles_per_frame=machine.TSTATES_PER_FRAME,
        raster_lines=machine.frame_height,
    )

    after = (
        machine.vic.display_xstart(),
        machine.vic.display_xstop(),
        machine.vic.fetch_xstart(),
        machine.vic.fetch_xstop(),
        machine.vic.display_ystart(),
        machine.vic.display_ystop(),
    )
    assert after == before


def test_vic20_vic_exposes_aux_color_volume_and_char_height():
    machine = _make_vic20_machine()
    machine.bus.write8(0x900E, 0xA7)
    machine.bus.write8(0x9003, 0x2F)

    assert machine.vic.auxiliary_color_index() == 0x0A
    assert machine.vic.volume() == 0x07
    assert machine.vic.char_height() == 16


def test_vic20_vertical_offset_uses_character_height_in_8x16_mode():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9003, 0x15)  # 10 rows, 8x16 mode

    assert machine.vic.screen_rows() == 10
    assert machine.vic.char_height() == 16
    assert machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows()) == 48


def test_vic20_vic_character_base_uses_vic20_specific_address_table():
    machine = _make_vic20_machine()

    machine.bus.write8(0x9005, 0xF0)
    assert machine.vic.char_base() == 0x8000

    machine.bus.write8(0x9005, 0xF2)
    assert machine.vic.char_base() == 0x8800

    machine.bus.write8(0x9005, 0xFC)
    assert machine.vic.char_base() == 0x1000

    machine.bus.write8(0x9005, 0xFF)
    assert machine.vic.char_base() == 0x1C00


def test_vic20_vic_glyph_rows_wrap_within_the_selected_character_window():
    machine = _make_vic20_machine()

    machine.bus.write8(0x9005, 0xFF)
    machine.bus.write8(0x9003, 0x2E)
    assert machine.vic.char_window_size() == 0x0400
    assert machine.vic.glyph_row_address(0x7F, 7) == 0x1FFF

    machine.bus.write8(0x9003, 0x2F)
    assert machine.vic.char_window_size() == 0x1000
    assert machine.vic.glyph_row_address(0xFF, 15) == 0x2BFF


def test_vic20_render_frame_supports_8x16_character_mode():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x10:0x20] = bytes(
        [
            0b11111111,
            0b10000001,
            0b10111101,
            0b10100101,
            0b10100101,
            0b10111101,
            0b10000001,
            0b11111111,
            0b00000000,
            0b01111110,
            0b01000010,
            0b01011010,
            0b01000010,
            0b01111110,
            0b00000000,
            0b11111111,
        ]
    )
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2F)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x1A)
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9400, 0x05)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (0, 160, 0)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 1, y0 + 1) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0 + 8) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 1, y0 + 9) == (0, 160, 0)


def test_vic20_audio_stays_silent_when_volume_and_channels_are_disabled():
    machine = _make_vic20_machine()

    machine.run_frame()

    assert len(machine.audio_samples) > 0
    assert all(sample == 0 for sample in machine.audio_samples)


def test_vic20_audio_produces_samples_for_enabled_bass_voice():
    machine = _make_vic20_machine()
    machine.bus.write8(0x900A, 0x80)
    machine.bus.write8(0x900E, 0x0F)

    machine.run_frame()

    assert len(machine.audio_samples) > 0
    assert any(sample != 0 for sample in machine.audio_samples)


def test_vic20_render_frame_uses_full_8bit_screen_codes_in_8x16_mode():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x10:0x20] = bytes([0x00] * 16)
    char_rom[0x810:0x820] = bytes(
        [
            0b11111111,
            0b10000001,
            0b10111101,
            0b10100101,
            0b10100101,
            0b10111101,
            0b10000001,
            0b11111111,
            0b00000000,
            0b01111110,
            0b01000010,
            0b01011010,
            0b01000010,
            0b01111110,
            0b00000000,
            0b11111111,
        ]
    )
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2F)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x1A)
    machine.bus.write8(0x1E00, 0x81)
    machine.bus.write8(0x9400, 0x05)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (0, 160, 0)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 1, y0 + 1) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0 + 8) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 1, y0 + 9) == (0, 160, 0)


def test_vic20_render_frame_uses_screen_code_bit_7_as_reverse_for_the_same_glyph():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x08:0x10] = bytes(
        [
            0b11111111,
            0b00000000,
            0b11111111,
            0b00000000,
            0b11111111,
            0b00000000,
            0b11111111,
            0b00000000,
        ]
    )
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x19)
    machine.bus.write8(0x1E00, 0x81)
    machine.bus.write8(0x9400, 0x05)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0 + 1) == (0, 160, 0)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0 + 2) == (255, 255, 255)


def test_vic20_render_frame_uses_selected_9600_color_map_for_default_screen_layout():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x08:0x10] = bytes([0x80, 0, 0, 0, 0, 0, 0, 0])
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x19)
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9600, 0x06)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (0, 0, 240)


def test_vic20_render_frame_derives_color_ram_from_screen_address_per_cell():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x08:0x10] = bytes([0x80, 0, 0, 0, 0, 0, 0, 0])
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x04)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x19)
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x1E16, 0x01)
    machine.bus.write8(0x9600, 0x06)
    machine.bus.write8(0x9616, 0x02)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (0, 0, 240)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0 + 8) == (240, 0, 0)


def test_vic20_renderer_reads_only_memory_visible_to_the_vic():
    machine = _make_vic20_machine()
    machine.bus.write8(0x0010, 0x12)

    assert machine._read_vic_visible(0x0010) == 0x12
    assert machine._read_vic_visible(0x2010) == 0x12
    assert machine._read_vic_visible(0x8000) == 0xEA
    assert machine._read_vic_visible(0x9000) == 0xEA


def test_vic20_render_frame_applies_global_reverse_mode_from_vic_register():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x08:0x10] = bytes(
        [
            0b10000000,
            0b00000000,
            0b00000000,
            0b00000000,
            0b00000000,
            0b00000000,
            0b00000000,
            0b00000000,
        ]
    )
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900F, 0x11)
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9400, 0x05)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 1, y0) == (0, 160, 0)


def test_vic20_render_frame_supports_multicolor_character_cells_from_color_ram():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x08:0x10] = bytes(
        [
            0b00011011,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900E, 0x70)  # auxiliary yellow
    machine.bus.write8(0x900F, 0x19)  # white background, white border, normal mode
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9400, 0x0A)  # multicolor + red character color

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 2, y0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 4, y0) == (240, 0, 0)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 6, y0) == (208, 208, 0)


def test_vic20_multicolor_cells_ignore_global_reverse_mode():
    char_rom = bytearray(_make_vic20_rom(0x1000))
    char_rom[0x08:0x10] = bytes([0b00011011, 0, 0, 0, 0, 0, 0, 0])
    machine = VIC20(
        _make_vic20_rom(0x2000),
        _make_vic20_rom(0x2000, reset_vector=0xE000),
        bytes(char_rom),
    )
    machine.bus.write8(0x9000, 0x0C)
    machine.bus.write8(0x9001, 0x26)
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x2E)
    machine.bus.write8(0x9005, 0xF0)
    machine.bus.write8(0x900E, 0x70)
    machine.bus.write8(0x900F, 0x11)  # reverse enabled globally, white background/border
    machine.bus.write8(0x1E00, 0x01)
    machine.bus.write8(0x9400, 0x0A)

    frame = machine.render_frame()
    x0 = machine.vic.horizontal_offset(machine.frame_width, machine.vic.screen_columns())
    y0 = machine.vic.vertical_offset(machine.frame_height, machine.vic.screen_rows())

    assert _pixel_at_rgb24(frame, machine.frame_width, x0, y0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 2, y0) == (255, 255, 255)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 4, y0) == (240, 0, 0)
    assert _pixel_at_rgb24(frame, machine.frame_width, x0 + 6, y0) == (208, 208, 0)


def test_machine_registry_exposes_vic20ntsc_with_named_rom_slots():
    spec = get_machine_spec("vic20ntsc")

    assert spec.display_name == "Commodore VIC-20 NTSC (experimental)"
    assert [slot.slot_id for slot in spec.rom_slots[:3]] == ["basic", "kernal", "char"]


def test_parse_cli_rom_specs_requires_named_slots_for_vic20ntsc():
    try:
        parse_cli_rom_specs("vic20ntsc", ["vic20.bin"])
    except ValueError as exc:
        assert "varios slots" in str(exc)
    else:
        raise AssertionError("expected ValueError for VIC-20 short ROM form")


def test_instantiate_vic20_machine(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    blk5 = tmp_path / "blk5.bin"
    basic.write_bytes(_make_vic20_rom(0x2000))
    kernal.write_bytes(_make_vic20_rom(0x2000, reset_vector=0xE000))
    char.write_bytes(_make_vic20_rom(0x1000))
    blk5.write_bytes(bytes([0x5A]) * 0x2000)

    machine = instantiate_machine(
        "vic20ntsc",
        roms={
            "basic": basic,
            "kernal": kernal,
            "char": char,
            "blk5": blk5,
        },
    )

    assert machine.machine_id == "vic20ntsc"
    assert machine.display_name == "Commodore VIC-20 NTSC (experimental)"
    assert machine.cpu.PC == 0xE000
    assert machine.bus.read8(0xA000) == 0x5A


def test_instantiate_vic20_alias_keeps_backward_compatible_registry_id(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    basic.write_bytes(_make_vic20_rom(0x2000))
    kernal.write_bytes(_make_vic20_rom(0x2000, reset_vector=0xE000))
    char.write_bytes(_make_vic20_rom(0x1000))

    machine = instantiate_machine(
        "vic20",
        roms={
            "basic": basic,
            "kernal": kernal,
            "char": char,
        },
    )

    assert machine.machine_id == "vic20"
    assert machine.display_name == "Commodore VIC-20 (alias de vic20ntsc)"


def test_vic20_render_frame_clips_cells_that_fall_outside_the_framebuffer():
    machine = _make_vic20_machine()
    machine.bus.write8(0x9002, 0x96)
    machine.bus.write8(0x9003, 0x3F)  # 31 rows, 8x16 chars
    machine.bus.write8(0x9000, 0x1F)
    machine.bus.write8(0x9001, 0x7F)

    frame = machine.render_frame()

    assert len(frame) == machine.frame_width * machine.frame_height * 3
