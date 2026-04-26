from __future__ import annotations

from frontend.input_events import (
    InputEvent,
    JOYSTICK_DOWN,
    JOYSTICK_LEFT,
    JOYSTICK_RIGHT,
    JOYSTICK_START,
    JOYSTICK_UP,
)
from machines.z80 import ColecoVision


def _make_bios() -> bytes:
    return bytes([0x00]) * 0x2000


def _make_cart() -> bytes:
    return bytes([0xC9]) * 0x8000


def test_colecovision_initializes_machine_scaffold():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    assert machine.machine_id == "colecovision"
    assert machine.input_keymap_name == "colecovision"
    assert machine.frame_width == 256
    assert machine.frame_height == 192
    assert len(machine.framebuffer_rgb24) == 256 * 192 * 3
    assert machine.bus.wait_io_tstates == machine.IO_WAIT_TSTATES
    assert machine.bus.wait_low_mem_tstates == machine.LOW_MEM_WAIT_TSTATES


def test_colecovision_maps_bios_cart_and_mirrored_ram():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    machine.poke(0x6000, 0x5A)

    assert machine.peek(0x0000) == 0x00
    assert machine.peek(0x8000) == 0xC9
    assert machine.peek(0x6000) == 0x5A
    assert machine.peek(0x6400) == 0x5A


def test_colecovision_psg_port_write_produces_audio():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    machine._port_write(0xE0, 0x81)
    machine._port_write(0xE0, 0x00)
    machine._port_write(0xE0, 0x90)
    machine._finish_frame()

    assert any(sample != 0 for sample in machine.audio_samples)


def test_colecovision_psg_write_adds_ready_wait_states():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())
    baseline = machine.cpu.step()

    machine._port_write(0xE0, 0x90)

    assert machine._pending_wait_tstates == machine.PSG_WRITE_WAIT_TSTATES
    assert machine._cpu_step_with_wait() == baseline + machine.PSG_WRITE_WAIT_TSTATES
    assert machine._pending_wait_tstates == 0


def test_colecovision_c0_write_does_not_feed_psg():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    machine._port_write(0xC0, 0x81)
    machine._finish_frame()

    assert all(sample == 0 for sample in machine.audio_samples)


def test_colecovision_start_button_is_exposed_on_controller_port():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_START, True))

    assert machine.snapshot()["frame_counter"] == 0


def test_colecovision_state_roundtrip_preserves_ram_and_controller():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())
    machine.poke(0x6001, 0xA5)
    machine.handle_input_event(InputEvent("key_matrix", 0, 6, True))

    state = machine.read_state()
    other = ColecoVision(_make_cart(), bios_data=_make_bios())
    other.write_state(state)

    assert other.peek(0x6001) == 0xA5
    assert other.snapshot()["controller_mode"] == "joystick"


def test_colecovision_maps_vdp_ports():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    machine._port_write(0xA1, 0x34)
    machine._port_write(0xA1, 0x40)
    machine._port_write(0xA0, 0x5A)
    machine._port_write(0xA1, 0x34)
    machine._port_write(0xA1, 0x00)

    assert machine._port_read(0xA0) == 0x5A


def test_colecovision_state_roundtrip_preserves_vdp():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())
    machine.vdp.vram[0x20] = 0x7F
    machine.vdp.registers[1] = 0x40

    state = machine.read_state()
    other = ColecoVision(_make_cart(), bios_data=_make_bios())
    other.write_state(state)

    assert other.vdp.vram[0x20] == 0x7F
    assert other.vdp.registers[1] == 0x40


def test_colecovision_controller_mode_and_keypad_are_exposed_on_e0_ports():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    machine._port_write(0x80, 0x00)
    machine.handle_input_event(InputEvent("key_matrix", 1, 3, True))
    keypad_value = machine._port_read(0xE0)
    machine._port_write(0xC0, 0x00)
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_UP, True))
    joystick_value = machine._port_read(0xE0)

    assert machine._controller_mode == "joystick"
    assert keypad_value != 0xFF
    assert (joystick_value & 0x01) == 0


def test_colecovision_joystick_direction_bits_match_bios_order():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())

    machine._port_write(0xC0, 0x00)

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_UP, True))
    assert (machine._port_read(0xFC) & 0x01) == 0
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_UP, False))

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_RIGHT, True))
    assert (machine._port_read(0xFC) & 0x02) == 0
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_RIGHT, False))

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_DOWN, True))
    assert (machine._port_read(0xFC) & 0x04) == 0
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_DOWN, False))

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_LEFT, True))
    assert (machine._port_read(0xFC) & 0x08) == 0


def test_colecovision_keypad_encoding_matches_bios_lookup_expectations():
    machine = ColecoVision(_make_cart(), bios_data=_make_bios())
    expected_complemented_nibbles = {
        0: 0x05,
        1: 0x02,
        2: 0x08,
        3: 0x03,
        4: 0x0D,
        5: 0x0C,
        6: 0x01,
        7: 0x0A,
        8: 0x0E,
        9: 0x04,
        10: 0x06,
        11: 0x09,
    }

    machine._port_write(0x80, 0x00)
    for key, expected in expected_complemented_nibbles.items():
        machine.handle_input_event(InputEvent("key_matrix", 1, key, True))
        port_value = machine._port_read(0xFC)
        assert ((~port_value) & 0x0F) == expected
        machine.handle_input_event(InputEvent("key_matrix", 1, key, False))
