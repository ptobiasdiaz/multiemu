from __future__ import annotations

from collections import deque

import pygame
from frontend.backend import wrap_backend
from frontend.input_events import InputEvent
from frontend.keymap import SPECTRUM_PYGAME_KEYMAP

try:
    import numpy as np
except ImportError:
    np = None


class PygameFrontend:
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

        fb = self.backend.framebuffer
        if fb is None:
            fb = self.backend.render_frame()

        self.src_height = len(fb)
        self.src_width = len(fb[0])

        self.win_width = self.src_width * self.scale
        self.win_height = self.src_height * self.scale

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

        self.keymap = SPECTRUM_PYGAME_KEYMAP

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
            self.screen = pygame.display.set_mode((self.win_width, self.win_height))
            pygame.display.set_caption(self.window_title)
            self.surface = pygame.Surface((self.src_width, self.src_height))

            # Reserva un canal dedicado al audio del emulador
            pygame.mixer.set_num_channels(8)
            self.audio_channel = pygame.mixer.Channel(0)
            self.audio_channel.set_volume(1.0)

            self.running = True

            while self.running:
                self._handle_events()

                self.backend.run_frame()
                self._play_audio()
                self._pump_audio_queue()
                self._draw_framebuffer(self.backend.framebuffer)

                if self.fps_limit > 0:
                    self.clock.tick(self.fps_limit)
        finally:
            pygame.quit()

    def _handle_events(self):
        self.backend.clear_input_state()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

        keys = pygame.key.get_pressed()

        if keys[pygame.K_ESCAPE]:
            self.running = False
            return

        for pg_key, (row, bit) in self.keymap.items():
            if keys[pg_key]:
                self.backend.handle_input_event(
                    InputEvent(
                        kind="key_matrix",
                        control_a=row,
                        control_b=bit,
                        active=True,
                    )
                )

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

    def _draw_framebuffer(self, framebuffer):
        if self.use_surfarray:
            # Pygame surfarray uses (width, height, channels).
            frame_array = np.asarray(framebuffer, dtype=np.uint8).swapaxes(0, 1)
            pygame.surfarray.blit_array(self.surface, frame_array)
        else:
            for y, row in enumerate(framebuffer):
                for x, rgb in enumerate(row):
                    self.surface.set_at((x, y), rgb)

        if self.scale != 1:
            scaled = pygame.transform.scale(self.surface, (self.win_width, self.win_height))
            self.screen.blit(scaled, (0, 0))
        else:
            self.screen.blit(self.surface, (0, 0))

        pygame.display.flip()
