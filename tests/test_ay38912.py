from __future__ import annotations

"""Checks for the reusable AY-3-8912 core."""

from devices import AY38912


def test_ay38912_register_read_write_roundtrip():
    chip = AY38912()

    chip.select_register(7)
    chip.write_selected(0x3F)

    assert chip.read_selected() == 0x3F


def test_ay38912_port_a_uses_callbacks():
    state = {"value": 0xA5, "written": None}

    def read_port_a():
        return state["value"]

    def write_port_a(value: int):
        state["written"] = value

    chip = AY38912(port_a_read=read_port_a, port_a_write=write_port_a)

    chip.select_register(7)
    chip.write_selected(0x40)  # Port A input
    chip.select_register(14)
    assert chip.read_selected() == 0xA5

    chip.select_register(7)
    chip.write_selected(0x00)  # Port A output
    chip.select_register(14)
    chip.write_selected(0x5A)
    assert state["written"] == 0x5A


def test_ay38912_port_b_uses_callbacks():
    state = {"value": 0x3C, "written": None}

    def read_port_b():
        return state["value"]

    def write_port_b(value: int):
        state["written"] = value

    chip = AY38912(port_b_read=read_port_b, port_b_write=write_port_b)

    chip.select_register(7)
    chip.write_selected(0x80)  # Port B input
    chip.select_register(15)
    assert chip.read_selected() == 0x3C

    chip.select_register(7)
    chip.write_selected(0x00)  # Port B output
    chip.select_register(15)
    chip.write_selected(0xA7)
    assert state["written"] == 0xA7


def test_ay38912_masks_register_values():
    chip = AY38912()

    chip.select_register(1)
    chip.write_selected(0xFF)
    assert chip.read_selected() == 0x0F

    chip.select_register(6)
    chip.write_selected(0xFF)
    assert chip.read_selected() == 0x1F


def test_ay38912_port_direction_controls_callback_reads():
    state = {"value": 0x66}

    chip = AY38912(port_a_read=lambda: state["value"])

    chip.select_register(7)
    chip.write_selected(0x40)  # Port A input
    chip.select_register(14)
    assert chip.read_selected() == 0x66

    chip.select_register(7)
    chip.write_selected(0x00)  # Port A output
    chip.select_register(14)
    chip.write_selected(0x12)
    assert chip.read_selected() == 0x12


def test_ay38912_can_expose_external_port_state_while_configured_as_output():
    """Some machine wirings need the external port pins readable at all times."""

    state = {"value": 0xE7}

    chip = AY38912(
        port_a_read=lambda: state["value"],
        port_a_read_through_output=True,
    )

    chip.select_register(7)
    chip.write_selected(0x00)  # Port A output
    chip.select_register(14)

    assert chip.read_selected() == 0xE7


def test_ay38912_renders_non_silent_tone():
    chip = AY38912(clock_hz=1_000_000, sample_rate=8_000)

    chip.select_register(0)
    chip.write_selected(2)
    chip.select_register(1)
    chip.write_selected(0)
    chip.select_register(8)
    chip.write_selected(0x0F)

    samples = chip.render_samples(128)

    assert len(samples) == 128
    assert any(sample != 0 for sample in samples)
    assert max(samples) > 0
    assert min(samples) < 0


def test_ay38912_envelope_drives_channel_volume():
    chip = AY38912(clock_hz=1_000_000, sample_rate=8_000)

    chip.select_register(0)
    chip.write_selected(1)
    chip.select_register(8)
    chip.write_selected(0x10)  # channel A uses envelope
    chip.select_register(11)
    chip.write_selected(1)
    chip.select_register(12)
    chip.write_selected(0)
    chip.select_register(13)
    chip.write_selected(0x0C)  # continue + attack

    samples = chip.render_samples(64)

    assert len(samples) == 64
    assert max(samples) != min(samples)


def test_ay38912_alternating_envelope_changes_direction_across_cycles():
    chip = AY38912(clock_hz=1_000_000, sample_rate=8_000)

    chip.select_register(8)
    chip.write_selected(0x10)
    chip.select_register(11)
    chip.write_selected(1)
    chip.select_register(12)
    chip.write_selected(0)
    chip.select_register(13)
    chip.write_selected(0x0E)  # continue + attack + alternate

    levels = []
    for _ in range(40):
        chip._step_psg_cycle()
        levels.append(chip._get_envelope_level())

    assert max(levels[:16]) > min(levels[:16])
    assert levels[14] == 15
    assert levels[15] == 15
    assert levels[16] == 14
    assert levels[30] == 0
    assert levels[31] == 0
    assert levels[32] == 1
