from __future__ import annotations

from array import array
from math import exp, pi

from multiemu.state_codec import read_state_fields, write_state_fields


class SN76489Reference:
    """Python reference SN76489 PSG used as an equivalence oracle."""

    _VOLUME_TABLE = tuple(
        0.0 if level >= 0x0F else 10.0 ** ((-2.0 * level) / 20.0)
        for level in range(0x10)
    )

    def __init__(self, *, clock_hz: int = 3_579_545, sample_rate: int = 44_100):
        self.clock_hz = int(clock_hz)
        self.sample_rate = max(1, int(sample_rate))
        self.reset()

    def reset(self) -> None:
        self._latched_channel = 0
        self._latched_is_volume = False
        self._tone_periods = [0x10, 0x10, 0x10]
        self._volumes = [0x0F, 0x0F, 0x0F, 0x0F]
        self._noise_control = 0x00
        self._tone_phases = [0.0, 0.0, 0.0]
        self._noise_phase = 0.0
        self._noise_output = 1.0
        self._noise_lfsr = 0x4000
        self._tone_steps = [0.0, 0.0, 0.0]
        self._attenuations = [0.0, 0.0, 0.0, 0.0]
        self._noise_step_value = 0.0
        self._output_smooth = 0.0
        self._output_smooth_alpha = 0.0
        self._dc_block_x = 0.0
        self._dc_block_y = 0.0
        self._dc_block_alpha = 0.0
        self._refresh_cache()

    def _refresh_tone_step(self, channel: int) -> None:
        period = self._tone_periods[channel] & 0x3FF
        if period <= 0:
            period = 1
        frequency = self.clock_hz / (32.0 * period)
        self._tone_steps[channel] = frequency / self.sample_rate

    def _refresh_noise_step(self) -> None:
        rate = self._noise_control & 0x03
        if rate == 0x00:
            divisor = 16
        elif rate == 0x01:
            divisor = 32
        elif rate == 0x02:
            divisor = 64
        else:
            divisor = max(1, self._tone_periods[2] & 0x3FF)
        frequency = self.clock_hz / (32.0 * divisor)
        self._noise_step_value = frequency / self.sample_rate

    def _refresh_attenuation(self, channel: int) -> None:
        volume = self._volumes[channel] & 0x0F
        self._attenuations[channel] = self._VOLUME_TABLE[volume]

    def _refresh_cache(self) -> None:
        for channel in range(3):
            self._refresh_tone_step(channel)
        for channel in range(4):
            self._refresh_attenuation(channel)
        self._refresh_noise_step()
        lowpass_cutoff_hz = 6_000.0
        self._output_smooth_alpha = 1.0 - exp(
            (-2.0 * pi * lowpass_cutoff_hz) / float(self.sample_rate)
        )
        cutoff_hz = 20.0
        rc = 1.0 / (2.0 * pi * cutoff_hz)
        dt = 1.0 / float(self.sample_rate)
        self._dc_block_alpha = rc / (rc + dt)

    def write(self, value: int) -> None:
        value &= 0xFF
        if value & 0x80:
            self._latched_channel = (value >> 5) & 0x03
            self._latched_is_volume = bool(value & 0x10)
            nibble = value & 0x0F
            if self._latched_is_volume:
                self._volumes[self._latched_channel] = nibble
                self._refresh_attenuation(self._latched_channel)
            elif self._latched_channel == 3:
                self._noise_control = nibble & 0x07
                self._noise_lfsr = 0x4000
                self._refresh_noise_step()
            else:
                channel = self._latched_channel
                self._tone_periods[channel] = (self._tone_periods[channel] & 0x3F0) | nibble
                self._refresh_tone_step(channel)
                if channel == 2 and (self._noise_control & 0x03) == 0x03:
                    self._refresh_noise_step()
            return

        if self._latched_is_volume:
            self._volumes[self._latched_channel] = value & 0x0F
            self._refresh_attenuation(self._latched_channel)
        elif self._latched_channel == 3:
            self._noise_control = value & 0x07
            self._noise_lfsr = 0x4000
            self._refresh_noise_step()
        else:
            channel = self._latched_channel
            self._tone_periods[channel] = ((value & 0x3F) << 4) | (self._tone_periods[channel] & 0x0F)
            self._refresh_tone_step(channel)
            if channel == 2 and (self._noise_control & 0x03) == 0x03:
                self._refresh_noise_step()

    def _clock_noise(self) -> None:
        if self._noise_control & 0x04:
            feedback = (self._noise_lfsr ^ (self._noise_lfsr >> 3)) & 1
        else:
            feedback = self._noise_lfsr & 1
        self._noise_lfsr = ((self._noise_lfsr >> 1) | (feedback << 14)) & 0x7FFF
        if self._noise_lfsr == 0:
            self._noise_lfsr = 0x4000
        self._noise_output = 1.0 if (self._noise_lfsr & 1) == 0 else -1.0

    def render_samples(self, count: int) -> array:
        count = int(count)
        out = array("h")
        if count <= 0:
            return out
        out.extend([0] * count)

        tone_phases = self._tone_phases
        tone_steps = self._tone_steps
        attenuations = self._attenuations
        noise_phase = self._noise_phase
        noise_step = self._noise_step_value
        noise_output = self._noise_output
        output_smooth = self._output_smooth
        output_smooth_alpha = self._output_smooth_alpha
        dc_block_x = self._dc_block_x
        dc_block_y = self._dc_block_y
        dc_block_alpha = self._dc_block_alpha

        append_scale = 32767

        for index in range(count):
            mix = 0.0
            phase0 = tone_phases[0] + tone_steps[0]
            if phase0 >= 1.0:
                phase0 -= int(phase0)
            tone_phases[0] = phase0
            mix += (1.0 if phase0 < 0.5 else -1.0) * attenuations[0]

            phase1 = tone_phases[1] + tone_steps[1]
            if phase1 >= 1.0:
                phase1 -= int(phase1)
            tone_phases[1] = phase1
            mix += (1.0 if phase1 < 0.5 else -1.0) * attenuations[1]

            phase2 = tone_phases[2] + tone_steps[2]
            if phase2 >= 1.0:
                phase2 -= int(phase2)
            tone_phases[2] = phase2
            mix += (1.0 if phase2 < 0.5 else -1.0) * attenuations[2]

            noise_phase += noise_step
            while noise_phase >= 1.0:
                noise_phase -= 1.0
                self._clock_noise()
                noise_output = self._noise_output
            mix += noise_output * attenuations[3]

            sample = mix * 0.25
            output_smooth += output_smooth_alpha * (sample - output_smooth)
            sample = output_smooth
            filtered = dc_block_alpha * (dc_block_y + sample - dc_block_x)
            dc_block_x = sample
            dc_block_y = filtered
            sample = filtered
            if sample > 1.0:
                sample = 1.0
            elif sample < -1.0:
                sample = -1.0
            out[index] = int(sample * append_scale)
        self._noise_phase = noise_phase
        self._noise_output = noise_output
        self._output_smooth = output_smooth
        self._dc_block_x = dc_block_x
        self._dc_block_y = dc_block_y
        return out

    def read_state(self) -> dict:
        return read_state_fields(
            self,
            scalar_fields=("clock_hz", "sample_rate", "_latched_channel", "_latched_is_volume", "_noise_control", "_noise_phase", "_noise_output", "_noise_lfsr", "_output_smooth", "_output_smooth_alpha", "_dc_block_x", "_dc_block_y", "_dc_block_alpha"),
            meta={"type": "SN76489Reference"},
        ) | {
            "tone_periods": list(self._tone_periods),
            "volumes": list(self._volumes),
            "tone_phases": list(self._tone_phases),
        }

    def write_state(self, state: dict) -> None:
        write_state_fields(
            self,
            state,
            scalar_fields=("clock_hz", "sample_rate", "_latched_channel", "_latched_is_volume", "_noise_control", "_noise_phase", "_noise_output", "_noise_lfsr", "_output_smooth", "_output_smooth_alpha", "_dc_block_x", "_dc_block_y", "_dc_block_alpha"),
        )
        if "tone_periods" in state:
            values = [int(v) & 0x3FF for v in state["tone_periods"]]
            if len(values) != 3:
                raise ValueError("tone_periods debe tener 3 entradas")
            self._tone_periods = values
        if "volumes" in state:
            values = [int(v) & 0x0F for v in state["volumes"]]
            if len(values) != 4:
                raise ValueError("volumes debe tener 4 entradas")
            self._volumes = values
        if "tone_phases" in state:
            values = [float(v) for v in state["tone_phases"]]
            if len(values) != 3:
                raise ValueError("tone_phases debe tener 3 entradas")
            self._tone_phases = values
        self._refresh_cache()
