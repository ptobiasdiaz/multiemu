from __future__ import annotations

from multiemu.remote_runtime import RemoteFrontendSession


class _DummyBackend:
    def __init__(self):
        self.framebuffer_rgb24 = bytearray(b"\x00\x00\x00")
        self.frame_width = 1
        self.frame_height = 1
        self.events = []

    def run_frame(self):
        return None

    def get_audio_buffered_samples(self):
        return 0

    def clear_input_state(self):
        return None

    def handle_input_event(self, event):
        self.events.append(event)
        return None


class _DummySession(RemoteFrontendSession):
    def __init__(self, backend, **kwargs):
        super().__init__(backend, **kwargs)
        self.service_calls = 0

    def start_transport(self) -> None:
        return None

    def accept_new_clients(self) -> None:
        return None

    def drain_inputs(self) -> None:
        return None

    def collect_pressed_keys(self) -> set[tuple[int, int]]:
        return set()

    def broadcast_stream_data(self, frame_bytes: bytes, audio_bytes: bytes) -> None:
        self.running = False

    def flush_writes(self) -> None:
        return None

    def remove_disconnected_clients(self) -> None:
        return None

    def service_transport(self, remaining_seconds: float) -> None:
        self.service_calls += 1

    def close_transport(self) -> None:
        return None


def test_remote_frontend_session_accepts_none_fps_limit():
    session = _DummySession(_DummyBackend(), fps_limit=None)
    session.run()
    assert session.service_calls == 0


def test_remote_frontend_session_applies_keyboard_and_joystick_inputs():
    backend = _DummyBackend()
    session = _DummySession(backend)

    session._apply_merged_input_state({(1, 2)}, {0: {0x10}})

    assert [(event.kind, event.control_a, event.control_b) for event in backend.events] == [
        ("key_matrix", 1, 2),
        ("joystick", 0, 0x10),
    ]
