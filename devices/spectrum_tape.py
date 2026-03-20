from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TapePulse:
    duration_tstates: int
    level: int


class SpectrumCassetteTape:
    """Minimal TZX playback device for Spectrum EAR input.

    This first pass intentionally supports only the standard-speed data block
    used by many classic 48K tapes, including ``phantomasa-48k.tzx``.
    """

    STANDARD_PILOT_PULSE = 2168
    STANDARD_SYNC_FIRST = 667
    STANDARD_SYNC_SECOND = 735
    STANDARD_ZERO = 855
    STANDARD_ONE = 1710
    STANDARD_HEADER_PILOT_COUNT = 8063
    STANDARD_DATA_PILOT_COUNT = 3223

    def __init__(self, pulses: list[TapePulse] | None = None):
        self.pulses = pulses or []
        self.reset()

    def reset(self) -> None:
        self.playing = False
        self._pulse_index = 0
        self._pulse_elapsed = 0
        self._level = 0 if not self.pulses else self.pulses[0].level

    def set_playing(self, enabled: bool) -> None:
        self.playing = bool(enabled and self.pulses)

    def toggle_play_pause(self) -> bool:
        self.set_playing(not self.playing)
        return self.playing

    @property
    def level(self) -> int:
        if not self.playing or not self.pulses:
            return 0
        return self._level

    def run_cycles(self, cycles: int) -> None:
        if cycles <= 0 or not self.playing or not self.pulses:
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
    def from_tzx_bytes(cls, data: bytes) -> "SpectrumCassetteTape":
        if len(data) < 10 or not data.startswith(b"ZXTape!\x1A"):
            raise ValueError("TZX inválido: cabecera no reconocida")

        pulses: list[TapePulse] = []
        cursor = 10
        current_level = 1

        def add_pulse(duration: int) -> None:
            nonlocal current_level
            pulses.append(TapePulse(max(1, duration), current_level))
            current_level ^= 1

        def add_pause(duration_ms: int) -> None:
            nonlocal current_level
            if duration_ms <= 0:
                pulses.append(TapePulse(1, 0))
                current_level = 1
                return
            # 3.5 MHz Spectrum clock
            pulses.append(TapePulse(max(1, duration_ms * 3500), 0))
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

            raise ValueError(f"bloque TZX no soportado aún para Spectrum: 0x{block_id:02X}")

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
