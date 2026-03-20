from __future__ import annotations

from collections import deque

import pygame
from frontend.backend import wrap_backend
from frontend.input_events import InputEvent
from frontend.keymap import get_pygame_keymap

try:
    import numpy as np
except ImportError:
    np = None


class PygameFrontend:
    """Local pygame frontend with event-driven keyboard state tracking."""

    # CPC firmware scans the keyboard from interrupts, not from host events.
    # Short host taps therefore need to be stretched into a few emulator
    # frames or they disappear between firmware scans.
    TAP_HOLD_FRAMES = 5
    QUICK_TAP_MAX_FRAMES = 2
    AUTO_TURBO_FRAME_BATCH = 8

    def __init__(
        self,
        backend,
        *,
        scale: int = 2,
        window_title: str = "MultiEmu",
        fps_limit: int = 50,
        audio_sample_rate: int = 44100,
        audio_chunk_size: int = 512,
    ):
        self.backend = wrap_backend(backend)

        self.scale = scale
        self.window_title = window_title
        self.fps_limit = fps_limit
        self.audio_sample_rate = audio_sample_rate
        self.audio_chunk_size = audio_chunk_size
        self.audio_play_chunk_size = max(audio_chunk_size, 2048)

        packed = getattr(self.backend, "framebuffer_rgb24", None)
        frame_width = getattr(self.backend, "frame_width", None)
        frame_height = getattr(self.backend, "frame_height", None)
        if packed is None:
            packed = self.backend.render_frame()
        self.src_width = frame_width
        self.src_height = frame_height

        self.win_width = self.src_width * self.scale
        self.win_height = self.src_height * self.scale
        self.fullscreen = False

        self.running = False
        self.clock = None
        self.screen = None
        self.surface = None

        self.audio_channel = None
        self.audio_started = False
        self.audio_queue = deque()
        self.audio_prebuffer_chunks = 4
        self.audio_byte_buffer = bytearray()
        self.use_surfarray = np is not None and hasattr(pygame, "surfarray")
        self._configure_audio_profile()

        self.keymap = get_pygame_keymap(getattr(self.backend, "input_keymap_name", None))
        self.tap_hold_frames = getattr(
            self.backend,
            "input_tap_hold_frames",
            self.TAP_HOLD_FRAMES,
        )
        self.quick_tap_max_frames = getattr(
            self.backend,
            "input_quick_tap_max_frames",
            self.QUICK_TAP_MAX_FRAMES,
        )
        self.active_controls: set[tuple[int, int]] = set()
        # Track how long a control has been held while physically down.
        self.active_control_frames: dict[tuple[int, int], int] = {}
        # Keep one short synthetic pulse per quick tap so repeated taps of the
        # same host key are not collapsed into a single emulated press.
        self.tap_pulse_frames: dict[tuple[int, int], int] = {}
        self.pending_tap_counts: dict[tuple[int, int], int] = {}

    def _get_frame_batch_size(self) -> int:
        machine_id = str(getattr(self.backend, "machine_id", ""))
        auto_turbo_enabled = str(getattr(self.backend, "cpc_tape_auto_turbo", False)).lower() not in {"", "0", "false", "no", "off"}
        if auto_turbo_enabled and machine_id.startswith("cpc") and bool(getattr(self.backend, "tape_motor_on", False)):
            return self.AUTO_TURBO_FRAME_BATCH
        return 1

    def _discard_audio(self) -> None:
        available = self.backend.get_audio_buffered_samples()
        if available > 0:
            self.backend.pop_audio_samples(available)
        self.audio_queue.clear()
        self.audio_byte_buffer.clear()
        self.audio_started = False

    def _configure_audio_profile(self) -> None:
        """Tune local buffering to the audio pattern of the active machine."""

        machine_id = str(getattr(self.backend, "machine_id", ""))

        if machine_id.startswith("cpc"):
            self.audio_prebuffer_chunks = 1
            self.audio_play_chunk_size = max(1024, self.audio_chunk_size)
            return

        self.audio_prebuffer_chunks = 4
        self.audio_play_chunk_size = max(2048, self.audio_chunk_size)

    def run(self):
        pygame.mixer.pre_init(
            frequency=self.audio_sample_rate,
            size=-16,
            channels=1,
            buffer=self.audio_play_chunk_size,
        )
        pygame.init()

        try:
            self.clock = pygame.time.Clock()
            self._apply_display_mode()
            pygame.display.set_caption(self.window_title)
            self.surface = pygame.Surface((self.src_width, self.src_height))

            # Reserva un canal dedicado al audio del emulador
            pygame.mixer.set_num_channels(8)
            self.audio_channel = pygame.mixer.Channel(0)
            self.audio_channel.set_volume(1.0)

            self.running = True

            while self.running:
                self._handle_events()
                frame_batch_size = self._get_frame_batch_size()
                for _ in range(frame_batch_size):
                    self.backend.run_frame()
                if frame_batch_size > 1:
                    self._discard_audio()
                else:
                    self._play_audio()
                self._pump_audio_queue()
                self._draw_framebuffer(self.backend.framebuffer_rgb24)

                if self.fps_limit > 0 and frame_batch_size == 1:
                    self.clock.tick(self.fps_limit)
        finally:
            pygame.quit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.KEYDOWN:
                if self._is_fullscreen_toggle_event(event):
                    self._toggle_fullscreen()
                    continue
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    return
                if event.key == pygame.K_F1:
                    self.backend.toggle_tape_play_pause()
                    continue
                control = self.keymap.get(event.key)
                if control is not None:
                    self.active_controls.add(control)
                    self.active_control_frames.setdefault(control, 0)
            elif event.type == pygame.KEYUP:
                control = self.keymap.get(event.key)
                if control is not None:
                    held_frames = self.active_control_frames.get(control, 0)
                    if held_frames <= self.quick_tap_max_frames:
                        if control in self.tap_pulse_frames:
                            self.pending_tap_counts[control] = self.pending_tap_counts.get(control, 0) + 1
                        else:
                            self.tap_pulse_frames[control] = self.tap_hold_frames
                    self.active_controls.discard(control)
                    self.active_control_frames.pop(control, None)

        self.backend.clear_input_state()
        controls_to_apply = set(self.active_controls)
        controls_to_apply.update(self.tap_pulse_frames)

        for row, bit in controls_to_apply:
            self.backend.handle_input_event(
                InputEvent(
                    kind="key_matrix",
                    control_a=row,
                    control_b=bit,
                    active=True,
                )
            )

        for control in list(self.active_controls):
            self.active_control_frames[control] = self.active_control_frames.get(control, 0) + 1

        expired = []
        for control, frames_left in self.tap_pulse_frames.items():
            if frames_left <= 1:
                expired.append(control)
            else:
                self.tap_pulse_frames[control] = frames_left - 1

        for control in expired:
            queued = self.pending_tap_counts.get(control, 0)
            if queued > 0:
                self.pending_tap_counts[control] = queued - 1
                self.tap_pulse_frames[control] = self.tap_hold_frames
            else:
                self.tap_pulse_frames.pop(control, None)
                self.pending_tap_counts.pop(control, None)

    def _is_fullscreen_toggle_event(self, event) -> bool:
        mods = getattr(event, "mod", 0)
        return event.key == pygame.K_RETURN and bool(mods & pygame.KMOD_ALT)

    def _toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self._apply_display_mode()

    def _apply_display_mode(self) -> None:
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        size = (0, 0) if self.fullscreen else (self.win_width, self.win_height)
        self.screen = pygame.display.set_mode(size, flags)

    def _play_audio(self):
        available = self.backend.get_audio_buffered_samples()
        if available > 0:
            chunk = self.backend.pop_audio_samples(available)
            self.audio_byte_buffer.extend(chunk.tobytes())

        chunk_bytes = self.audio_play_chunk_size * 2
        while len(self.audio_byte_buffer) >= chunk_bytes:
            chunk = bytes(self.audio_byte_buffer[:chunk_bytes])
            del self.audio_byte_buffer[:chunk_bytes]
            self.audio_queue.append(pygame.mixer.Sound(buffer=chunk))

        self._pump_audio_queue()

    def _pump_audio_queue(self):
        if self.audio_channel is None or not self.audio_queue:
            return

        if not self.audio_started:
            if len(self.audio_queue) < self.audio_prebuffer_chunks:
                return
            self.audio_channel.play(self.audio_queue.popleft())
            self.audio_started = True

        if not self.audio_channel.get_busy():
            if self.audio_queue:
                self.audio_channel.play(self.audio_queue.popleft())
            return

        while self.audio_channel.get_queue() is None and self.audio_queue:
            try:
                self.audio_channel.queue(self.audio_queue.popleft())
            except pygame.error:
                break

    def _draw_framebuffer(self, packed):
        if self.use_surfarray:
            frame_array = np.frombuffer(packed, dtype=np.uint8).reshape(
                self.src_height,
                self.src_width,
                3,
            ).swapaxes(0, 1)
            pygame.surfarray.blit_array(self.surface, frame_array)
        else:
            frame_surface = pygame.image.frombuffer(
                packed,
                (self.src_width, self.src_height),
                "RGB",
            )
            self.surface.blit(frame_surface, (0, 0))

        target_width, target_height = self.screen.get_size()
        if target_width != self.src_width or target_height != self.src_height:
            scaled = pygame.transform.scale(self.surface, (target_width, target_height))
            self.screen.blit(scaled, (0, 0))
        else:
            self.screen.blit(self.surface, (0, 0))

        pygame.display.flip()
