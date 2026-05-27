from __future__ import annotations

from chipsets import TMS9918A
from tests.fallbacks.tms9918a_reference import TMS9918AReference


class _DummyCPU:
    def __init__(self):
        self.interrupt_count = 0
        self.nmi_count = 0

    def interrupt(self):
        self.interrupt_count += 1

    def nmi(self):
        self.nmi_count += 1


class _DummyMachine:
    TSTATES_PER_FRAME = 59_736

    def __init__(self, *, vdp_vblank_uses_nmi: bool = False):
        self.cpu = _DummyCPU()
        self.vdp_vblank_uses_nmi = vdp_vblank_uses_nmi


def _write_register(vdp: TMS9918A, register: int, value: int) -> None:
    vdp.write_control(value)
    vdp.write_control(0x80 | (register & 0x07))


def _set_vram_write_address(vdp: TMS9918A, address: int) -> None:
    vdp.write_control(address & 0xFF)
    vdp.write_control(0x40 | ((address >> 8) & 0x3F))


def _pixel(frame: bytes, x: int, y: int) -> bytes:
    offset = (y * TMS9918A.FRAME_WIDTH + x) * 3
    return frame[offset:offset + 3]


def test_tms9918a_vram_roundtrip_through_ports():
    vdp = TMS9918A(_DummyMachine())

    _set_vram_write_address(vdp, 0x0123)
    vdp.write_data(0x5A)

    vdp.write_control(0x23)
    vdp.write_control(0x01)
    assert vdp.read_data() == 0x5A


def test_tms9918a_graphics1_renders_pattern_and_colors():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x40)
    _write_register(vdp, 3, 0x01)
    _write_register(vdp, 7, 0x14)
    vdp.vram[0x0000] = 0x01
    for row in range(8):
        vdp.vram[0x0008 + row] = 0x80
    vdp.vram[0x0040] = 0xF4

    frame = vdp.render_frame()
    fg = bytes(vdp.PALETTE[0x0F])
    bg = bytes(vdp.PALETTE[0x04])
    assert frame[0:3] == fg
    assert frame[3:6] == bg


def test_tms9918a_graphics1_allows_high_color_table_base():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x40)
    _write_register(vdp, 3, 0x80)
    vdp.vram[0x0000] = 0x01
    for row in range(8):
        vdp.vram[0x0008 + row] = 0x80
    vdp.vram[0x2000] = 0xF4

    frame = vdp.render_frame()
    fg = bytes(vdp.PALETTE[0x0F])
    bg = bytes(vdp.PALETTE[0x04])
    assert frame[0:3] == fg
    assert frame[3:6] == bg


def test_tms9918a_graphics2_uses_per_line_color_table():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x40)
    _write_register(vdp, 0, 0x02)
    _write_register(vdp, 3, 0x80)
    _write_register(vdp, 7, 0x12)
    vdp.vram[0x0000] = 0x01
    for row in range(8):
        vdp.vram[0x0008 + row] = 0x80
        vdp.vram[0x2008 + row] = 0xE2

    frame = vdp.render_frame()
    fg = bytes(vdp.PALETTE[0x0E])
    bg = bytes(vdp.PALETTE[0x02])
    assert frame[0:3] == fg
    assert frame[3:6] == bg


def test_tms9918a_graphics2_register3_masks_pattern_and_color_low_bits():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x40)
    _write_register(vdp, 0, 0x02)
    _write_register(vdp, 2, 0x02)
    _write_register(vdp, 3, 0x80)
    _write_register(vdp, 4, 0x00)
    _write_register(vdp, 7, 0x14)

    vdp.vram[0x0000] = 0x08
    vdp.vram[0x2000] = 0xE4
    vdp.vram[0x0800] = 8

    frame = vdp.render_frame()
    fg = bytes(vdp.PALETTE[0x0E])
    bg = bytes(vdp.PALETTE[0x04])
    assert _pixel(frame, 4, 0) == fg
    assert _pixel(frame, 0, 0) == bg


def test_tms9918a_graphics2_register3_low_bits_enable_pattern_color_groups():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x40)
    _write_register(vdp, 0, 0x02)
    _write_register(vdp, 2, 0x02)
    _write_register(vdp, 3, 0x81)
    _write_register(vdp, 4, 0x00)
    _write_register(vdp, 7, 0x14)

    vdp.vram[0x0800] = 8
    vdp.vram[0x0040] = 0x80
    vdp.vram[0x2040] = 0xE4

    frame = vdp.render_frame()
    fg = bytes(vdp.PALETTE[0x0E])
    bg = bytes(vdp.PALETTE[0x04])
    assert _pixel(frame, 0, 0) == fg
    assert _pixel(frame, 1, 0) == bg


def test_tms9918a_raises_vblank_interrupt_when_enabled():
    machine = _DummyMachine()
    vdp = TMS9918A(machine)
    _write_register(vdp, 1, 0x60)

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)

    assert machine.cpu.interrupt_count == 1
    assert (vdp.read_control() & 0x80) != 0


def test_tms9918a_can_raise_vblank_nmi_for_colecovision_style_machine():
    machine = _DummyMachine(vdp_vblank_uses_nmi=True)
    vdp = TMS9918A(machine)
    _write_register(vdp, 1, 0x60)

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)

    assert machine.cpu.nmi_count == 1
    assert machine.cpu.interrupt_count == 0


def test_tms9918a_mode_decode_matches_legacy_tms_modes():
    vdp = TMS9918A(_DummyMachine())

    assert vdp._mode() == "graphics1"
    vdp.registers[1] = 0x10
    assert vdp._mode() == "text"
    vdp.registers[1] = 0x00
    vdp.registers[0] = 0x02
    assert vdp._mode() == "graphics2"
    vdp.registers[0] = 0x00
    vdp.registers[1] = 0x08
    assert vdp._mode() == "multicolor"


def test_tms9918a_table_base_register_masks_match_tms9918a_layout():
    vdp = TMS9918A(_DummyMachine())

    vdp.registers[3] = 0xFF
    vdp.registers[4] = 0xFF
    vdp.registers[5] = 0xFF
    vdp.registers[6] = 0xFF

    assert vdp._color_table_base() == 0x3FC0
    assert vdp._pattern_table_base() == 0x3800
    assert vdp._sprite_attribute_base() == 0x3F80
    assert vdp._sprite_pattern_base() == 0x3800


def test_tms9918a_graphics2_table_masks_ignore_low_bits():
    vdp = TMS9918A(_DummyMachine())
    vdp.registers[0] = 0x02
    vdp.registers[3] = 0x7F
    vdp.registers[4] = 0x03

    assert vdp._color_table_base() == 0x0000
    assert vdp._pattern_table_base() == 0x0000

    vdp.registers[3] = 0x80
    vdp.registers[4] = 0x04

    assert vdp._color_table_base() == 0x2000
    assert vdp._pattern_table_base() == 0x2000


def test_tms9918a_status_read_clears_vblank_and_sprite_flags():
    vdp = TMS9918A(_DummyMachine())
    vdp.status = 0xE7

    assert vdp.read_control() == 0xE7
    assert vdp.status == 0x00


def test_tms9918a_does_not_retrigger_interrupt_without_status_read():
    machine = _DummyMachine(vdp_vblank_uses_nmi=True)
    vdp = TMS9918A(machine)
    _write_register(vdp, 1, 0x60)

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)
    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)

    assert machine.cpu.nmi_count == 1
    assert (vdp.status & 0x80) != 0


def test_tms9918a_status_read_does_not_retrigger_vblank_in_same_frame():
    machine = _DummyMachine(vdp_vblank_uses_nmi=True)
    vdp = TMS9918A(machine)
    _write_register(vdp, 1, 0x60)

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)
    assert machine.cpu.nmi_count == 1

    assert (vdp.read_control() & 0x80) != 0
    vdp.run_until(vdp.VBLANK_TSTATE + 128)

    assert machine.cpu.nmi_count == 1
    assert vdp.interrupt_line_asserted is False


def test_tms9918a_enabling_interrupt_after_vblank_asserts_pending_line():
    machine = _DummyMachine()
    vdp = TMS9918A(machine)
    _write_register(vdp, 1, 0x40)

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)
    assert machine.cpu.interrupt_count == 0
    assert (vdp.status & 0x80) != 0

    _write_register(vdp, 1, 0x60)

    assert machine.cpu.interrupt_count == 1
    assert vdp.interrupt_line_asserted is True


def test_tms9918a_disabling_interrupt_lowers_pending_line_until_reenabled():
    machine = _DummyMachine()
    vdp = TMS9918A(machine)
    _write_register(vdp, 1, 0x60)

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)
    assert machine.cpu.interrupt_count == 1
    assert vdp.interrupt_line_asserted is True

    _write_register(vdp, 1, 0x40)

    assert vdp.interrupt_line_asserted is False
    assert machine.cpu.interrupt_count == 1

    _write_register(vdp, 1, 0x60)

    assert vdp.interrupt_line_asserted is True
    assert machine.cpu.interrupt_count == 2


def test_tms9918a_status_read_before_enabling_interrupt_clears_pending_line():
    machine = _DummyMachine()
    vdp = TMS9918A(machine)
    _write_register(vdp, 1, 0x40)

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)
    assert (vdp.read_control() & 0x80) != 0

    _write_register(vdp, 1, 0x60)

    assert machine.cpu.interrupt_count == 0
    assert vdp.interrupt_line_asserted is False


def test_tms9918a_latches_sprite_collision_before_status_read_at_vblank():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x60)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)

    vdp.vram[0x0000:0x0008] = b"\xFF" * 8
    vdp.vram[0x0100] = 31
    vdp.vram[0x0101] = 40
    vdp.vram[0x0102] = 0
    vdp.vram[0x0103] = 0x01
    vdp.vram[0x0104] = 31
    vdp.vram[0x0105] = 40
    vdp.vram[0x0106] = 0
    vdp.vram[0x0107] = 0x02
    vdp.vram[0x0108] = 0xD0

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)

    assert (vdp.read_control() & 0x20) != 0


def test_tms9918a_sprite_priority_uses_lowest_sprite_index():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x40)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)
    _write_register(vdp, 7, 0x14)

    vdp.vram[0x0000:0x0008] = b"\x80" * 8
    vdp.vram[0x0100:0x0108] = bytes([31, 40, 0, 0x02, 31, 40, 0, 0x0F])
    vdp.vram[0x0108] = 0xD0

    frame = vdp.render_frame()

    assert _pixel(frame, 40, 32) == bytes(vdp.PALETTE[0x02])
    assert (vdp.status & 0x20) != 0


def test_tms9918a_fifth_sprite_sets_status_index():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x60)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)

    for index in range(5):
        base = 0x0100 + index * 4
        vdp.vram[base:base + 4] = bytes([31, index * 8, 0, 0x01])
    vdp.vram[0x0100 + 5 * 4] = 0xD0

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)

    status = vdp.read_control()
    assert (status & 0x40) != 0
    assert (status & 0x1F) == 4


def test_tms9918a_fifth_sprite_waits_for_status_read_after_vblank():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x60)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)

    for index in range(5):
        base = 0x0100 + index * 4
        vdp.vram[base:base + 4] = bytes([31, index * 8, 0, 0x01])
    vdp.vram[0x0100 + 5 * 4] = 0xD0
    vdp.status = 0x80

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)

    assert (vdp.read_control() & 0x40) == 0


def test_tms9918a_sprite_y_attribute_is_screen_y_minus_one():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x60)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)
    _write_register(vdp, 7, 0x14)

    vdp.vram[0x0000:0x0008] = b"\x80" * 8
    vdp.vram[0x0100] = 31
    vdp.vram[0x0101] = 40
    vdp.vram[0x0102] = 0
    vdp.vram[0x0103] = 0x0F
    vdp.vram[0x0104] = 0xD0

    frame = vdp.render_frame()

    assert _pixel(frame, 40, 31) != bytes(vdp.PALETTE[0x0F])
    assert _pixel(frame, 40, 32) == bytes(vdp.PALETTE[0x0F])


def test_tms9918a_sprite_y_ff_wraps_to_top_line():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x60)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)
    _write_register(vdp, 7, 0x14)

    vdp.vram[0x0000:0x0008] = b"\x80" * 8
    vdp.vram[0x0100] = 0xFF
    vdp.vram[0x0101] = 40
    vdp.vram[0x0102] = 0
    vdp.vram[0x0103] = 0x0F
    vdp.vram[0x0104] = 0xD0

    frame = vdp.render_frame()

    assert _pixel(frame, 40, 0) == bytes(vdp.PALETTE[0x0F])


def test_tms9918a_large_sprite_uses_tms_quadrant_pattern_order():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x42)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)
    _write_register(vdp, 7, 0x14)

    vdp.vram[(6 * 8)] = 0x80
    vdp.vram[0x0100] = 31
    vdp.vram[0x0101] = 40
    vdp.vram[0x0102] = 5
    vdp.vram[0x0103] = 0x0F
    vdp.vram[0x0104] = 0xD0

    frame = vdp.render_frame()

    assert _pixel(frame, 48, 32) == bytes(vdp.PALETTE[0x0F])
    assert _pixel(frame, 40, 40) != bytes(vdp.PALETTE[0x0F])


def test_tms9918a_magnified_sprite_doubles_pixels():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x41)
    _write_register(vdp, 5, 0x02)
    _write_register(vdp, 6, 0x00)
    _write_register(vdp, 7, 0x14)

    vdp.vram[0x0000] = 0x80
    vdp.vram[0x0100] = 31
    vdp.vram[0x0101] = 40
    vdp.vram[0x0102] = 0
    vdp.vram[0x0103] = 0x0F
    vdp.vram[0x0104] = 0xD0

    frame = vdp.render_frame()
    color = bytes(vdp.PALETTE[0x0F])

    assert _pixel(frame, 40, 32) == color
    assert _pixel(frame, 41, 32) == color
    assert _pixel(frame, 40, 33) == color
    assert _pixel(frame, 42, 32) != color


def test_tms9918a_matches_python_reference_for_basic_graphics_and_state():
    machine = _DummyMachine()
    cython_vdp = TMS9918A(machine)
    python_vdp = TMS9918AReference(machine)

    for vdp in (cython_vdp, python_vdp):
        _write_register(vdp, 1, 0x60)
        _write_register(vdp, 3, 0x01)
        _write_register(vdp, 7, 0x14)
        vdp.vram[0x0000] = 0x01
        for row in range(8):
            vdp.vram[0x0008 + row] = 0x80
        vdp.vram[0x0040] = 0xF4
        vdp.begin_frame()
        vdp.run_until(vdp.VBLANK_TSTATE)

    assert cython_vdp.render_frame() == python_vdp.render_frame()
    assert cython_vdp.read_state() == python_vdp.read_state()
