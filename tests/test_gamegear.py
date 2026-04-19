from __future__ import annotations

from frontend.input_events import InputEvent, JOYSTICK_START
from machines.z80 import GameGear, MasterSystem2


def _make_test_rom() -> bytes:
    rom = bytearray(0x10000)
    for bank in range(4):
        base = bank * 0x4000
        rom[base:base + 0x4000] = bytes([bank]) * 0x4000
    return bytes(rom)


def test_gamegear_initializes_as_160x144_machine():
    machine = GameGear(_make_test_rom())

    assert machine.machine_id == "gamegear"
    assert machine.display_name == "Sega Game Gear"
    assert machine.audio_channels == 2
    assert machine.frame_width == 160
    assert machine.frame_height == 144
    assert len(machine.framebuffer_rgb24) == 160 * 144 * 3


def test_gamegear_visible_framebuffer_is_cropped_from_sms_vdp_frame():
    machine = GameGear(_make_test_rom())
    full = bytearray(machine.VDP_FRAME_WIDTH * machine.VDP_FRAME_HEIGHT * 3)
    src = ((machine.VISIBLE_Y * machine.VDP_FRAME_WIDTH) + machine.VISIBLE_X) * 3
    full[src:src + 3] = b"\x11\x22\x33"

    visible = machine._visible_framebuffer(bytes(full))

    assert visible[:3] == b"\x11\x22\x33"
    assert len(visible) == 160 * 144 * 3


def test_gamegear_vdp_uses_12_bit_cram_colours():
    machine = GameGear(_make_test_rom())

    assert len(machine.vdp.cram) == 0x40

    machine.vdp.code = 0x03
    machine.vdp.address = 0x02
    machine.vdp.write_data(0x2F)
    machine.vdp.write_data(0x0A)

    assert machine.vdp._cram_color(1) == (255, 34, 170)


def test_gamegear_start_button_is_exposed_on_port_00():
    machine = GameGear(_make_test_rom())

    assert machine._port_read(0x00) & 0x80 == 0x80

    machine.handle_input_event(InputEvent("key_matrix", 1, 2, True))

    assert machine._port_read(0x00) & 0x80 == 0


def test_gamegear_joystick_start_updates_start_button():
    machine = GameGear(_make_test_rom())

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_START, True))

    assert machine._port_read(0x00) & 0x80 == 0


def test_gamegear_state_roundtrip_preserves_start_button():
    machine = GameGear(_make_test_rom())
    machine.handle_input_event(InputEvent("key_matrix", 1, 2, True))

    state = machine.read_state()
    other = GameGear(_make_test_rom())
    other.write_state(state)

    assert other._port_read(0x00) & 0x80 == 0


def test_gamegear_exposes_serial_io_registers():
    machine = GameGear(_make_test_rom())

    for port in range(0x01, 0x06):
        machine._port_write(port, 0x80 | port)

    assert [machine._port_read(port) for port in range(0x01, 0x06)] == [
        0x81,
        0x82,
        0x83,
        0x84,
        0x85,
    ]


def test_gamegear_port_06_controls_psg_stereo_register():
    machine = GameGear(_make_test_rom())

    assert machine._port_read(0x06) == 0xFF

    machine._port_write(0x06, 0x51)

    assert machine._port_read(0x06) == 0x51
    assert machine.psg.read_stereo_control() == 0x51


def test_gamegear_audio_samples_are_interleaved_stereo():
    machine = GameGear(_make_test_rom(), audio_sample_rate=44_100)

    machine._port_write(0x06, 0x10)
    machine._port_write(0x7F, 0x80 | 0x01)
    machine._port_write(0x7F, 0x00)
    machine._port_write(0x7F, 0x90 | 0x00)
    machine._finish_frame()

    frame_count = machine._current_frame_sample_target
    assert len(machine.audio_samples) == frame_count * 2
    assert any(machine.audio_samples[index] != 0 for index in range(0, len(machine.audio_samples), 2))
    assert all(machine.audio_samples[index] == 0 for index in range(1, len(machine.audio_samples), 2))


def test_gamegear_state_roundtrip_preserves_io_and_stereo_registers():
    machine = GameGear(_make_test_rom())
    machine._port_write(0x02, 0x34)
    machine._port_write(0x06, 0x87)

    state = machine.read_state()
    other = GameGear(_make_test_rom())
    other.write_state(state)

    assert other._port_read(0x02) == 0x34
    assert other._port_read(0x06) == 0x87


def test_master_system_ignores_game_gear_stereo_port():
    machine = MasterSystem2(_make_test_rom())

    machine._port_write(0x06, 0x00)

    assert machine.psg.read_stereo_control() == 0xFF
