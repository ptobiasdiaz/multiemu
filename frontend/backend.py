from __future__ import annotations

import os
from typing import Protocol


class FrontendBackend(Protocol):
    framebuffer_rgb24: object

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
    def machine_id(self):
        return getattr(self.machine, "machine_id", self.machine.__class__.__name__.lower())

    @property
    def framebuffer_rgb24(self):
        return getattr(self.machine, "framebuffer_rgb24", None)

    @property
    def frame_width(self):
        return getattr(self.machine, "frame_width", None)

    @property
    def frame_height(self):
        return getattr(self.machine, "frame_height", None)

    @property
    def tape_motor_on(self):
        cassette = getattr(self.machine, "cassette", None)
        return bool(cassette is not None and getattr(cassette, "motor_on", False))

    @property
    def tape_present(self):
        return getattr(self.machine, "cassette", None) is not None

    @property
    def tape_playing(self):
        cassette = getattr(self.machine, "cassette", None)
        return bool(cassette is not None and getattr(cassette, "playing", False))

    @property
    def cpc_tape_auto_turbo(self):
        return os.environ.get("MULTIEMU_CPC_TAPE_AUTO_TURBO", "0")

    @property
    def input_keymap_name(self):
        return getattr(self.machine, "input_keymap_name", None)

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

    def toggle_tape_play_pause(self):
        toggle = getattr(self.machine, "toggle_tape_play_pause", None)
        if toggle is None:
            return False
        return bool(toggle())


def wrap_backend(backend):
    if getattr(backend, "__frontend_backend__", False):
        return backend
    return LocalMachineBackend(backend)
