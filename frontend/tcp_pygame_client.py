from __future__ import annotations
"""Pygame client for the TCP frontend protocol.

The client connects to a remote emulator instance, sends ``hello``, receives
``welcome``, then loops on ``frame`` messages carrying raw ``rgb24`` video and
``s16le`` mono audio. Keyboard state is sent as ``input_state`` for the shared
``keyboard_0`` device, matching the server-side model of per-client input
state. The server also advertises which local keymap should be used so the
same client can talk to different machine families without hardcoding
Spectrum-only assumptions.
"""

import json
import socket
from collections import deque

import pygame
from frontend.keymap import (
    load_pygame_input_maps,
    resolve_pygame_key_controls,
)

try:
    import numpy as np
except ImportError:
    np = None


class TcpPygameClient:
    """Render a remote emulator stream locally with pygame."""

    # Mirror the local frontend so short remote taps survive firmware scans.
    TAP_HOLD_FRAMES = 5
    QUICK_TAP_MAX_FRAMES = 2
    GAMEPAD_AXIS_THRESHOLD = 0.5

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        scale: int = 2,
        window_title: str = "MultiEmu TCP Client",
        joystick_player: int = 1,
        keymap_file: str | None = None,
    ):
        self.host = host
        self.port = port
        self.scale = scale
        self.window_title = window_title
        self.joystick_player = max(1, int(joystick_player))
        self.keymap_file = keymap_file

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
        self.audio_channels = 1
        self.audio_chunk_size = 512
        self.audio_play_chunk_size = 2048

        self.audio_channel = None
        self.audio_started = False
        self.audio_queue = deque()
        # Default to the more stable Spectrum-like profile until the server
        # tells us which machine family is behind the transport.
        self.audio_prebuffer_chunks = 4
        self.audio_max_queue_chunks = 12
        self.audio_byte_buffer = bytearray()
        self.use_surfarray = np is not None and hasattr(pygame, "surfarray")
        self.keymap_name = None
        self.input_maps = load_pygame_input_maps(None)
        self.keymap = self.input_maps.keymap
        self.combo_keymap = self.input_maps.combo_keymap
        self.unicode_combo_keymap = self.input_maps.unicode_combo_keymap
        self.gamepad_map = self.input_maps.gamepad_map
        self.joystick_device_ids: list[str] = []
        self.active_keyboard_controls: set[tuple[int, int]] = set()
        self._keyboard_key_bindings: dict[int, tuple[tuple[int, int], ...]] = {}
        self.active_gamepad_targets: set[tuple[str, int, int]] = set()
        self.active_control_frames: dict[tuple[int, int], int] = {}
        self.tap_pulse_frames: dict[tuple[int, int], int] = {}
        self.pending_tap_counts: dict[tuple[int, int], int] = {}
        self.gamepads: dict[int, object] = {}
        self._gamepad_assignments: dict[int, int] = {}
        self._gamepad_sources: dict[tuple[int, str], tuple[str, int, int]] = {}

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
                channels=self.audio_channels,
                buffer=self.audio_play_chunk_size,
            )
            pygame.init()

            try:
                self.clock = pygame.time.Clock()
                self.screen = pygame.display.set_mode((self.win_width, self.win_height))
                pygame.display.set_caption(self.window_title)
                self.surface = pygame.Surface((self.src_width, self.src_height))
                self._refresh_gamepads()

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
        fps_value = video.get("fps", self.fps_limit)
        if fps_value is not None:
            self.fps_limit = int(fps_value)
        self.audio_sample_rate = int(audio.get("sample_rate", self.audio_sample_rate))
        self.audio_channels = max(1, int(audio.get("channels", self.audio_channels)))
        self.audio_chunk_size = int(audio.get("chunk_samples", self.audio_chunk_size))
        self.audio_play_chunk_size = max(2048, self.audio_chunk_size)
        frontend = welcome.get("frontend", {})
        self.keymap_name = frontend.get("keymap")
        self.input_maps = load_pygame_input_maps(
            self.keymap_name,
            gamepad_name=frontend.get("gamepad_map") or self.keymap_name,
            keymap_file=self.keymap_file,
            keymap_spec=frontend.get("keymap_spec"),
        )
        self.keymap = self.input_maps.keymap
        self.combo_keymap = self.input_maps.combo_keymap
        self.unicode_combo_keymap = self.input_maps.unicode_combo_keymap
        self.gamepad_map = self.input_maps.gamepad_map
        self.joystick_device_ids = [
            str(device["device_id"])
            for device in welcome.get("input_devices", [])
            if device.get("device_type") == "joystick"
        ]
        self._configure_audio_profile(welcome)

    def _configure_audio_profile(self, welcome: dict) -> None:
        """Tune client-side buffering to the remote machine audio pattern.

        Spectrum benefits from the more conservative buffering already used by
        the local frontend because its continuous audio exposes transport
        jitter quickly. CPC firmware, on the other hand, often emits short
        beeps, so it needs a shallower startup queue to avoid swallowing them.
        """

        machine = welcome.get("machine", {})
        machine_id = str(machine.get("id", ""))

        if machine_id.startswith("cpc"):
            self.audio_prebuffer_chunks = 1
            self.audio_max_queue_chunks = 8
            self.audio_play_chunk_size = max(1024, self.audio_chunk_size)
            return

        if machine_id.startswith("vic20"):
            self.audio_prebuffer_chunks = 4
            self.audio_max_queue_chunks = 12
            self.audio_play_chunk_size = max(2048, self.audio_chunk_size)
            return

        if machine_id.startswith("mastersystem"):
            self.audio_prebuffer_chunks = 2
            self.audio_max_queue_chunks = 8
            self.audio_play_chunk_size = max(1024, self.audio_chunk_size)
            return

        self.audio_prebuffer_chunks = 4
        self.audio_max_queue_chunks = 12
        self.audio_play_chunk_size = max(2048, self.audio_chunk_size)

    def _handle_local_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    return
                controls = resolve_pygame_key_controls(
                    self.keymap, self.combo_keymap, self.unicode_combo_keymap, event
                )
                if controls:
                    if self._uses_unicode_combo(event):
                        self._suppress_host_shift_bindings()
                    self._keyboard_key_bindings[event.key] = controls
                    for control in controls:
                        self.active_keyboard_controls.add(control)
                        self.active_control_frames.setdefault(control, 0)
            elif event.type == pygame.KEYUP:
                controls = self._keyboard_key_bindings.pop(event.key, None)
                if controls is None:
                    controls = resolve_pygame_key_controls(
                        self.keymap, self.combo_keymap, self.unicode_combo_keymap, event
                    )
                for control in controls:
                    held_frames = self.active_control_frames.get(control, 0)
                    if held_frames <= self.QUICK_TAP_MAX_FRAMES:
                        if control in self.tap_pulse_frames:
                            self.pending_tap_counts[control] = self.pending_tap_counts.get(control, 0) + 1
                        else:
                            self.tap_pulse_frames[control] = self.TAP_HOLD_FRAMES
                    self.active_keyboard_controls.discard(control)
                    self.active_control_frames.pop(control, None)
            elif event.type == pygame.JOYDEVICEADDED:
                self._open_gamepad(event.device_index)
            elif event.type == pygame.JOYDEVICEREMOVED:
                self._close_gamepad(event.instance_id)
            elif event.type == pygame.JOYBUTTONDOWN:
                self._set_gamepad_binding(event.instance_id, self._gamepad_button_name(event.button), True)
            elif event.type == pygame.JOYBUTTONUP:
                self._set_gamepad_binding(event.instance_id, self._gamepad_button_name(event.button), False)
            elif event.type == pygame.JOYHATMOTION:
                self._set_gamepad_hat(event.instance_id, event.value)
            elif event.type == pygame.JOYAXISMOTION:
                self._set_gamepad_axis(event.instance_id, event.axis, event.value)

    def _send_input_state(self):
        if not self.running:
            return

        pressed = []
        joystick_pressed: dict[int, list[dict]] = {}
        controls_to_send = set(self.active_keyboard_controls)
        controls_to_send.update(self.tap_pulse_frames)

        for row, bit in controls_to_send:
            pressed.append(
                {
                    "control_a": row,
                    "control_b": bit,
                }
            )

        for kind, control_a, control_b in self.active_gamepad_targets:
            if kind == "key_matrix":
                pressed.append({"control_a": control_a, "control_b": control_b})
                continue
            if kind == "joystick":
                joystick_pressed.setdefault(control_a, []).append(
                    {"control_a": control_a, "control_b": control_b}
                )

        for control in list(self.active_keyboard_controls):
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
                self.tap_pulse_frames[control] = self.TAP_HOLD_FRAMES
            else:
                self.tap_pulse_frames.pop(control, None)
                self.pending_tap_counts.pop(control, None)

    def _uses_unicode_combo(self, event) -> bool:
        text = getattr(event, "unicode", "") or ""
        return bool(text and text in self.unicode_combo_keymap)

    def _suppress_host_shift_bindings(self) -> None:
        for shift_key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
            controls = self._keyboard_key_bindings.pop(shift_key, None)
            if not controls:
                continue
            for control in controls:
                self.active_keyboard_controls.discard(control)
                self.active_control_frames.pop(control, None)

        self._send_json(
            {
                "type": "input_state",
                "device_id": "keyboard_0",
                "pressed": pressed,
            }
        )
        for joystick_index, device_id in enumerate(self.joystick_device_ids):
            self._send_json(
                {
                    "type": "input_state",
                    "device_id": device_id,
                    "pressed": joystick_pressed.get(joystick_index, []),
                }
            )

    def _refresh_gamepads(self) -> None:
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        for device_index in range(pygame.joystick.get_count()):
            self._open_gamepad(device_index)

    def _open_gamepad(self, device_index: int) -> None:
        if not self.gamepad_map:
            return
        joystick = pygame.joystick.Joystick(device_index)
        joystick.init()
        instance_id = joystick.get_instance_id()
        self.gamepads[instance_id] = joystick
        assignment = self._next_gamepad_assignment()
        if assignment is not None:
            self._gamepad_assignments[instance_id] = assignment

    def _next_gamepad_assignment(self) -> int | None:
        joystick_count = len(self.joystick_device_ids)
        if joystick_count <= 0:
            return None
        preferred = min(max(0, self.joystick_player - 1), joystick_count - 1)
        candidates = [preferred] + [index for index in range(joystick_count) if index != preferred]
        for candidate in candidates:
            if candidate not in self._gamepad_assignments.values():
                return candidate
        return None

    def _close_gamepad(self, instance_id: int) -> None:
        joystick = self.gamepads.pop(instance_id, None)
        if joystick is not None:
            joystick.quit()
        self._gamepad_assignments.pop(instance_id, None)
        stale = [key for key in self._gamepad_sources if key[0] == instance_id]
        for key in stale:
            target = self._gamepad_sources.pop(key)
            self._discard_gamepad_target_if_unused(target)

    def _gamepad_button_name(self, button: int) -> str | None:
        return {
            0: "button_south",
            1: "button_east",
            6: "button_select",
            7: "button_start",
        }.get(int(button))

    def _set_gamepad_binding(self, instance_id: int, binding_name: str | None, active: bool) -> None:
        if binding_name is None:
            return
        control = self.gamepad_map.get(binding_name)
        if control is None:
            return
        target = self._gamepad_target_for_binding(int(instance_id), control)
        if target is None:
            return
        source_key = (int(instance_id), binding_name)
        if active:
            self._gamepad_sources[source_key] = target
            self.active_gamepad_targets.add(target)
            return
        old_target = self._gamepad_sources.pop(source_key, None)
        if old_target is not None:
            self._discard_gamepad_target_if_unused(old_target)

    def _gamepad_target_for_binding(self, instance_id: int, control) -> tuple[str, int, int] | None:
        if isinstance(control, tuple) and len(control) == 2:
            return ("key_matrix", int(control[0]), int(control[1]))
        if isinstance(control, int):
            joystick_index = self._gamepad_assignments.get(instance_id)
            if joystick_index is None:
                return None
            return ("joystick", joystick_index, int(control))
        return None

    def _discard_gamepad_target_if_unused(self, target: tuple[str, int, int]) -> None:
        if target in self._gamepad_sources.values():
            return
        self.active_gamepad_targets.discard(target)

    def _set_gamepad_hat(self, instance_id: int, value) -> None:
        hat_x, hat_y = int(value[0]), int(value[1])
        self._set_gamepad_binding(instance_id, "dpad_left", hat_x < 0)
        self._set_gamepad_binding(instance_id, "dpad_right", hat_x > 0)
        self._set_gamepad_binding(instance_id, "dpad_up", hat_y > 0)
        self._set_gamepad_binding(instance_id, "dpad_down", hat_y < 0)

    def _set_gamepad_axis(self, instance_id: int, axis: int, value: float) -> None:
        axis = int(axis)
        value = float(value)
        if axis == 0:
            self._set_gamepad_binding(instance_id, "dpad_left", value <= -self.GAMEPAD_AXIS_THRESHOLD)
            self._set_gamepad_binding(instance_id, "dpad_right", value >= self.GAMEPAD_AXIS_THRESHOLD)
        elif axis == 1:
            self._set_gamepad_binding(instance_id, "dpad_up", value <= -self.GAMEPAD_AXIS_THRESHOLD)
            self._set_gamepad_binding(instance_id, "dpad_down", value >= self.GAMEPAD_AXIS_THRESHOLD)

    def _queue_audio(self, audio_bytes: bytes):
        if not audio_bytes:
            return

        self.audio_byte_buffer.extend(audio_bytes)
        chunk_bytes = self.audio_play_chunk_size * self.audio_channels * 2

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
            else:
                self.audio_started = False
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
