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


def test_tms9918a_latches_sprite_collision_before_status_read_at_vblank():
    vdp = TMS9918A(_DummyMachine())
    _write_register(vdp, 1, 0x60)
    _write_register(vdp, 5, 0x00)
    _write_register(vdp, 6, 0x00)

    vdp.vram[0x0000:0x0008] = b"\xFF" * 8
    vdp.vram[0x0004] = 32
    vdp.vram[0x0005] = 40
    vdp.vram[0x0006] = 0
    vdp.vram[0x0007] = 0x01
    vdp.vram[0x0008] = 32
    vdp.vram[0x0009] = 40
    vdp.vram[0x000A] = 0
    vdp.vram[0x000B] = 0x02
    vdp.vram[0x000C] = 0xD0

    vdp.begin_frame()
    vdp.run_until(vdp.VBLANK_TSTATE)

    assert (vdp.read_control() & 0x20) != 0


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
