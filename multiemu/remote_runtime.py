from __future__ import annotations

"""Shared runtime loop for remote/fronted-backed emulation servers.

This layer owns the emulation cadence and input merge policy while transport
implementations provide connection management and payload delivery.
"""

import time
from abc import ABC, abstractmethod

from frontend.backend import wrap_backend
from frontend.input_events import InputEvent


class RemoteFrontendSession(ABC):
    """Transport-agnostic emulation session used by remote server frontends."""

    def __init__(
        self,
        backend,
        *,
        fps_limit: int = 50,
        audio_sample_rate: int = 44100,
        audio_chunk_size: int = 512,
    ):
        self.backend = wrap_backend(backend)
        self.fps_limit = fps_limit
        self.audio_sample_rate = audio_sample_rate
        self.audio_chunk_size = audio_chunk_size
        self.running = False

        packed = getattr(self.backend, "framebuffer_rgb24", None)
        frame_width = getattr(self.backend, "frame_width", None)
        frame_height = getattr(self.backend, "frame_height", None)

        if packed is None:
            packed = self.backend.render_frame()
        self.frame_width = frame_width
        self.frame_height = frame_height

    def run(self):
        """Drive the emulation loop and delegate transport hooks to subclasses."""

        self.start_transport()
        self.running = True

        try:
            while self.running:
                frame_start = time.monotonic()

                self.accept_new_clients()
                self.drain_inputs()
                self._apply_merged_input_state(self.collect_pressed_keys())

                self.backend.run_frame()
                frame_bytes = self.encode_framebuffer(getattr(self.backend, "framebuffer_rgb24", None))
                audio_bytes = self.pop_audio_bytes()
                self.broadcast_stream_data(frame_bytes, audio_bytes)
                self.flush_writes()
                self.remove_disconnected_clients()

                if self.fps_limit > 0:
                    elapsed = time.monotonic() - frame_start
                    frame_budget = 1.0 / self.fps_limit
                    if elapsed < frame_budget:
                        self.service_transport(frame_budget - elapsed)
        finally:
            self.running = False
            self.close_transport()

    def _apply_merged_input_state(self, pressed_keys: set[tuple[int, int]]):
        """Merge keyboard state once per frame for deterministic shared input."""

        self.backend.clear_input_state()
        for row, bit in pressed_keys:
            self.backend.handle_input_event(
                InputEvent(
                    kind="key_matrix",
                    control_a=row,
                    control_b=bit,
                    active=True,
                )
            )

    def pop_audio_bytes(self) -> bytes:
        """Drain queued audio from the backend in the wire format used today."""

        available = self.backend.get_audio_buffered_samples()
        if available <= 0:
            return b""
        return self.backend.pop_audio_samples(available).tobytes()

    def encode_framebuffer(self, framebuffer) -> bytes:
        """Encode the RGB framebuffer as contiguous rgb24 bytes."""

        if framebuffer is None:
            raise ValueError("backend no expone framebuffer_rgb24")
        return bytes(framebuffer)

    @abstractmethod
    def start_transport(self) -> None:
        """Initialize the transport before entering the main loop."""

    @abstractmethod
    def accept_new_clients(self) -> None:
        """Accept any pending new clients."""

    @abstractmethod
    def drain_inputs(self) -> None:
        """Consume inbound transport messages and update client state."""

    @abstractmethod
    def collect_pressed_keys(self) -> set[tuple[int, int]]:
        """Return the merged pressed-key state visible for the next frame."""

    @abstractmethod
    def broadcast_stream_data(self, frame_bytes: bytes, audio_bytes: bytes) -> None:
        """Queue the latest emulation outputs for interested clients."""

    @abstractmethod
    def flush_writes(self) -> None:
        """Advance any pending transport writes."""

    @abstractmethod
    def remove_disconnected_clients(self) -> None:
        """Drop sessions that are no longer valid."""

    @abstractmethod
    def service_transport(self, remaining_seconds: float) -> None:
        """Use any spare frame time for transport maintenance."""

    @abstractmethod
    def close_transport(self) -> None:
        """Tear down the transport and any connected clients."""
