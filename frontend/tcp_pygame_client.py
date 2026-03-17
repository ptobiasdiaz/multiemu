from __future__ import annotations
"""Pygame client for the TCP frontend protocol.

The client connects to a remote emulator instance, sends ``hello``, receives
``welcome``, then loops on ``frame`` messages carrying raw ``rgb24`` video and
``s16le`` mono audio. Keyboard state is sent as ``input_state`` for the shared
``keyboard_0`` device, matching the server-side model of per-client input
state.
"""

import json
import socket
from collections import deque

import pygame
from frontend.keymap import SPECTRUM_PYGAME_KEYMAP

try:
    import numpy as np
except ImportError:
    np = None


class TcpPygameClient:
    """Render a remote emulator stream locally with pygame."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        scale: int = 2,
        window_title: str = "MultiEmu TCP Client",
    ):
        self.host = host
        self.port = port
        self.scale = scale
        self.window_title = window_title

        self.running = False
        self.sock = None
        self.screen = None
        self.surface = None
        self.clock = None

        self.src_width = 0
        self.src_height = 0
        self.win_width = 0
        self.win_height = 0
        self.fps_limit = 50
        self.audio_sample_rate = 44100
        self.audio_chunk_size = 512
        self.audio_play_chunk_size = 2048

        self.audio_channel = None
        self.audio_started = False
        self.audio_queue = deque()
        self.audio_prebuffer_chunks = 4
        self.audio_max_queue_chunks = 12
        self.audio_byte_buffer = bytearray()
        self.use_surfarray = np is not None and hasattr(pygame, "surfarray")
        self.keymap = SPECTRUM_PYGAME_KEYMAP

    def run(self):
        with socket.create_connection((self.host, self.port)) as sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock = sock
            self._send_json(
                {
                    "type": "hello",
                    "protocol": 1,
                    "client_name": "pygame-client",
                    "capabilities": {
                        "video": ["rgb24"],
                        "audio": ["s16le"],
                        "input": True,
                    },
                }
            )
            welcome = self._recv_json()
            self._configure_from_welcome(welcome)

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

                pygame.mixer.set_num_channels(8)
                self.audio_channel = pygame.mixer.Channel(0)
                self.audio_channel.set_volume(1.0)

                self.running = True

                while self.running:
                    self._handle_local_events()
                    self._send_input_state()

                    message = self._recv_json()
                    if message.get("type") == "error":
                        raise ValueError(
                            f"error del servidor: {message.get('code')}: {message.get('detail')}"
                        )
                    if message.get("type") != "frame":
                        raise ValueError(f"mensaje TCP inesperado: {message!r}")

                    frame_bytes = self._recv_exact(int(message["video_bytes"]))
                    audio_bytes = self._recv_exact(int(message["audio_bytes"]))
                    self._draw_framebuffer(frame_bytes)
                    self._queue_audio(audio_bytes)
                    self._pump_audio_queue()
            finally:
                if self.sock is not None:
                    try:
                        self._send_json({"type": "shutdown"})
                    except OSError:
                        pass
                pygame.quit()

    def _configure_from_welcome(self, welcome: dict):
        if welcome.get("type") != "welcome":
            raise ValueError(f"handshake TCP inesperado: {welcome!r}")

        video = welcome.get("video", {})
        audio = welcome.get("audio", {})

        if video.get("pixel_format") != "rgb24":
            raise ValueError(f"pixel_format no soportado: {video.get('pixel_format')!r}")

        if audio.get("format") != "s16le":
            raise ValueError(f"audio_format no soportado: {audio.get('format')!r}")

        self.src_width = int(video["width"])
        self.src_height = int(video["height"])
        self.win_width = self.src_width * self.scale
        self.win_height = self.src_height * self.scale
        self.fps_limit = int(video.get("fps", self.fps_limit))
        self.audio_sample_rate = int(audio.get("sample_rate", self.audio_sample_rate))

    def _handle_local_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return

        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            self.running = False

    def _send_input_state(self):
        if not self.running:
            return

        keys = pygame.key.get_pressed()
        pressed = []

        for pg_key, (row, bit) in self.keymap.items():
            if keys[pg_key]:
                pressed.append(
                    {
                        "control_a": row,
                        "control_b": bit,
                    }
                )

        self._send_json(
            {
                "type": "input_state",
                "device_id": "keyboard_0",
                "pressed": pressed,
            }
        )

    def _queue_audio(self, audio_bytes: bytes):
        if not audio_bytes:
            return

        self.audio_byte_buffer.extend(audio_bytes)
        chunk_bytes = self.audio_play_chunk_size * 2

        # Match the local frontend: feed the mixer longer, stable chunks rather
        # than a stream of tiny sounds that tends to produce clicks.
        # FIXME: TCP audio still shares framing cadence with video delivery.
        # Split audio into its own stream/message path to reduce jitter further.
        while len(self.audio_byte_buffer) >= chunk_bytes:
            chunk = bytes(self.audio_byte_buffer[:chunk_bytes])
            del self.audio_byte_buffer[:chunk_bytes]
            self.audio_queue.append(pygame.mixer.Sound(buffer=chunk))

        while len(self.audio_queue) > self.audio_max_queue_chunks:
            self.audio_queue.popleft()

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

    def _draw_framebuffer(self, frame_bytes: bytes):
        if self.use_surfarray:
            frame_array = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(
                (self.src_height, self.src_width, 3)
            ).swapaxes(0, 1)
            pygame.surfarray.blit_array(self.surface, frame_array)
        else:
            offset = 0
            for y in range(self.src_height):
                for x in range(self.src_width):
                    rgb = (
                        frame_bytes[offset],
                        frame_bytes[offset + 1],
                        frame_bytes[offset + 2],
                    )
                    self.surface.set_at((x, y), rgb)
                    offset += 3

        if self.scale != 1:
            scaled = pygame.transform.scale(self.surface, (self.win_width, self.win_height))
            self.screen.blit(scaled, (0, 0))
        else:
            self.screen.blit(self.surface, (0, 0))

        pygame.display.flip()

    def _recv_json(self) -> dict:
        line = self._recv_line()
        return json.loads(line.decode("utf-8"))

    def _recv_line(self) -> bytes:
        data = bytearray()

        while True:
            chunk = self._recv_exact(1)
            if chunk == b"\n":
                return bytes(data)
            data.extend(chunk)

    def _recv_exact(self, size: int) -> bytes:
        data = bytearray()

        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError("conexión TCP cerrada")
            data.extend(chunk)

        return bytes(data)

    def _send_json(self, payload: dict):
        self.sock.sendall(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
