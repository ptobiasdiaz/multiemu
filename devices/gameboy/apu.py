"""Audio Processing Unit support for the original Game Boy."""

from __future__ import annotations

from array import array


class GameBoyAPU:
    """First-pass DMG APU with two pulse channels plus basic noise."""

    CPU_CLOCK_HZ = 4_194_304
    FRAME_SEQUENCER_HZ = 512
    DUTY_PATTERNS = (
        (0, 0, 0, 0, 0, 0, 0, 1),
        (1, 0, 0, 0, 0, 0, 0, 1),
        (1, 0, 0, 0, 0, 1, 1, 1),
        (0, 1, 1, 1, 1, 1, 1, 0),
    )

    def __init__(self, *, sample_rate: int = 44100):
        self.sample_rate = int(sample_rate)
        self._cycles_per_sample = self.CPU_CLOCK_HZ / float(self.sample_rate)
        self.reset()

    def reset(self) -> None:
        self.nr10 = 0x80
        self.nr11 = 0xBF
        self.nr12 = 0xF3
        self.nr13 = 0xFF
        self.nr14 = 0xBF
        self.nr21 = 0x3F
        self.nr22 = 0x00
        self.nr23 = 0xFF
        self.nr24 = 0xBF
        self.nr30 = 0x7F
        self.nr31 = 0xFF
        self.nr32 = 0x9F
        self.nr33 = 0xFF
        self.nr34 = 0xBF
        self.nr41 = 0xFF
        self.nr42 = 0x00
        self.nr43 = 0x00
        self.nr44 = 0xBF
        self.nr50 = 0x77
        self.nr51 = 0xF3
        self.nr52 = 0xF1

        self._master_enabled = True
        self._sample_clock = 0.0
        self._sequencer_clock = 0
        self._sequencer_step = 0
        self._frame_samples = array("h")

        self._ch1_enabled = False
        self._ch1_length_counter = 0
        self._ch1_length_enabled = False
        self._ch1_duty = 2
        self._ch1_initial_volume = 0
        self._ch1_volume = 0
        self._ch1_envelope_period = 0
        self._ch1_envelope_timer = 0
        self._ch1_envelope_increase = False
        self._ch1_frequency = 0
        self._ch1_phase = 0.0
        self._ch1_sweep_period = 0
        self._ch1_sweep_timer = 0
        self._ch1_sweep_shift = 0
        self._ch1_sweep_negate = False
        self._ch1_sweep_enabled = False
        self._ch1_sweep_shadow_frequency = 0

        self._ch2_enabled = False
        self._ch2_length_counter = 0
        self._ch2_length_enabled = False
        self._ch2_duty = 0
        self._ch2_initial_volume = 0
        self._ch2_volume = 0
        self._ch2_envelope_period = 0
        self._ch2_envelope_timer = 0
        self._ch2_envelope_increase = False
        self._ch2_frequency = 0
        self._ch2_phase = 0.0

        self._ch3_enabled = False
        self._ch3_dac_enabled = False
        self._ch3_length_counter = 0
        self._ch3_length_enabled = False
        self._ch3_output_level = 0
        self._ch3_frequency = 0
        self._ch3_phase = 0.0
        self._ch3_wave_ram = bytearray(16)

        self._ch4_enabled = False
        self._ch4_length_counter = 0
        self._ch4_length_enabled = False
        self._ch4_initial_volume = 0
        self._ch4_volume = 0
        self._ch4_envelope_period = 0
        self._ch4_envelope_timer = 0
        self._ch4_envelope_increase = False
        self._ch4_clock_shift = 0
        self._ch4_width_mode = False
        self._ch4_divisor_code = 0
        self._ch4_phase = 0.0
        self._ch4_lfsr = 0x7FFF

    def begin_frame(self) -> None:
        self._frame_samples = array("h")

    def get_frame_samples(self) -> array:
        return self._frame_samples

    def run_cycles(self, cycles: int) -> None:
        cycles = max(0, int(cycles))
        if cycles <= 0:
            return
        self._run_frame_sequencer(cycles)
        if not self._master_enabled:
            self._sample_clock += cycles
            while self._sample_clock >= self._cycles_per_sample:
                self._sample_clock -= self._cycles_per_sample
                self._frame_samples.append(0)
            return

        self._sample_clock += cycles
        while self._sample_clock >= self._cycles_per_sample:
            self._sample_clock -= self._cycles_per_sample
            self._frame_samples.append(self._mix_sample())

    def read_nr10(self) -> int:
        return self.nr10

    def write_nr10(self, value: int) -> None:
        self.nr10 = value & 0x7F
        self._ch1_sweep_period = (self.nr10 >> 4) & 0x07
        self._ch1_sweep_negate = (self.nr10 & 0x08) != 0
        self._ch1_sweep_shift = self.nr10 & 0x07

    def read_nr11(self) -> int:
        return self.nr11

    def write_nr11(self, value: int) -> None:
        self.nr11 = value & 0xFF
        self._ch1_duty = (value >> 6) & 0x03
        self._ch1_length_counter = 64 - (value & 0x3F)

    def read_nr12(self) -> int:
        return self.nr12

    def write_nr12(self, value: int) -> None:
        self.nr12 = value & 0xFF
        self._ch1_initial_volume = (self.nr12 >> 4) & 0x0F
        self._ch1_volume = self._ch1_initial_volume

    def read_nr13(self) -> int:
        return self.nr13

    def write_nr13(self, value: int) -> None:
        self.nr13 = value & 0xFF
        self._update_ch1_frequency()

    def read_nr14(self) -> int:
        return self.nr14

    def write_nr14(self, value: int) -> None:
        self.nr14 = value & 0xFF
        self._ch1_length_enabled = (self.nr14 & 0x40) != 0
        self._update_ch1_frequency()
        if self.nr14 & 0x80:
            self._trigger_ch1()

    def read_nr21(self) -> int:
        return self.nr21

    def write_nr21(self, value: int) -> None:
        self.nr21 = value & 0xFF
        self._ch2_duty = (value >> 6) & 0x03
        self._ch2_length_counter = 64 - (value & 0x3F)

    def read_nr22(self) -> int:
        return self.nr22

    def write_nr22(self, value: int) -> None:
        self.nr22 = value & 0xFF
        self._ch2_initial_volume = (self.nr22 >> 4) & 0x0F
        self._ch2_volume = self._ch2_initial_volume
        self._ch2_envelope_increase = (self.nr22 & 0x08) != 0
        self._ch2_envelope_period = self.nr22 & 0x07
        self._ch2_envelope_timer = self._ch2_envelope_period or 8

    def read_nr23(self) -> int:
        return self.nr23

    def write_nr23(self, value: int) -> None:
        self.nr23 = value & 0xFF
        self._update_ch2_frequency()

    def read_nr24(self) -> int:
        return self.nr24

    def write_nr24(self, value: int) -> None:
        self.nr24 = value & 0xFF
        self._ch2_length_enabled = (self.nr24 & 0x40) != 0
        self._update_ch2_frequency()
        if self.nr24 & 0x80:
            self._trigger_ch2()

    def read_nr30(self) -> int:
        return self.nr30

    def write_nr30(self, value: int) -> None:
        self.nr30 = value & 0xFF
        self._ch3_dac_enabled = (self.nr30 & 0x80) != 0
        if not self._ch3_dac_enabled:
            self._ch3_enabled = False

    def read_nr31(self) -> int:
        return self.nr31

    def write_nr31(self, value: int) -> None:
        self.nr31 = value & 0xFF
        self._ch3_length_counter = 256 - self.nr31

    def read_nr32(self) -> int:
        return self.nr32

    def write_nr32(self, value: int) -> None:
        self.nr32 = value & 0xFF
        self._ch3_output_level = (self.nr32 >> 5) & 0x03

    def read_nr33(self) -> int:
        return self.nr33

    def write_nr33(self, value: int) -> None:
        self.nr33 = value & 0xFF
        self._update_ch3_frequency()

    def read_nr34(self) -> int:
        return self.nr34

    def write_nr34(self, value: int) -> None:
        self.nr34 = value & 0xFF
        self._ch3_length_enabled = (self.nr34 & 0x40) != 0
        self._update_ch3_frequency()
        if self.nr34 & 0x80:
            self._trigger_ch3()

    def read_wave_ram(self, index: int) -> int:
        return self._ch3_wave_ram[index & 0x0F]

    def write_wave_ram(self, index: int, value: int) -> None:
        self._ch3_wave_ram[index & 0x0F] = value & 0xFF

    def read_nr41(self) -> int:
        return self.nr41

    def write_nr41(self, value: int) -> None:
        self.nr41 = value & 0x3F
        self._ch4_length_counter = 64 - (self.nr41 & 0x3F)

    def read_nr42(self) -> int:
        return self.nr42

    def write_nr42(self, value: int) -> None:
        self.nr42 = value & 0xFF
        self._ch4_initial_volume = (self.nr42 >> 4) & 0x0F
        self._ch4_volume = self._ch4_initial_volume
        self._ch4_envelope_increase = (self.nr42 & 0x08) != 0
        self._ch4_envelope_period = self.nr42 & 0x07
        self._ch4_envelope_timer = self._ch4_envelope_period or 8

    def read_nr43(self) -> int:
        return self.nr43

    def write_nr43(self, value: int) -> None:
        self.nr43 = value & 0xFF
        self._ch4_clock_shift = (self.nr43 >> 4) & 0x0F
        self._ch4_width_mode = (self.nr43 & 0x08) != 0
        self._ch4_divisor_code = self.nr43 & 0x07

    def read_nr44(self) -> int:
        return self.nr44

    def write_nr44(self, value: int) -> None:
        self.nr44 = value & 0xFF
        self._ch4_length_enabled = (self.nr44 & 0x40) != 0
        if self.nr44 & 0x80:
            self._trigger_ch4()

    def read_nr50(self) -> int:
        return self.nr50

    def write_nr50(self, value: int) -> None:
        self.nr50 = value & 0xFF

    def read_nr51(self) -> int:
        return self.nr51

    def write_nr51(self, value: int) -> None:
        self.nr51 = value & 0xFF

    def read_nr52(self) -> int:
        status = 0x80 if self._master_enabled else 0x00
        if self._ch1_enabled:
            status |= 0x01
        if self._ch2_enabled:
            status |= 0x02
        if self._ch3_enabled:
            status |= 0x04
        if self._ch4_enabled:
            status |= 0x08
        return status | 0x70

    def write_nr52(self, value: int) -> None:
        enabled = (value & 0x80) != 0
        if not enabled:
            self._master_enabled = False
            self._ch1_enabled = False
            self._ch2_enabled = False
            self._ch3_enabled = False
            self._ch4_enabled = False
            self.nr10 = 0
            self.nr11 = 0
            self.nr12 = 0
            self.nr13 = 0
            self.nr14 = 0
            self.nr21 = 0
            self.nr22 = 0
            self.nr23 = 0
            self.nr24 = 0
            self.nr30 = 0
            self.nr31 = 0
            self.nr32 = 0
            self.nr33 = 0
            self.nr34 = 0
            self.nr41 = 0
            self.nr42 = 0
            self.nr43 = 0
            self.nr44 = 0
            self.nr50 = 0
            self.nr51 = 0
            self.nr52 = 0
            self._ch1_volume = 0
            self._ch1_frequency = 0
            self._ch2_volume = 0
            self._ch2_frequency = 0
            self._ch3_frequency = 0
            self._ch4_volume = 0
            return

        if not self._master_enabled:
            self.reset()
        self._master_enabled = True
        self.nr52 = 0x80

    def _update_ch1_frequency(self) -> None:
        self._ch1_frequency = ((self.nr14 & 0x07) << 8) | self.nr13

    def _trigger_ch1(self) -> None:
        self._update_ch1_frequency()
        self._ch1_enabled = ((self.nr12 >> 3) & 0x1E) != 0
        self._ch1_volume = self._ch1_initial_volume
        self._ch1_envelope_increase = (self.nr12 & 0x08) != 0
        self._ch1_envelope_period = self.nr12 & 0x07
        self._ch1_envelope_timer = self._ch1_envelope_period or 8
        self._ch1_sweep_shadow_frequency = self._ch1_frequency
        self._ch1_sweep_timer = self._ch1_sweep_period or 8
        self._ch1_sweep_enabled = self._ch1_sweep_period != 0 or self._ch1_sweep_shift != 0
        if self._ch1_length_counter == 0:
            self._ch1_length_counter = 64
        if self._ch1_sweep_shift != 0:
            self._ch1_calculate_sweep_frequency(apply_update=False)

    def _update_ch2_frequency(self) -> None:
        self._ch2_frequency = ((self.nr24 & 0x07) << 8) | self.nr23

    def _trigger_ch2(self) -> None:
        self._update_ch2_frequency()
        self._ch2_enabled = ((self.nr22 >> 3) & 0x1E) != 0
        self._ch2_volume = self._ch2_initial_volume
        self._ch2_envelope_increase = (self.nr22 & 0x08) != 0
        self._ch2_envelope_period = self.nr22 & 0x07
        self._ch2_envelope_timer = self._ch2_envelope_period or 8
        if self._ch2_length_counter == 0:
            self._ch2_length_counter = 64

    def _update_ch3_frequency(self) -> None:
        self._ch3_frequency = ((self.nr34 & 0x07) << 8) | self.nr33

    def _trigger_ch3(self) -> None:
        self._update_ch3_frequency()
        self._ch3_enabled = self._ch3_dac_enabled
        self._ch3_phase = 0.0
        if self._ch3_length_counter == 0:
            self._ch3_length_counter = 256

    def _trigger_ch4(self) -> None:
        self.write_nr43(self.nr43)
        self._ch4_enabled = ((self.nr42 >> 3) & 0x1E) != 0
        self._ch4_volume = self._ch4_initial_volume
        self._ch4_envelope_increase = (self.nr42 & 0x08) != 0
        self._ch4_envelope_period = self.nr42 & 0x07
        self._ch4_envelope_timer = self._ch4_envelope_period or 8
        self._ch4_lfsr = 0x7FFF
        self._ch4_phase = 0.0
        if self._ch4_length_counter == 0:
            self._ch4_length_counter = 64

    def _mix_sample(self) -> int:
        ch1 = self._render_ch1_sample()
        ch2 = self._render_ch2_sample()
        ch3 = self._render_ch3_sample()
        ch4 = self._render_ch4_sample()

        left_mix = 0.0
        right_mix = 0.0
        if (self.nr51 & 0x10) != 0:
            left_mix += ch1
        if (self.nr51 & 0x20) != 0:
            left_mix += ch2
        if (self.nr51 & 0x40) != 0:
            left_mix += ch3
        if (self.nr51 & 0x80) != 0:
            left_mix += ch4
        if (self.nr51 & 0x01) != 0:
            right_mix += ch1
        if (self.nr51 & 0x02) != 0:
            right_mix += ch2
        if (self.nr51 & 0x04) != 0:
            right_mix += ch3
        if (self.nr51 & 0x08) != 0:
            right_mix += ch4

        if left_mix == 0.0 and right_mix == 0.0:
            return 0

        left_volume = ((self.nr50 >> 4) & 0x07) + 1
        right_volume = (self.nr50 & 0x07) + 1
        mix = (left_mix * left_volume + right_mix * right_volume) * 0.5
        return int(max(-32767, min(32767, mix * 2048)))

    def _render_ch1_sample(self) -> float:
        if not self._master_enabled or not self._ch1_enabled or self._ch1_volume == 0:
            return 0.0

        frequency = self._ch1_output_hz()
        if frequency <= 0.0:
            return 0.0

        self._ch1_phase = (self._ch1_phase + frequency / self.sample_rate) % 1.0
        duty_pattern = self.DUTY_PATTERNS[self._ch1_duty]
        duty_index = int(self._ch1_phase * 8.0) & 0x07
        level = 1.0 if duty_pattern[duty_index] else -1.0
        return level * (self._ch1_volume / 15.0)

    def _ch1_output_hz(self) -> float:
        if self._ch1_frequency >= 2048:
            return 0.0
        return 131072.0 / (2048 - self._ch1_frequency)

    def _render_ch2_sample(self) -> float:
        if not self._master_enabled or not self._ch2_enabled or self._ch2_volume == 0:
            return 0.0

        frequency = self._ch2_output_hz()
        if frequency <= 0.0:
            return 0.0

        self._ch2_phase = (self._ch2_phase + frequency / self.sample_rate) % 1.0
        duty_pattern = self.DUTY_PATTERNS[self._ch2_duty]
        duty_index = int(self._ch2_phase * 8.0) & 0x07
        level = 1.0 if duty_pattern[duty_index] else -1.0
        return level * (self._ch2_volume / 15.0)

    def _ch2_output_hz(self) -> float:
        if self._ch2_frequency >= 2048:
            return 0.0
        return 131072.0 / (2048 - self._ch2_frequency)

    def _render_ch3_sample(self) -> float:
        if not self._master_enabled or not self._ch3_enabled or not self._ch3_dac_enabled:
            return 0.0
        if self._ch3_output_level == 0:
            return 0.0

        frequency = self._ch3_output_hz()
        if frequency <= 0.0:
            return 0.0

        self._ch3_phase = (self._ch3_phase + frequency / self.sample_rate) % 1.0
        sample_index = int(self._ch3_phase * 32.0) & 0x1F
        sample_byte = self._ch3_wave_ram[sample_index >> 1]
        if (sample_index & 0x01) == 0:
            sample = (sample_byte >> 4) & 0x0F
        else:
            sample = sample_byte & 0x0F

        if self._ch3_output_level == 1:
            scaled = sample
        elif self._ch3_output_level == 2:
            scaled = sample >> 1
        else:
            scaled = sample >> 2
        return ((scaled / 7.5) - 1.0) if scaled else -1.0

    def _ch3_output_hz(self) -> float:
        if self._ch3_frequency >= 2048:
            return 0.0
        return 65536.0 / (2048 - self._ch3_frequency)

    def _render_ch4_sample(self) -> float:
        if not self._master_enabled or not self._ch4_enabled or self._ch4_volume == 0:
            return 0.0

        frequency = self._ch4_output_hz()
        if frequency <= 0.0:
            return 0.0

        self._ch4_phase += frequency / self.sample_rate
        while self._ch4_phase >= 1.0:
            self._ch4_phase -= 1.0
            xor_bit = (self._ch4_lfsr & 0x01) ^ ((self._ch4_lfsr >> 1) & 0x01)
            self._ch4_lfsr = (self._ch4_lfsr >> 1) | (xor_bit << 14)
            if self._ch4_width_mode:
                self._ch4_lfsr = (self._ch4_lfsr & ~(1 << 6)) | (xor_bit << 6)

        level = -1.0 if (self._ch4_lfsr & 0x01) else 1.0
        return level * (self._ch4_volume / 15.0)

    def _ch4_output_hz(self) -> float:
        divisors = (8, 16, 32, 48, 64, 80, 96, 112)
        divisor = divisors[self._ch4_divisor_code]
        return 524288.0 / divisor / (2**(self._ch4_clock_shift + 1))

    def _run_frame_sequencer(self, cycles: int) -> None:
        if not self._master_enabled:
            return
        self._sequencer_clock += cycles
        step_cycles = self.CPU_CLOCK_HZ // self.FRAME_SEQUENCER_HZ
        while self._sequencer_clock >= step_cycles:
            self._sequencer_clock -= step_cycles
            self._sequencer_tick()

    def _sequencer_tick(self) -> None:
        step = self._sequencer_step
        if step in {0, 2, 4, 6}:
            self._clock_length()
        if step in {2, 6}:
            self._clock_sweep()
        if step == 7:
            self._clock_envelopes()
        self._sequencer_step = (self._sequencer_step + 1) & 0x07

    def _clock_sweep(self) -> None:
        if not self._ch1_sweep_enabled:
            return
        self._ch1_sweep_timer -= 1
        if self._ch1_sweep_timer > 0:
            return

        self._ch1_sweep_timer = self._ch1_sweep_period or 8
        if self._ch1_sweep_period == 0:
            return

        new_frequency = self._ch1_calculate_sweep_frequency(apply_update=True)
        if new_frequency is None:
            return
        if self._ch1_sweep_shift != 0:
            self._ch1_calculate_sweep_frequency(apply_update=False)

    def _ch1_calculate_sweep_frequency(self, *, apply_update: bool) -> int | None:
        delta = self._ch1_sweep_shadow_frequency >> self._ch1_sweep_shift
        if self._ch1_sweep_negate:
            new_frequency = self._ch1_sweep_shadow_frequency - delta
        else:
            new_frequency = self._ch1_sweep_shadow_frequency + delta

        if new_frequency > 2047:
            self._ch1_enabled = False
            return None

        if apply_update and self._ch1_sweep_shift != 0:
            self._ch1_sweep_shadow_frequency = new_frequency
            self._ch1_frequency = new_frequency
            self.nr13 = new_frequency & 0xFF
            self.nr14 = (self.nr14 & 0xF8) | ((new_frequency >> 8) & 0x07)
        return new_frequency

    def _clock_length(self) -> None:
        if self._ch1_enabled and self._ch1_length_enabled and self._ch1_length_counter > 0:
            self._ch1_length_counter -= 1
            if self._ch1_length_counter == 0:
                self._ch1_enabled = False
        if self._ch2_enabled and self._ch2_length_enabled and self._ch2_length_counter > 0:
            self._ch2_length_counter -= 1
            if self._ch2_length_counter == 0:
                self._ch2_enabled = False
        if self._ch3_enabled and self._ch3_length_enabled and self._ch3_length_counter > 0:
            self._ch3_length_counter -= 1
            if self._ch3_length_counter == 0:
                self._ch3_enabled = False
        if self._ch4_enabled and self._ch4_length_enabled and self._ch4_length_counter > 0:
            self._ch4_length_counter -= 1
            if self._ch4_length_counter == 0:
                self._ch4_enabled = False

    def _clock_envelopes(self) -> None:
        self._clock_channel_envelope(
            enabled_attr="_ch1_enabled",
            period_attr="_ch1_envelope_period",
            timer_attr="_ch1_envelope_timer",
            increase_attr="_ch1_envelope_increase",
            volume_attr="_ch1_volume",
        )
        self._clock_channel_envelope(
            enabled_attr="_ch2_enabled",
            period_attr="_ch2_envelope_period",
            timer_attr="_ch2_envelope_timer",
            increase_attr="_ch2_envelope_increase",
            volume_attr="_ch2_volume",
        )
        self._clock_channel_envelope(
            enabled_attr="_ch4_enabled",
            period_attr="_ch4_envelope_period",
            timer_attr="_ch4_envelope_timer",
            increase_attr="_ch4_envelope_increase",
            volume_attr="_ch4_volume",
        )

    def _clock_channel_envelope(
        self,
        *,
        enabled_attr: str,
        period_attr: str,
        timer_attr: str,
        increase_attr: str,
        volume_attr: str,
    ) -> None:
        if not getattr(self, enabled_attr):
            return
        period = getattr(self, period_attr)
        if period == 0:
            return
        timer = getattr(self, timer_attr) - 1
        if timer > 0:
            setattr(self, timer_attr, timer)
            return

        setattr(self, timer_attr, period)
        volume = getattr(self, volume_attr)
        if getattr(self, increase_attr):
            if volume < 15:
                setattr(self, volume_attr, volume + 1)
        else:
            if volume > 0:
                setattr(self, volume_attr, volume - 1)
