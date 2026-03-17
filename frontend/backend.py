from __future__ import annotations

from typing import Protocol


class FrontendBackend(Protocol):
    framebuffer: object

    def render_frame(self):
        ...

    def run_frame(self):
        ...

    def clear_input_state(self):
        ...

    def handle_input_event(self, event):
        ...

    def get_audio_buffered_samples(self) -> int:
        ...

    def pop_audio_samples(self, count: int):
        ...


class LocalMachineBackend:
    __frontend_backend__ = True

    def __init__(self, machine):
        self.machine = machine

    @property
    def frame_counter(self):
        return self.machine.frame_counter

    @property
    def framebuffer(self):
        return self.machine.framebuffer

    def render_frame(self):
        return self.machine.render_frame()

    def run_frame(self):
        return self.machine.run_frame()

    def clear_input_state(self):
        self.machine.clear_input_state()

    def handle_input_event(self, event):
        self.machine.handle_input_event(event)

    def get_audio_buffered_samples(self) -> int:
        return self.machine.get_audio_buffered_samples()

    def pop_audio_samples(self, count: int):
        return self.machine.pop_audio_samples(count)


def wrap_backend(backend):
    if getattr(backend, "__frontend_backend__", False):
        return backend
    return LocalMachineBackend(backend)
