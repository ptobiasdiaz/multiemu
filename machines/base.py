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

    def read_state(self) -> dict:
        ...

    def write_state(self, state: dict) -> None:
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

    def _debug_device(self, device_id: str, obj, kind: str, *, label: str | None = None) -> dict:
        return {
            "id": device_id,
            "obj": obj,
            "kind": kind,
            "label": label or device_id,
            "writable": bool(obj is not None and hasattr(obj, "write_state")),
        }

    def debug_devices(self) -> list[dict]:
        return [
            self._debug_device("machine", self, "machine", label="Machine"),
            self._debug_device("cpu", self.cpu, "cpu", label="CPU"),
            self._debug_device("bus", self.bus, "bus", label="Bus"),
        ]

    @abstractmethod
    def run_frame(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def render_frame(self):
        raise NotImplementedError

    @abstractmethod
    def _run_devices_until(self, tstates: int):
        raise NotImplementedError

    def read_state(self) -> dict:
        state = {
            "__meta__": {
                "type": type(self).__name__,
                "module": type(self).__module__,
            },
            "tstates": self.tstates,
            "frame_counter": self.frame_counter,
            "frame_tstates": self.frame_tstates,
        }
        if hasattr(self.cpu, "read_state"):
            state["cpu"] = self.cpu.read_state()
        if hasattr(self.bus, "read_state"):
            state["bus"] = self.bus.read_state()
        return state

    def write_state(self, state: dict) -> None:
        if "tstates" in state:
            self.tstates = int(state["tstates"])
        if "frame_counter" in state:
            self.frame_counter = int(state["frame_counter"])
        if "frame_tstates" in state:
            self.frame_tstates = int(state["frame_tstates"])
        if "cpu" in state and hasattr(self.cpu, "write_state"):
            self.cpu.write_state(state["cpu"])
        if "bus" in state and hasattr(self.bus, "write_state"):
            self.bus.write_state(state["bus"])
