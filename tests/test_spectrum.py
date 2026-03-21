from __future__ import annotations

import pytest

from frontend.input_events import InputEvent
from machines.z80 import Spectrum16K, Spectrum48K
from devices import SpectrumCassetteTape


def _pixel_at_rgb24(packed: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    pixel_offset = ((y * width) + x) * 3
    return tuple(packed[pixel_offset:pixel_offset + 3])


def _build_smoke_rom() -> bytes:
    rom = bytes([
        0x3E, 0x02,             # LD A,02h
        0xD3, 0xFE,             # OUT (FEh),A
        0x3E, 0x09,             # LD A,09h
        0x32, 0x00, 0x40,       # LD (4000h),A
        0x3A, 0x00, 0x40,       # LD A,(4000h)
        0x76,                   # HALT
    ])
    return rom + bytes(0x4000 - len(rom))


def _build_ram_exec_rom() -> bytes:
    rom = bytes([
        0xC3, 0x00, 0x40,       # JP 4000h
    ])
    return rom + bytes(0x4000 - len(rom))


def _build_beeper_rom() -> bytes:
    code = bytes([
        0xF3,                   # DI
        0x3E, 0x10,             # loop: LD A,10h
        0xD3, 0xFE,             #       OUT (FEh),A
        0x06, 0x40,             #       LD B,40h
        0x10, 0xFE,             # d1:   DJNZ d1
        0xAF,                   #       XOR A
        0xD3, 0xFE,             #       OUT (FEh),A
        0x06, 0x40,             #       LD B,40h
        0x10, 0xFE,             # d2:   DJNZ d2
        0xC3, 0x01, 0x00,       #       JP loop
    ])
    return code + bytes(0x4000 - len(code))


def test_spectrum16k_exposes_only_installed_ram():
    machine = Spectrum16K(bytes([0x00]) * 0x4000)
    machine.reset()

    machine.poke(0x4000, 0x12)

    assert machine.peek(0x4000) == 0x12
    assert machine.peek(0x8000) == 0xFF

    with pytest.raises(ValueError):
        machine.poke(0x8000, 0x34)


def test_spectrum_exposes_frame_dimensions_for_frontends():
    machine = Spectrum48K(bytes([0x00]) * 0x4000)

    assert machine.frame_width == machine.ula.frame_width
    assert machine.frame_height == machine.ula.frame_height


def test_spectrum48k_smoke_program_updates_border_ram_and_register_a():
    machine = Spectrum48K(_build_smoke_rom())
    machine.reset()

    machine.run_cycles(200)
    snap = machine.snapshot()

    assert machine.border_color == 0x02
    assert machine.peek(0x4000) == 0x09
    assert snap["A"] == 0x09
    assert snap["halted"] is True


def test_spectrum48k_can_jump_from_rom_to_ram_program():
    machine = Spectrum48K(_build_ram_exec_rom())
    ram_prog = bytes([
        0x3E, 0x05,             # LD A,05h
        0xD3, 0xFE,             # OUT (FEh),A
        0x3E, 0x42,             # LD A,42h
        0x76,                   # HALT
    ])
    machine.load_ram(0x4000, ram_prog)

    machine.reset()
    machine.run_cycles(200)
    snap = machine.snapshot()

    assert machine.border_color == 0x05
    assert snap["A"] == 0x42
    assert snap["halted"] is True


def test_spectrum_keyboard_matrix_read_reflects_input_events():
    machine = Spectrum48K(bytes([0x00]) * 0x4000)
    machine.reset()

    event = InputEvent(kind="key_matrix", control_a=0, control_b=0, active=True)
    machine.handle_input_event(event)

    assert machine._port_read_fe(0xFEFE) & 0x01 == 0

    machine.handle_input_event(InputEvent(kind="key_matrix", control_a=0, control_b=0, active=False))

    assert machine._port_read_fe(0xFEFE) & 0x01 == 0x01


def test_spectrum_render_frame_uses_screen_bitmap_and_attributes():
    machine = Spectrum48K(bytes([0x00]) * 0x4000)
    machine.reset()
    machine.border_color = 1
    machine.poke(0x4000, 0b1000_0000)
    machine.poke(0x5800, 0b0100_0011)  # bright ink 3, paper 0

    packed = machine.render_frame()
    x = machine.ula.border_left
    y = machine.ula.border_top

    assert isinstance(packed, bytes)
    assert _pixel_at_rgb24(packed, machine.ula.frame_width, 0, 0) == machine.ula.PALETTE[1]
    assert _pixel_at_rgb24(packed, machine.ula.frame_width, x, y) == machine.ula.PALETTE[11]
    assert _pixel_at_rgb24(packed, machine.ula.frame_width, x + 1, y) == machine.ula.PALETTE[0]


def test_spectrum_run_frame_produces_audio_and_advances_frame_counter():
    machine = Spectrum48K(_build_beeper_rom())
    machine.reset()

    machine.run_frame()

    assert machine.frame_counter == 1
    assert len(machine.get_audio_samples()) > 0
    assert any(sample != 0 for sample in machine.get_audio_samples())
    assert machine.get_audio_buffered_samples() > 0


def test_tzx_parser_accepts_standard_speed_blocks_for_spectrum():
    payload = b"\x00\x01\x02"
    data = (
        b"ZXTape!\x1A\x01\x14"
        + bytes([0x10])
        + (1000).to_bytes(2, "little")
        + len(payload).to_bytes(2, "little")
        + payload
    )

    tape = SpectrumCassetteTape.from_tzx_bytes(data)

    assert tape.pulses
    assert any(pulse.level == 0 for pulse in tape.pulses)
    assert any(pulse.level == 1 for pulse in tape.pulses)


def test_spectrum48k_port_fe_exposes_tape_ear_input():
    payload = b"\x00"
    data = (
        b"ZXTape!\x1A\x01\x14"
        + bytes([0x10])
        + (1000).to_bytes(2, "little")
        + len(payload).to_bytes(2, "little")
        + payload
    )
    machine = Spectrum48K(bytes([0x00]) * 0x4000, tape_data=data)
    machine.toggle_tape_play_pause()

    seen = set()
    for _ in range(200):
        seen.add(1 if (machine._port_read_fe(0xFEFE) & 0x40) else 0)
        machine._run_devices_until(machine.frame_tstates + 3000)
        machine.frame_tstates += 3000
        if seen == {0, 1}:
            break

    assert seen == {0, 1}


def test_spectrum48k_tape_starts_paused_and_can_be_toggled():
    data = (
        b"ZXTape!\x1A\x01\x14"
        + bytes([0x10])
        + (1000).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + b"\x00"
    )
    machine = Spectrum48K(bytes([0x00]) * 0x4000, tape_data=data)

    assert machine.cassette is not None
    assert machine.cassette.playing is False
    assert machine.toggle_tape_play_pause() is True
    assert machine.cassette.playing is True
