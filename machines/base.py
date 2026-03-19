from __future__ import annotations

from abc import ABC, abstractmethod
from array import array
from typing import Protocol

from audio import AudioRingBuffer


class Bus(Protocol):
    pass


class CPU(Protocol):
    def reset(self):
        ...

    def step(self) -> int:
        ...

    def run_cycles(self, cycles: int) -> int:
        ...

    def snapshot(self) -> dict:
        ...


class BaseMachine(ABC):
    def __init__(self, *, bus: Bus, cpu: CPU, audio_sample_rate: int = 44100):
        self.bus = bus
        self.cpu = cpu

        self.tstates = 0
        self.frame_counter = 0
        self.frame_tstates = 0

        self.framebuffer_rgb24 = None
        self.audio_samples = array("h")
        self.audio_ring = AudioRingBuffer(audio_sample_rate // 2)

    def reset(self):
        self.cpu.reset()
        self.tstates = 0
        self.frame_counter = 0
        self.frame_tstates = 0
        self.audio_samples = array("h")
        self.audio_ring.clear()

    def run_cycles(self, cycles: int) -> int:
        used = self.cpu.run_cycles(cycles)
        self.tstates += used
        self.frame_tstates += used
        self._run_devices_until(self.frame_tstates)
        return used

    def get_audio_samples(self):
        return self.audio_samples

    def get_audio_buffered_samples(self) -> int:
        return self.audio_ring.available()

    def pop_audio_samples(self, count: int):
        return self.audio_ring.read(count)

    def clear_input_state(self):
        pass

    def handle_input_event(self, event):
        raise ValueError(f"input no soportado: {event!r}")

    @abstractmethod
    def run_frame(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def render_frame(self):
        raise NotImplementedError

    @abstractmethod
    def _run_devices_until(self, tstates: int):
        raise NotImplementedError
