from __future__ import annotations

from array import array
cdef double[16] _VOLUME_TABLE = [
    1.0,
    0.7943282347242815,
    0.6309573444801932,
    0.5011872336272722,
    0.3981071705534972,
    0.31622776601683794,
    0.251188643150958,
    0.19952623149688797,
    0.15848931924611134,
    0.12589254117941673,
    0.1,
    0.07943282347242814,
    0.06309573444801933,
    0.05011872336272722,
    0.039810717055349734,
    0.0,
]


cdef class SN76489:
    """Cython SN76489 PSG implementation.

    ``chipsets/sn76489.py`` remains the pure Python fallback and
    ``SN76489Reference`` remains the readable oracle for tests.
    """

    cdef public int clock_hz
    cdef public int sample_rate
    cdef int _latched_channel
    cdef bint _latched_is_volume
    cdef int _noise_control
    cdef int _noise_lfsr
    cdef int _tone_periods[3]
    cdef int _volumes[4]
    cdef double _tone_phases[3]
    cdef double _tone_steps[3]
    cdef double _attenuations[4]
    cdef double _noise_phase
    cdef double _noise_output
    cdef double _noise_step_value
    cdef double _output_smooth
    cdef double _output_smooth_alpha
    cdef double _dc_block_x
    cdef double _dc_block_y
    cdef double _dc_block_alpha
    cdef int _stereo_control

    def __init__(self, *, int clock_hz=3_579_545, int sample_rate=44_100):
        self.clock_hz = int(clock_hz)
        self.sample_rate = max(1, int(sample_rate))
        self.reset()

    cpdef void reset(self):
        cdef int channel
        self._latched_channel = 0
        self._latched_is_volume = False
        for channel in range(3):
            self._tone_periods[channel] = 0x10
            self._tone_phases[channel] = 0.0
            self._tone_steps[channel] = 0.0
        for channel in range(4):
            self._volumes[channel] = 0x0F
            self._attenuations[channel] = 0.0
        self._noise_control = 0x00
        self._noise_phase = 0.0
        self._noise_output = 1.0
        self._noise_lfsr = 0x4000
        self._noise_step_value = 0.0
        self._output_smooth = 0.0
        self._output_smooth_alpha = 0.0
        self._dc_block_x = 0.0
        self._dc_block_y = 0.0
        self._dc_block_alpha = 0.0
        self._stereo_control = 0xFF
        self._refresh_cache()

    cdef void _refresh_tone_step(self, int channel):
        cdef int period = self._tone_periods[channel] & 0x3FF
        cdef double frequency
        if period <= 0:
            period = 1
        frequency = self.clock_hz / (32.0 * period)
        self._tone_steps[channel] = frequency / self.sample_rate

    cdef void _refresh_noise_step(self):
        cdef int rate = self._noise_control & 0x03
        cdef int divisor
        cdef double frequency
        if rate == 0x00:
            divisor = 16
        elif rate == 0x01:
            divisor = 32
        elif rate == 0x02:
            divisor = 64
        else:
            divisor = self._tone_periods[2] & 0x3FF
            if divisor < 1:
                divisor = 1
        frequency = self.clock_hz / (32.0 * divisor)
        self._noise_step_value = frequency / self.sample_rate

    cdef void _refresh_attenuation(self, int channel):
        self._attenuations[channel] = _VOLUME_TABLE[self._volumes[channel] & 0x0F]

    cdef void _refresh_cache(self):
        cdef int channel
        for channel in range(3):
            self._refresh_tone_step(channel)
        for channel in range(4):
            self._refresh_attenuation(channel)
        self._refresh_noise_step()
        self._output_smooth_alpha = 1.0
        self._dc_block_alpha = 1.0

    cpdef void write(self, int value):
        cdef int nibble
        cdef int channel
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

    cpdef void write_stereo_control(self, int value):
        self._stereo_control = value & 0xFF

    cpdef int read_stereo_control(self):
        return self._stereo_control & 0xFF

    cdef void _clock_noise(self):
        cdef int feedback
        if self._noise_control & 0x04:
            feedback = (self._noise_lfsr ^ (self._noise_lfsr >> 3)) & 1
        else:
            feedback = self._noise_lfsr & 1
        self._noise_lfsr = ((self._noise_lfsr >> 1) | (feedback << 14)) & 0x7FFF
        if self._noise_lfsr == 0:
            self._noise_lfsr = 0x4000
        self._noise_output = 1.0 if (self._noise_lfsr & 1) == 0 else -1.0

    cpdef object render_samples(self, int count):
        cdef object out
        cdef int index
        cdef int append_scale = 32767
        cdef double mix
        cdef double phase0
        cdef double phase1
        cdef double phase2
        cdef double noise_phase
        cdef double noise_step
        cdef double noise_output
        cdef double sample
        cdef double pan0
        cdef double pan1
        cdef double pan2
        cdef double pan3

        out = array("h")
        if count <= 0:
            return out
        out.extend([0] * count)

        noise_phase = self._noise_phase
        noise_step = self._noise_step_value
        noise_output = self._noise_output
        pan0 = (((self._stereo_control >> 0) & 1) + ((self._stereo_control >> 4) & 1)) * 0.5
        pan1 = (((self._stereo_control >> 1) & 1) + ((self._stereo_control >> 5) & 1)) * 0.5
        pan2 = (((self._stereo_control >> 2) & 1) + ((self._stereo_control >> 6) & 1)) * 0.5
        pan3 = (((self._stereo_control >> 3) & 1) + ((self._stereo_control >> 7) & 1)) * 0.5

        for index in range(count):
            mix = 0.0

            if self._tone_periods[0] <= 1:
                mix += self._attenuations[0] * pan0
            else:
                phase0 = self._tone_phases[0] + self._tone_steps[0]
                if phase0 >= 1.0:
                    phase0 -= <int>phase0
                self._tone_phases[0] = phase0
                mix += (1.0 if phase0 < 0.5 else -1.0) * self._attenuations[0] * pan0

            if self._tone_periods[1] <= 1:
                mix += self._attenuations[1] * pan1
            else:
                phase1 = self._tone_phases[1] + self._tone_steps[1]
                if phase1 >= 1.0:
                    phase1 -= <int>phase1
                self._tone_phases[1] = phase1
                mix += (1.0 if phase1 < 0.5 else -1.0) * self._attenuations[1] * pan1

            if self._tone_periods[2] <= 1:
                mix += self._attenuations[2] * pan2
            else:
                phase2 = self._tone_phases[2] + self._tone_steps[2]
                if phase2 >= 1.0:
                    phase2 -= <int>phase2
                self._tone_phases[2] = phase2
                mix += (1.0 if phase2 < 0.5 else -1.0) * self._attenuations[2] * pan2

            noise_phase += noise_step
            while noise_phase >= 1.0:
                noise_phase -= 1.0
                self._clock_noise()
                noise_output = self._noise_output
            mix += noise_output * self._attenuations[3] * pan3

            sample = mix * 0.25
            if sample > 1.0:
                sample = 1.0
            elif sample < -1.0:
                sample = -1.0
            out[index] = <int>(sample * append_scale)

        self._noise_phase = noise_phase
        self._noise_output = noise_output
        return out

    cpdef object render_stereo_samples(self, int count):
        cdef object out
        cdef int index
        cdef int append_scale = 32767
        cdef double left
        cdef double right
        cdef double channel_sample
        cdef double phase0
        cdef double phase1
        cdef double phase2
        cdef double noise_phase
        cdef double noise_step
        cdef double noise_output
        cdef double left0 = 1.0 if (self._stereo_control & 0x10) else 0.0
        cdef double left1 = 1.0 if (self._stereo_control & 0x20) else 0.0
        cdef double left2 = 1.0 if (self._stereo_control & 0x40) else 0.0
        cdef double left3 = 1.0 if (self._stereo_control & 0x80) else 0.0
        cdef double right0 = 1.0 if (self._stereo_control & 0x01) else 0.0
        cdef double right1 = 1.0 if (self._stereo_control & 0x02) else 0.0
        cdef double right2 = 1.0 if (self._stereo_control & 0x04) else 0.0
        cdef double right3 = 1.0 if (self._stereo_control & 0x08) else 0.0

        out = array("h")
        if count <= 0:
            return out
        out.extend([0] * (count * 2))

        noise_phase = self._noise_phase
        noise_step = self._noise_step_value
        noise_output = self._noise_output

        for index in range(count):
            left = 0.0
            right = 0.0

            if self._tone_periods[0] <= 1:
                channel_sample = self._attenuations[0]
            else:
                phase0 = self._tone_phases[0] + self._tone_steps[0]
                if phase0 >= 1.0:
                    phase0 -= <int>phase0
                self._tone_phases[0] = phase0
                channel_sample = (1.0 if phase0 < 0.5 else -1.0) * self._attenuations[0]
            left += channel_sample * left0
            right += channel_sample * right0

            if self._tone_periods[1] <= 1:
                channel_sample = self._attenuations[1]
            else:
                phase1 = self._tone_phases[1] + self._tone_steps[1]
                if phase1 >= 1.0:
                    phase1 -= <int>phase1
                self._tone_phases[1] = phase1
                channel_sample = (1.0 if phase1 < 0.5 else -1.0) * self._attenuations[1]
            left += channel_sample * left1
            right += channel_sample * right1

            if self._tone_periods[2] <= 1:
                channel_sample = self._attenuations[2]
            else:
                phase2 = self._tone_phases[2] + self._tone_steps[2]
                if phase2 >= 1.0:
                    phase2 -= <int>phase2
                self._tone_phases[2] = phase2
                channel_sample = (1.0 if phase2 < 0.5 else -1.0) * self._attenuations[2]
            left += channel_sample * left2
            right += channel_sample * right2

            noise_phase += noise_step
            while noise_phase >= 1.0:
                noise_phase -= 1.0
                self._clock_noise()
                noise_output = self._noise_output
            channel_sample = noise_output * self._attenuations[3]
            left += channel_sample * left3
            right += channel_sample * right3

            left *= 0.25
            right *= 0.25
            if left > 1.0:
                left = 1.0
            elif left < -1.0:
                left = -1.0
            if right > 1.0:
                right = 1.0
            elif right < -1.0:
                right = -1.0
            out[index * 2] = <int>(left * append_scale)
            out[index * 2 + 1] = <int>(right * append_scale)

        self._noise_phase = noise_phase
        self._noise_output = noise_output
        return out

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "SN76489"},
            "clock_hz": self.clock_hz,
            "sample_rate": self.sample_rate,
            "_latched_channel": self._latched_channel,
            "_latched_is_volume": bool(self._latched_is_volume),
            "_noise_control": self._noise_control,
            "_noise_phase": self._noise_phase,
            "_noise_output": self._noise_output,
            "_noise_lfsr": self._noise_lfsr,
            "_output_smooth": self._output_smooth,
            "_output_smooth_alpha": self._output_smooth_alpha,
            "_dc_block_x": self._dc_block_x,
            "_dc_block_y": self._dc_block_y,
            "_dc_block_alpha": self._dc_block_alpha,
            "_stereo_control": self._stereo_control,
            "tone_periods": [self._tone_periods[0], self._tone_periods[1], self._tone_periods[2]],
            "volumes": [self._volumes[0], self._volumes[1], self._volumes[2], self._volumes[3]],
            "tone_phases": [self._tone_phases[0], self._tone_phases[1], self._tone_phases[2]],
        }

    def write_state(self, state: dict) -> None:
        cdef list values
        if "clock_hz" in state:
            self.clock_hz = int(state["clock_hz"])
        if "sample_rate" in state:
            self.sample_rate = max(1, int(state["sample_rate"]))
        if "_latched_channel" in state:
            self._latched_channel = int(state["_latched_channel"]) & 0x03
        if "_latched_is_volume" in state:
            self._latched_is_volume = bool(state["_latched_is_volume"])
        if "_noise_control" in state:
            self._noise_control = int(state["_noise_control"]) & 0x07
        if "_noise_phase" in state:
            self._noise_phase = float(state["_noise_phase"])
        if "_noise_output" in state:
            self._noise_output = float(state["_noise_output"])
        if "_noise_lfsr" in state:
            self._noise_lfsr = int(state["_noise_lfsr"]) & 0x7FFF
            if self._noise_lfsr == 0:
                self._noise_lfsr = 0x4000
        if "_output_smooth" in state:
            self._output_smooth = float(state["_output_smooth"])
        if "_output_smooth_alpha" in state:
            self._output_smooth_alpha = float(state["_output_smooth_alpha"])
        if "_dc_block_x" in state:
            self._dc_block_x = float(state["_dc_block_x"])
        if "_dc_block_y" in state:
            self._dc_block_y = float(state["_dc_block_y"])
        if "_dc_block_alpha" in state:
            self._dc_block_alpha = float(state["_dc_block_alpha"])
        if "_stereo_control" in state:
            self._stereo_control = int(state["_stereo_control"]) & 0xFF
        if "tone_periods" in state:
            values = [int(v) & 0x3FF for v in state["tone_periods"]]
            if len(values) != 3:
                raise ValueError("tone_periods debe tener 3 entradas")
            self._tone_periods[0] = values[0]
            self._tone_periods[1] = values[1]
            self._tone_periods[2] = values[2]
        if "volumes" in state:
            values = [int(v) & 0x0F for v in state["volumes"]]
            if len(values) != 4:
                raise ValueError("volumes debe tener 4 entradas")
            self._volumes[0] = values[0]
            self._volumes[1] = values[1]
            self._volumes[2] = values[2]
            self._volumes[3] = values[3]
        if "tone_phases" in state:
            values = [float(v) for v in state["tone_phases"]]
            if len(values) != 3:
                raise ValueError("tone_phases debe tener 3 entradas")
            self._tone_phases[0] = values[0]
            self._tone_phases[1] = values[1]
            self._tone_phases[2] = values[2]
        self._refresh_cache()
