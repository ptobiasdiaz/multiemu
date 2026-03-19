from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from typing import Callable


PortReadFn = Callable[[], int]
PortWriteFn = Callable[[int], None]


@dataclass(slots=True)
class AY38912:
    """Reference pure-Python AY-3-8912 model kept only for tests."""

    clock_hz: int = 1_000_000
    sample_rate: int = 44_100
    port_a_read: PortReadFn | None = None
    port_a_write: PortWriteFn | None = None
    port_b_read: PortReadFn | None = None
    port_b_write: PortWriteFn | None = None
    port_a_read_through_output: bool = False
    port_b_read_through_output: bool = False
    selected_register: int = 0
    registers: list[int] = field(default_factory=lambda: [0] * 16)
    last_read_value: int = 0xFF
    sample_phase: float = 0.0
    tone_counters: list[int] = field(default_factory=lambda: [1, 1, 1])
    tone_outputs: list[int] = field(default_factory=lambda: [1, 1, 1])
    noise_counter: int = 1
    noise_output: int = 1
    noise_lfsr: int = 0x1FFFF
    envelope_counter: int = 1
    envelope_step: int = 0
    envelope_holding: bool = False

    REGISTER_MASKS = (
        0xFF, 0x0F,
        0xFF, 0x0F,
        0xFF, 0x0F,
        0x1F,
        0xFF,
        0x1F,
        0x1F,
        0x1F,
        0xFF, 0xFF,
        0x0F,
        0xFF,
        0xFF,
    )

    LEVEL_TABLE = (
        0,
        513,
        724,
        1023,
        1445,
        2040,
        2883,
        4073,
        5753,
        8124,
        11472,
        16206,
        22898,
        32359,
        45738,
        64635,
    )

    def __post_init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.selected_register = 0
        self.registers[:] = [0] * 16
        self.last_read_value = 0xFF
        self.sample_phase = 0.0
        self.tone_counters[:] = [1, 1, 1]
        self.tone_outputs[:] = [1, 1, 1]
        self.noise_counter = 1
        self.noise_output = 1
        self.noise_lfsr = 0x1FFFF
        self.envelope_counter = 1
        self.envelope_step = 0
        self.envelope_holding = False

    def select_register(self, register_index: int) -> None:
        self.selected_register = register_index & 0x0F

    def write_selected(self, value: int) -> None:
        register_index = self.selected_register
        value &= self.REGISTER_MASKS[register_index]
        self.registers[register_index] = value

        if register_index == 13:
            self._restart_envelope()
        elif register_index == 14 and self.port_a_write is not None and self.port_a_is_output:
            self.port_a_write(value)
        elif register_index == 15 and self.port_b_write is not None and self.port_b_is_output:
            self.port_b_write(value)

    def read_selected(self) -> int:
        register_index = self.selected_register

        if (
            register_index == 14
            and self.port_a_read is not None
            and (self.port_a_is_input or self.port_a_read_through_output)
        ):
            self.last_read_value = self.port_a_read() & 0xFF
            return self.last_read_value

        if (
            register_index == 15
            and self.port_b_read is not None
            and (self.port_b_is_input or self.port_b_read_through_output)
        ):
            self.last_read_value = self.port_b_read() & 0xFF
            return self.last_read_value

        self.last_read_value = self.registers[register_index] & self.REGISTER_MASKS[register_index]
        return self.last_read_value

    @property
    def port_a_is_input(self) -> bool:
        return bool(self.registers[7] & 0x40)

    @property
    def port_a_is_output(self) -> bool:
        return not self.port_a_is_input

    @property
    def port_b_is_input(self) -> bool:
        return bool(self.registers[7] & 0x80)

    @property
    def port_b_is_output(self) -> bool:
        return not self.port_b_is_input

    def get_tone_period(self, channel: int) -> int:
        base = channel * 2
        period = self.registers[base] | ((self.registers[base + 1] & 0x0F) << 8)
        return period or 1

    def get_noise_period(self) -> int:
        return (self.registers[6] & 0x1F) or 1

    def get_envelope_period(self) -> int:
        return ((self.registers[12] << 8) | self.registers[11]) or 1

    def render_samples(self, sample_count: int) -> array:
        sample_count = max(0, int(sample_count))
        out = array("h")
        if sample_count <= 0:
            return out

        psg_cycles_per_sample = self.clock_hz / (16.0 * self.sample_rate)

        for _ in range(sample_count):
            self.sample_phase += psg_cycles_per_sample
            whole_cycles = int(self.sample_phase)
            self.sample_phase -= whole_cycles

            if whole_cycles <= 0:
                whole_cycles = 1

            for _ in range(whole_cycles):
                self._step_psg_cycle()

            mixed = self._mix_output()
            out.append(max(-32768, min(32767, mixed)))

        return out

    def _step_psg_cycle(self) -> None:
        for channel in range(3):
            self.tone_counters[channel] -= 1
            if self.tone_counters[channel] <= 0:
                self.tone_counters[channel] = self.get_tone_period(channel)
                self.tone_outputs[channel] ^= 1

        self.noise_counter -= 1
        if self.noise_counter <= 0:
            self.noise_counter = self.get_noise_period()
            bit0 = self.noise_lfsr & 1
            bit3 = (self.noise_lfsr >> 3) & 1
            feedback = bit0 ^ bit3
            self.noise_lfsr = ((self.noise_lfsr >> 1) | (feedback << 16)) & 0x1FFFF
            self.noise_output = self.noise_lfsr & 1

        if not self.envelope_holding:
            self.envelope_counter -= 1
            if self.envelope_counter <= 0:
                self.envelope_counter = self.get_envelope_period()
                self._advance_envelope()

    def _mix_output(self) -> int:
        total = 0

        for channel in range(3):
            if not self._channel_enabled(channel):
                continue
            total += self.LEVEL_TABLE[self._get_channel_level(channel)]

        return int((total / (3 * self.LEVEL_TABLE[-1])) * 32767.0)

    def _channel_enabled(self, channel: int) -> bool:
        tone_disabled = bool(self.registers[7] & (1 << channel))
        noise_disabled = bool(self.registers[7] & (1 << (channel + 3)))
        tone_ok = tone_disabled or bool(self.tone_outputs[channel])
        noise_ok = noise_disabled or bool(self.noise_output)
        return tone_ok and noise_ok

    def _get_channel_level(self, channel: int) -> int:
        reg = self.registers[8 + channel] & 0x1F
        if reg & 0x10:
            return self._get_envelope_level()
        return reg & 0x0F

    def _restart_envelope(self) -> None:
        self.envelope_counter = self.get_envelope_period()
        self.envelope_holding = False
        self.envelope_step = 0

    def _advance_envelope(self) -> None:
        self.envelope_step += 1
        if self.envelope_step < 16:
            return

        continue_flag = bool(self.registers[13] & 0x08)
        hold_flag = bool(self.registers[13] & 0x01)
        alternate_flag = bool(self.registers[13] & 0x02)

        if not continue_flag:
            self.envelope_step = 15
            self.envelope_holding = True
            return

        if hold_flag:
            self.envelope_step = 31 if alternate_flag else 15
            self.envelope_holding = True
            return

        if alternate_flag:
            if self.envelope_step >= 32:
                self.envelope_step -= 32
            return

        self.envelope_step -= 16

    def _get_envelope_level(self) -> int:
        attack = self._envelope_attack
        alternate = bool(self.registers[13] & 0x02)
        cycle = self.envelope_step // 16
        step = self.envelope_step & 0x0F

        if alternate and (cycle & 1):
            attack = not attack

        level = step if attack else (15 - step)
        return max(0, min(15, level))

    @property
    def _envelope_attack(self) -> bool:
        return bool(self.registers[13] & 0x04)
