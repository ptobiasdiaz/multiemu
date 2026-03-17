from __future__ import annotations
"""TCP frontend server for remote video/audio streaming and shared input.

The server owns the emulated machine and can fan out frames to multiple
clients at once. Clients first send ``hello`` and receive ``welcome`` with the
stream layout and available input devices. For Spectrum 48K the exposed input
device is a shared keyboard matrix named ``keyboard_0``.

Input is modeled as per-client state, not as immediate events. Each client
publishes its current pressed keys with ``input_state`` and the server merges
all connected states once per emulated frame before applying them to the
machine. That keeps the behavior deterministic and allows several users to
control the same instance cooperatively.
"""

import json
import select
import socket
import time
from collections import deque
from dataclasses import dataclass, field

from multiemu.remote_runtime import RemoteFrontendSession


@dataclass(slots=True)
class ClientSession:
    """Per-client transport state.

    ``pending_video`` stores only the latest completed frame prepared for this
    client. ``pending_audio`` accumulates audio independently so dropped video
    frames do not automatically punch holes in the audio stream. ``send_buffer``
    stores the payload currently being written to the socket, so a partial send
    cannot be overwritten by newer data.
    """

    sock: socket.socket
    address: tuple[str, int]
    client_id: str
    recv_buffer: bytearray = field(default_factory=bytearray)
    control_queue: deque[bytes] = field(default_factory=deque)
    send_buffer: bytes | None = None
    pending_video: bytes | None = None
    pending_audio: bytearray = field(default_factory=bytearray)
    pressed_keys: set[tuple[int, int]] = field(default_factory=set)
    hello_received: bool = False
    wants_video: bool = True
    wants_audio: bool = True
    wants_input: bool = True
    dropped_frames: int = 0


class TcpFrontend(RemoteFrontendSession):
    """Serve an emulator backend to multiple TCP clients over a TCP transport."""

    PROTOCOL_VERSION = 1
    MACHINE_ID = "spectrum48k"
    MACHINE_NAME = "ZX Spectrum 48K"
    KEYBOARD_DEVICE_ID = "keyboard_0"
    MAX_PENDING_AUDIO_MS = 200

    def __init__(
        self,
        backend,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        fps_limit: int = 50,
        audio_sample_rate: int = 44100,
        audio_chunk_size: int = 512,
    ):
        super().__init__(
            backend,
            fps_limit=fps_limit,
            audio_sample_rate=audio_sample_rate,
            audio_chunk_size=audio_chunk_size,
        )
        self.host = host
        self.port = port
        self.server = None
        self._next_client_id = 1
        self.clients: dict[int, ClientSession] = {}

    def start_transport(self) -> None:
        """Create and configure the listening TCP socket."""

        server = socket.create_server((self.host, self.port), reuse_port=False)
        server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        server.setblocking(False)
        self.server = server

    def accept_new_clients(self) -> None:
        """Accept all pending sockets from the listening TCP server."""

        if self.server is None:
            return

        while True:
            try:
                conn, address = self.server.accept()
            except BlockingIOError:
                return

            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.setblocking(False)
            client_id = f"c{self._next_client_id}"
            self._next_client_id += 1
            self.clients[conn.fileno()] = ClientSession(
                sock=conn,
                address=address,
                client_id=client_id,
            )

    def drain_inputs(self) -> None:
        """Process inbound TCP traffic and update per-client input state."""

        if not self.clients:
            return

        sockets = [session.sock for session in self.clients.values()]
        readable, _, errored = select.select(sockets, [], sockets, 0)

        for sock in errored:
            self._disconnect_socket(sock)

        for sock in readable:
            session = self.clients.get(sock.fileno())
            if session is None:
                continue

            try:
                chunk = sock.recv(65536)
            except BlockingIOError:
                continue
            except OSError:
                self._disconnect_socket(sock)
                continue

            if not chunk:
                self._disconnect_socket(sock)
                continue

            session.recv_buffer.extend(chunk)
            self._consume_client_messages(session)

    def _consume_client_messages(self, session: ClientSession):
        while True:
            newline_index = session.recv_buffer.find(b"\n")
            if newline_index < 0:
                return

            raw_line = bytes(session.recv_buffer[:newline_index])
            del session.recv_buffer[:newline_index + 1]

            if not raw_line.strip():
                continue

            message = json.loads(raw_line.decode("utf-8"))
            self._handle_message(session, message)

    def _handle_message(self, session: ClientSession, message: dict):
        msg_type = message.get("type")

        if msg_type == "hello":
            self._handle_hello(session, message)
            return

        if not session.hello_received:
            self._queue_error(session, "handshake_required", "hello must be sent first")
            return

        if msg_type == "shutdown":
            self._disconnect_session(session)
            return

        if msg_type == "ping":
            self._queue_json(session, {"type": "pong", "ts": message.get("ts")})
            return

        if msg_type == "input_state":
            self._handle_input_state(session, message)
            return

        self._queue_error(session, "unsupported_message", f"unsupported message type: {msg_type!r}")

    def _handle_hello(self, session: ClientSession, message: dict):
        if session.hello_received:
            self._queue_error(session, "duplicate_hello", "hello already received")
            return

        if int(message.get("protocol", 0)) != self.PROTOCOL_VERSION:
            self._queue_error(session, "protocol_mismatch", "unsupported protocol version")
            return

        capabilities = message.get("capabilities", {})
        session.wants_video = "rgb24" in capabilities.get("video", ["rgb24"])
        session.wants_audio = "s16le" in capabilities.get("audio", ["s16le"])
        session.wants_input = bool(capabilities.get("input", True))
        session.hello_received = True

        self._queue_json(
            session,
            {
                "type": "welcome",
                "protocol": self.PROTOCOL_VERSION,
                "session_id": f"{self.MACHINE_ID}-{self.port}",
                "client_id": session.client_id,
                "machine": {
                    "id": self.MACHINE_ID,
                    "name": self.MACHINE_NAME,
                },
                "video": {
                    "width": self.frame_width,
                    "height": self.frame_height,
                    "pixel_format": "rgb24",
                    "fps": self.fps_limit,
                },
                "audio": {
                    "sample_rate": self.audio_sample_rate,
                    "channels": 1,
                    "format": "s16le",
                },
                "input_devices": [
                    {
                        "device_id": self.KEYBOARD_DEVICE_ID,
                        "device_type": "key_matrix",
                        "mode": "shared",
                        "state_model": "state",
                        "layout": {
                            "rows": 8,
                            "cols": 5,
                        },
                    }
                ],
            },
        )

    def _handle_input_state(self, session: ClientSession, message: dict):
        if not session.wants_input:
            return

        if message.get("device_id") != self.KEYBOARD_DEVICE_ID:
            self._queue_error(session, "unknown_device", str(message.get("device_id")))
            return

        pressed = set()
        for item in message.get("pressed", []):
            row = int(item["control_a"])
            bit = int(item["control_b"])
            if not (0 <= row < 8 and 0 <= bit < 5):
                continue
            pressed.add((row, bit))

        session.pressed_keys = pressed

    def collect_pressed_keys(self) -> set[tuple[int, int]]:
        """Return the union of currently pressed keys across connected clients."""

        pressed_keys: set[tuple[int, int]] = set()

        for session in self.clients.values():
            if session.hello_received and session.wants_input:
                pressed_keys.update(session.pressed_keys)

        return pressed_keys

    def broadcast_stream_data(self, frame_bytes: bytes, audio_bytes: bytes) -> None:
        """Queue frame/audio payloads for each subscribed TCP client."""

        for session in self.clients.values():
            if not session.hello_received:
                continue
            if session.wants_video:
                if session.pending_video is not None:
                    # Slow clients keep only the most recent unsent frame.
                    session.dropped_frames += 1
                session.pending_video = frame_bytes

            if session.wants_audio and audio_bytes:
                session.pending_audio.extend(audio_bytes)
                self._trim_pending_audio(session)

    def _trim_pending_audio(self, session: ClientSession):
        max_bytes = (self.audio_sample_rate * 2 * self.MAX_PENDING_AUDIO_MS) // 1000
        if len(session.pending_audio) <= max_bytes:
            return

        excess = len(session.pending_audio) - max_bytes
        # Keep sample alignment when trimming old audio to reduce clicks.
        if excess & 1:
            excess += 1
        del session.pending_audio[:excess]

    def _serialize_stream_packet(self, session: ClientSession) -> bytes | None:
        video_bytes = session.pending_video if session.pending_video is not None else b""
        audio_bytes = bytes(session.pending_audio)

        if not video_bytes and not audio_bytes:
            return None

        header = json.dumps(
            {
                "type": "frame",
                "seq": self.backend.frame_counter,
                "video_bytes": len(video_bytes),
                "audio_bytes": len(audio_bytes),
            },
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        session.pending_video = None
        session.pending_audio.clear()
        return header + video_bytes + audio_bytes

    def flush_writes(self) -> None:
        """Advance pending TCP sends for control and frame packets."""

        if not self.clients:
            return

        writable = [
            session.sock
            for session in self.clients.values()
            if session.control_queue
            or session.send_buffer is not None
            or session.pending_video is not None
            or session.pending_audio
        ]
        if not writable:
            return

        _, writable, errored = select.select([], writable, writable, 0)

        for sock in errored:
            self._disconnect_socket(sock)

        for sock in writable:
            session = self.clients.get(sock.fileno())
            if session is None:
                continue

            payload = self._next_outgoing_payload(session)
            if payload is None:
                continue

            try:
                sent = sock.send(payload)
            except BlockingIOError:
                continue
            except OSError:
                self._disconnect_socket(sock)
                continue

            if sent <= 0:
                self._disconnect_socket(sock)
                continue

            self._advance_outgoing_payload(session, payload, sent)

    def service_transport(self, remaining_seconds: float) -> None:
        """Use spare frame time to continue network I/O without emulating."""

        deadline = time.monotonic() + remaining_seconds

        while self.running and time.monotonic() < deadline:
            self.accept_new_clients()
            self.drain_inputs()
            self.flush_writes()
            self.remove_disconnected_clients()
            time.sleep(0.001)

    def _next_outgoing_payload(self, session: ClientSession) -> memoryview | None:
        if session.send_buffer is None:
            if session.control_queue:
                session.send_buffer = session.control_queue.popleft()
            else:
                # Promote the next completed packet only when no partial payload
                # is in flight for this client.
                session.send_buffer = self._serialize_stream_packet(session)

        if session.send_buffer is None:
            return None

        return memoryview(session.send_buffer)

    def _advance_outgoing_payload(self, session: ClientSession, payload: memoryview, sent: int):
        remaining = bytes(payload[sent:])
        session.send_buffer = remaining or None

    def _queue_json(self, session: ClientSession, payload: dict):
        session.control_queue.append(
            json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        )

    def _queue_error(self, session: ClientSession, code: str, detail: str):
        self._queue_json(session, {"type": "error", "code": code, "detail": detail})

    def _disconnect_socket(self, sock: socket.socket):
        session = self.clients.get(sock.fileno())
        if session is not None:
            self._disconnect_session(session)

    def _disconnect_session(self, session: ClientSession):
        fileno = session.sock.fileno()
        try:
            session.sock.close()
        finally:
            self.clients.pop(fileno, None)

    def remove_disconnected_clients(self) -> None:
        """Remove sessions whose sockets are already closed."""

        disconnected = [fileno for fileno, session in self.clients.items() if session.sock.fileno() < 0]
        for fileno in disconnected:
            self.clients.pop(fileno, None)

    def close_transport(self) -> None:
        """Close all client sockets and tear down the listening TCP socket."""

        for session in list(self.clients.values()):
            try:
                session.sock.close()
            finally:
                pass
        self.clients.clear()
        if self.server is not None:
            try:
                self.server.close()
            finally:
                self.server = None
