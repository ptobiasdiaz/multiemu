from __future__ import annotations

import os
from frontend.backend import LocalMachineBackend
from frontend.pygame_frontend import PygameFrontend
import pygame


class _FakeMachine:
    def __init__(self, machine_id: str, *, tape_motor_on: bool = False, audio_samples: int = 0):
        self.machine_id = machine_id
        self.frame_counter = 0
        self.frame_width = 160
        self.frame_height = 144
        self.framebuffer_rgb24 = bytes(self.frame_width * self.frame_height * 3)
        self.input_keymap_name = None
        self.cassette = type("Cassette", (), {"motor_on": tape_motor_on, "playing": False})()
        self._audio_samples = audio_samples
        self.popped_audio = 0
        self.tape_toggles = 0

    def render_frame(self):
        return self.framebuffer_rgb24

    def run_frame(self):
        return 0

    def clear_input_state(self):
        return None

    def handle_input_event(self, event):
        return None

    def get_audio_buffered_samples(self) -> int:
        return self._audio_samples

    def pop_audio_samples(self, count: int):
        self.popped_audio += count
        self._audio_samples = max(0, self._audio_samples - count)
        return array("h", [0] * count)

    def toggle_tape_play_pause(self):
        self.tape_toggles += 1
        self.cassette.playing = not self.cassette.playing
        return self.cassette.playing


from array import array


def test_local_machine_backend_exposes_machine_id():
    backend = LocalMachineBackend(_FakeMachine("cpc464"))

    assert backend.machine_id == "cpc464"


def test_pygame_frontend_uses_cpc_audio_profile():
    frontend = PygameFrontend(_FakeMachine("cpc464"))

    assert frontend.audio_prebuffer_chunks == 1
    assert frontend.audio_play_chunk_size == 1024


def test_pygame_frontend_keeps_default_audio_profile_for_other_machines():
    frontend = PygameFrontend(_FakeMachine("spectrum48k"))

    assert frontend.audio_prebuffer_chunks == 4
    assert frontend.audio_play_chunk_size == 2048


def test_local_machine_backend_exposes_cassette_motor_state():
    backend = LocalMachineBackend(_FakeMachine("cpc464", tape_motor_on=True))

    assert backend.tape_motor_on is True


def test_local_machine_backend_can_toggle_tape_play_pause():
    backend = LocalMachineBackend(_FakeMachine("spectrum48k"))

    assert backend.tape_present is True
    assert backend.tape_playing is False
    assert backend.toggle_tape_play_pause() is True
    assert backend.tape_playing is True


def test_pygame_frontend_keeps_cpc_tape_auto_turbo_disabled_by_default():
    frontend = PygameFrontend(_FakeMachine("cpc464", tape_motor_on=True))

    assert frontend._get_frame_batch_size() == 1


def test_pygame_frontend_uses_auto_turbo_while_cpc_tape_motor_is_on_when_enabled():
    old = os.environ.get("MULTIEMU_CPC_TAPE_AUTO_TURBO")
    os.environ["MULTIEMU_CPC_TAPE_AUTO_TURBO"] = "1"
    try:
        frontend = PygameFrontend(_FakeMachine("cpc464", tape_motor_on=True))
        assert frontend._get_frame_batch_size() == frontend.AUTO_TURBO_FRAME_BATCH
    finally:
        if old is None:
            os.environ.pop("MULTIEMU_CPC_TAPE_AUTO_TURBO", None)
        else:
            os.environ["MULTIEMU_CPC_TAPE_AUTO_TURBO"] = old


def test_pygame_frontend_discards_audio_during_tape_turbo():
    machine = _FakeMachine("cpc464", tape_motor_on=True, audio_samples=32)
    frontend = PygameFrontend(machine)

    frontend.audio_queue.append(object())
    frontend.audio_byte_buffer.extend(b"1234")
    frontend.audio_started = True
    frontend._discard_audio()

    assert machine.popped_audio == 32
    assert not frontend.audio_queue
    assert frontend.audio_byte_buffer == bytearray()
    assert frontend.audio_started is False


def test_pygame_frontend_f1_toggles_tape_play_pause(monkeypatch):
    machine = _FakeMachine("spectrum48k")
    frontend = PygameFrontend(machine)

    class _Event:
        type = 768  # pygame.KEYDOWN
        key = 1073741882  # pygame.K_F1

    monkeypatch.setattr("pygame.event.get", lambda: [_Event()])
    frontend._handle_events()

    assert machine.tape_toggles == 1
    assert machine.cassette.playing is True


def test_pygame_frontend_alt_enter_toggles_fullscreen(monkeypatch):
    machine = _FakeMachine("spectrum48k")
    frontend = PygameFrontend(machine)
    calls = []

    class _Screen:
        def __init__(self, size):
            self._size = size

        def get_size(self):
            return self._size

        def blit(self, *_args, **_kwargs):
            return None

    def fake_set_mode(size, flags=0):
        calls.append((size, flags))
        if flags & pygame.FULLSCREEN:
            return _Screen((1920, 1080))
        return _Screen(size)

    monkeypatch.setattr("pygame.display.set_mode", fake_set_mode)
    frontend._apply_display_mode()

    class _Event:
        type = pygame.KEYDOWN
        key = pygame.K_RETURN
        mod = pygame.KMOD_ALT

    monkeypatch.setattr("pygame.event.get", lambda: [_Event()])
    frontend._handle_events()

    assert frontend.fullscreen is True
    assert calls[0] == ((frontend.win_width, frontend.win_height), 0)
    assert calls[1] == ((0, 0), pygame.FULLSCREEN)
