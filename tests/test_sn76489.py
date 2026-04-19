from __future__ import annotations

from statistics import mean

from chipsets import SN76489, SN76489Reference


def test_sn76489_renders_non_silent_tone():
    chip = SN76489(clock_hz=3_579_545, sample_rate=8_000)

    chip.write(0x80 | 0x00 | 0x10)
    chip.write(0x00)
    chip.write(0x90 | 0x00)

    samples = chip.render_samples(128)

    assert len(samples) == 128
    assert any(sample != 0 for sample in samples)
    assert max(samples) > 0
    assert min(samples) < 0


def test_sn76489_volume_levels_are_monotonic():
    chip = SN76489()

    loudness = []
    for level in range(0x0F):
        chip.reset()
        chip.write(0x80 | 0x00 | 0x01)
        chip.write(0x00)
        chip.write(0x90 | level)
        samples = chip.render_samples(128)
        loudness.append(max(abs(sample) for sample in samples))

    assert all(a >= b for a, b in zip(loudness, loudness[1:]))


def test_sn76489_periodic_and_white_noise_differ():
    periodic = SN76489(clock_hz=3_579_545, sample_rate=8_000)
    white = SN76489(clock_hz=3_579_545, sample_rate=8_000)

    periodic.write(0xE0 | 0x00)
    periodic.write(0xF0 | 0x00)

    white.write(0xE0 | 0x04)
    white.write(0xF0 | 0x00)

    periodic_samples = periodic.render_samples(256)
    white_samples = white.render_samples(256)

    assert periodic_samples != white_samples


def test_sn76489_silent_volume_produces_silence():
    chip = SN76489(clock_hz=3_579_545, sample_rate=8_000)

    chip.write(0x80 | 0x00 | 0x01)
    chip.write(0x00)
    chip.write(0x90 | 0x0F)

    samples = chip.render_samples(128)

    assert all(sample == 0 for sample in samples)


def test_sn76489_period_one_can_be_used_as_volume_dac():
    chip = SN76489(clock_hz=3_579_545, sample_rate=44_100)

    chip.write(0x80 | 0x01)
    chip.write(0x00)
    chip.write(0x90 | 0x04)

    samples = chip.render_samples(64)

    assert len(set(samples)) == 1
    assert samples[0] > 0


def test_sn76489_stereo_control_downmixes_game_gear_channels():
    both = SN76489(clock_hz=3_579_545, sample_rate=44_100)
    right_only = SN76489(clock_hz=3_579_545, sample_rate=44_100)
    muted = SN76489(clock_hz=3_579_545, sample_rate=44_100)

    for chip in (both, right_only, muted):
        chip.write(0x80 | 0x01)
        chip.write(0x00)
        chip.write(0x90 | 0x00)

    both.write_stereo_control(0x11)
    right_only.write_stereo_control(0x01)
    muted.write_stereo_control(0x00)

    both_sample = both.render_samples(1)[0]
    right_sample = right_only.render_samples(1)[0]
    muted_sample = muted.render_samples(1)[0]

    assert both.read_stereo_control() == 0x11
    assert right_sample == both_sample // 2
    assert muted_sample == 0


def test_sn76489_renders_interleaved_stereo_samples():
    chip = SN76489(clock_hz=3_579_545, sample_rate=44_100)

    chip.write(0x80 | 0x01)
    chip.write(0x00)
    chip.write(0x90 | 0x00)
    chip.write_stereo_control(0x10)

    samples = chip.render_stereo_samples(4)

    assert len(samples) == 8
    assert all(samples[index] > 0 for index in range(0, len(samples), 2))
    assert all(samples[index] == 0 for index in range(1, len(samples), 2))


def test_sn76489_white_noise_is_non_silent():
    chip = SN76489(clock_hz=3_579_545, sample_rate=8_000)

    chip.write(0xE0 | 0x04)
    chip.write(0xF0 | 0x00)

    samples = chip.render_samples(256)

    assert any(sample != 0 for sample in samples)


def test_sn76489_state_roundtrip_preserves_filter_state():
    chip = SN76489(clock_hz=3_579_545, sample_rate=8_000)

    chip.write(0x80 | 0x00 | 0x01)
    chip.write(0x00)
    chip.write(0x90 | 0x02)
    chip.render_samples(64)

    state = chip.read_state()
    restored = SN76489(clock_hz=1, sample_rate=1)
    restored.write_state(state)

    assert restored.read_state() == state


def test_sn76489_tone_frequency_is_close_to_expected():
    sample_rate = 44_100
    clock_hz = 3_579_545
    period = 0x20
    expected_hz = clock_hz / (32.0 * period)

    chip = SN76489(clock_hz=clock_hz, sample_rate=sample_rate)
    chip.write(0x80 | 0x00 | (period & 0x0F))
    chip.write((period >> 4) & 0x3F)
    chip.write(0x90 | 0x00)

    samples = chip.render_samples(4096)[512:]
    signs = [1 if sample >= 0 else -1 for sample in samples]
    crossings = []
    previous = signs[0]
    for index, sign in enumerate(signs[1:], 1):
        if sign != previous:
            crossings.append(index)
            previous = sign

    half_periods = [b - a for a, b in zip(crossings, crossings[1:])]
    measured_hz = sample_rate / (2.0 * mean(half_periods))

    assert abs(measured_hz - expected_hz) / expected_hz < 0.01


def _program_reference_sequence(chip) -> None:
    chip.write(0x80 | 0x00 | 0x01)
    chip.write(0x12)
    chip.write(0x90 | 0x02)
    chip.write(0xA0 | 0x06)
    chip.write(0x05)
    chip.write(0xB0 | 0x05)
    chip.write(0xE0 | 0x04)
    chip.write(0xF0 | 0x03)


def test_sn76489_matches_reference_state_after_writes():
    chip = SN76489(clock_hz=3_579_545, sample_rate=44_100)
    reference = SN76489Reference(clock_hz=3_579_545, sample_rate=44_100)

    _program_reference_sequence(chip)
    _program_reference_sequence(reference)

    state = chip.read_state()
    ref_state = reference.read_state()
    assert {k: v for k, v in state.items() if k != "__meta__"} == {
        k: v for k, v in ref_state.items() if k != "__meta__"
    }


def test_sn76489_matches_reference_samples():
    chip = SN76489(clock_hz=3_579_545, sample_rate=44_100)
    reference = SN76489Reference(clock_hz=3_579_545, sample_rate=44_100)

    _program_reference_sequence(chip)
    _program_reference_sequence(reference)

    assert chip.render_samples(512).tolist() == reference.render_samples(512).tolist()
