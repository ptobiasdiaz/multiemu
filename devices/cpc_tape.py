from __future__ import annotations

from dataclasses import dataclass


TZX_CLOCK_HZ = 3_500_000
DEFAULT_CPC_CLOCK_HZ = 4_000_000


def _tzx_to_cpc_tstates(duration: int, *, cpc_clock_hz: int = DEFAULT_CPC_CLOCK_HZ) -> int:
    """Convert TZX pulse lengths to CPC tstates.

    CDT reuses TZX block definitions whose timings are expressed in Spectrum
    T-states. We convert them to absolute duration and then to CPC tstates.
    """

    return max(1, int(round((duration * cpc_clock_hz) / TZX_CLOCK_HZ)))


@dataclass(slots=True)
class TapePulse:
    duration_tstates: int
    level: int


class CPCCassetteTape:
    """Minimal CDT/TZX playback device for CPC tape input."""

    STANDARD_PILOT_PULSE = 2168
    STANDARD_SYNC_FIRST = 667
    STANDARD_SYNC_SECOND = 735
    STANDARD_ZERO = 855
    STANDARD_ONE = 1710
    STANDARD_HEADER_PILOT_COUNT = 8063
    STANDARD_DATA_PILOT_COUNT = 3223

    FAST_MAX_PILOT_PULSES = 256
    FAST_MAX_PAUSE_MS = 100

    def __init__(self, pulses: list[TapePulse] | None = None):
        self.pulses = pulses or []
        self.reset()

    def reset(self) -> None:
        self.motor_on = False
        self.playing = True
        self._pulse_index = 0
        self._pulse_elapsed = 0
        self._level = 0 if not self.pulses else self.pulses[0].level

    @property
    def level(self) -> int:
        if not self.motor_on or not self.playing or not self.pulses:
            return 0
        return self._level

    def set_motor(self, enabled: bool) -> None:
        self.motor_on = bool(enabled)

    def set_playing(self, enabled: bool) -> None:
        self.playing = bool(enabled and self.pulses)

    def toggle_play_pause(self) -> bool:
        self.set_playing(not self.playing)
        return self.playing

    def run_cycles(self, cycles: int) -> None:
        if cycles <= 0 or not self.motor_on or not self.playing or not self.pulses:
            return

        remaining = cycles
        while remaining > 0 and self.playing:
            pulse = self.pulses[self._pulse_index]
            left = pulse.duration_tstates - self._pulse_elapsed
            if remaining < left:
                self._pulse_elapsed += remaining
                return

            remaining -= left
            self._pulse_index += 1
            self._pulse_elapsed = 0
            if self._pulse_index >= len(self.pulses):
                self.playing = False
                self._level = 0
                return
            self._level = self.pulses[self._pulse_index].level

    @classmethod
    def from_cdt_bytes(
        cls,
        data: bytes,
        *,
        fast: bool = False,
        max_pilot_pulses: int = FAST_MAX_PILOT_PULSES,
        max_pause_ms: int = FAST_MAX_PAUSE_MS,
    ) -> "CPCCassetteTape":
        if len(data) < 10 or not data.startswith(b"ZXTape!\x1A"):
            raise ValueError("CDT/TZX inválido: cabecera no reconocida")

        pulses: list[TapePulse] = []
        cursor = 10
        current_level = 1

        def add_pulse(duration: int) -> None:
            nonlocal current_level
            pulses.append(TapePulse(_tzx_to_cpc_tstates(duration), current_level))
            current_level ^= 1

        def add_pause(duration_ms: int) -> None:
            nonlocal current_level
            if fast:
                duration_ms = min(duration_ms, max_pause_ms)
            if duration_ms <= 0:
                pulses.append(TapePulse(1, 0))
                current_level = 1
                return
            pulses.append(TapePulse(max(1, duration_ms * 4000), 0))
            current_level = 1

        while cursor < len(data):
            block_id = data[cursor]
            cursor += 1

            if block_id == 0x10:
                pause_ms = int.from_bytes(data[cursor:cursor + 2], "little")
                block_length = int.from_bytes(data[cursor + 2:cursor + 4], "little")
                payload = data[cursor + 4:cursor + 4 + block_length]
                cursor += 4 + block_length
                pilot_count = (
                    cls.STANDARD_DATA_PILOT_COUNT
                    if payload and payload[0] >= 0x80
                    else cls.STANDARD_HEADER_PILOT_COUNT
                )
                if fast:
                    pilot_count = min(pilot_count, max_pilot_pulses)
                for _ in range(pilot_count):
                    add_pulse(cls.STANDARD_PILOT_PULSE)
                add_pulse(cls.STANDARD_SYNC_FIRST)
                add_pulse(cls.STANDARD_SYNC_SECOND)
                cls._append_data_bits(
                    add_pulse,
                    payload,
                    zero_length=cls.STANDARD_ZERO,
                    one_length=cls.STANDARD_ONE,
                    used_bits_last_byte=8,
                )
                add_pause(pause_ms)
                continue

            if block_id == 0x11:
                pilot = int.from_bytes(data[cursor:cursor + 2], "little")
                sync_first = int.from_bytes(data[cursor + 2:cursor + 4], "little")
                sync_second = int.from_bytes(data[cursor + 4:cursor + 6], "little")
                zero_length = int.from_bytes(data[cursor + 6:cursor + 8], "little")
                one_length = int.from_bytes(data[cursor + 8:cursor + 10], "little")
                pilot_count = int.from_bytes(data[cursor + 10:cursor + 12], "little")
                used_bits_last_byte = data[cursor + 12] or 8
                pause_ms = int.from_bytes(data[cursor + 13:cursor + 15], "little")
                block_length = int.from_bytes(data[cursor + 15:cursor + 18], "little")
                payload = data[cursor + 18:cursor + 18 + block_length]
                cursor += 18 + block_length
                if fast:
                    pilot_count = min(pilot_count, max_pilot_pulses)
                for _ in range(pilot_count):
                    add_pulse(pilot)
                add_pulse(sync_first)
                add_pulse(sync_second)
                cls._append_data_bits(
                    add_pulse,
                    payload,
                    zero_length=zero_length,
                    one_length=one_length,
                    used_bits_last_byte=used_bits_last_byte,
                )
                add_pause(pause_ms)
                continue

            if block_id == 0x20:
                pause_ms = int.from_bytes(data[cursor:cursor + 2], "little")
                cursor += 2
                add_pause(pause_ms)
                continue

            raise ValueError(f"bloque CDT/TZX no soportado aún: 0x{block_id:02X}")

        return cls(pulses)

    @staticmethod
    def _append_data_bits(
        add_pulse,
        payload: bytes,
        *,
        zero_length: int,
        one_length: int,
        used_bits_last_byte: int,
    ) -> None:
        if not payload:
            return

        for index, byte in enumerate(payload):
            bit_count = used_bits_last_byte if index == len(payload) - 1 else 8
            for bit in range(8):
                if bit >= bit_count:
                    break
                value = one_length if (byte & (0x80 >> bit)) else zero_length
                add_pulse(value)
                add_pulse(value)
