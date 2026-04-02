from __future__ import annotations

"""TCP debug frontend server.

Extends TcpFrontend with a separate run() loop that supports pausing the CPU,
stepping one instruction at a time, and inspecting / modifying machine state.

Protocol additions (client → server):
  {"type": "pause"}
  {"type": "resume"}
  {"type": "step"}
  {"type": "get_state"}
  {"type": "write_state", "state": {...}, "ref": <any>}
  {"type": "read_memory",  "addr": N, "count": N}
  {"type": "write_memory", "addr": N, "data": [N, ...], "ref": <any>}

Protocol additions (server → client):
  {"type": "paused",  "cpu": {...}, "state": {...}, "tstates": N, "frame_tstates": N}
  {"type": "resumed"}
  {"type": "stepped", "cpu": {...}, "state": {...}, "tstates": N, "frame_tstates": N, "cycles": N}
  {"type": "state",   "cpu": {...}, "state": {...}, "tstates": N, "frame_tstates": N, "frame_counter": N}
  {"type": "memory",  "addr": N, "data": [...]}
  {"type": "ack",     "ref": <any>}

The CPU is paused at frame boundaries only: a pause request received mid-frame
takes effect after the current frame completes.  This keeps the debug loop free
of any checks inside the Cython frame-runner hot path.
"""

import time

from frontend.tcp_frontend import TcpFrontend
from multiemu.debug_session import DebugSession


class TcpDebugFrontend(TcpFrontend):
    """TcpFrontend with a debug-aware run loop and extra protocol messages."""

    def __init__(self, backend, **kwargs):
        super().__init__(backend, **kwargs)
        self._debug = DebugSession(self.machine)
        self._paused: bool = False
        self._pause_requested: bool = False

    # ------------------------------------------------------------------
    # Main loop (replaces RemoteFrontendSession.run)
    # ------------------------------------------------------------------

    def run(self):
        self.start_transport()
        self.running = True

        try:
            while self.running:
                frame_start = time.monotonic()

                self.accept_new_clients()
                self.drain_inputs()

                if self._paused:
                    self.flush_writes()
                    self.remove_disconnected_clients()
                    time.sleep(0.001)
                    continue

                self._apply_merged_input_state(self.collect_pressed_keys())
                self.backend.run_frame()

                # Honour a pause request at the frame boundary.
                if self._pause_requested:
                    self._pause_requested = False
                    self._paused = True
                    self._notify_all(self._paused_payload())

                frame_bytes = self.encode_framebuffer(
                    getattr(self.backend, "framebuffer_rgb24", None)
                )
                audio_bytes = self.pop_audio_bytes()
                self.broadcast_stream_data(frame_bytes, audio_bytes)
                self.flush_writes()
                self.remove_disconnected_clients()

                if self.fps_limit is not None and self.fps_limit > 0:
                    elapsed = time.monotonic() - frame_start
                    budget = 1.0 / self.fps_limit
                    if elapsed < budget:
                        self.service_transport(budget - elapsed)
        finally:
            self.running = False
            self.close_transport()

    # ------------------------------------------------------------------
    # Message handling (extends parent)
    # ------------------------------------------------------------------

    def _handle_message(self, session, message: dict):
        msg_type = message.get("type")

        if msg_type in {"pause", "debug.pause"}:
            if session.hello_received:
                self._pause_requested = True
            return

        if msg_type in {"resume", "debug.resume"}:
            if session.hello_received and self._paused:
                self._paused = False
                self._notify_all({"type": "resumed"})
            return

        if msg_type in {"step", "debug.step"}:
            if not session.hello_received:
                self._queue_error(session, "handshake_required", "hello must be sent first")
                return
            if not self._paused:
                self._queue_error(session, "not_paused", "CPU is not paused")
                return
            self._execute_step()
            return

        if msg_type in {"list_devices", "debug.list_devices"}:
            if not session.hello_received:
                self._queue_error(session, "handshake_required", "hello must be sent first")
                return
            self._queue_json(
                session,
                {"type": "debug.devices", "devices": self._debug.list_devices()},
            )
            return

        if msg_type in {"get_state", "debug.get_state"}:
            if not session.hello_received:
                self._queue_error(session, "handshake_required", "hello must be sent first")
                return
            device_id = message.get("device")
            if device_id:
                self._queue_json(
                    session,
                    {
                        "type": "debug.state",
                        "device": str(device_id),
                        "state": self._debug.get_device_state(str(device_id)),
                    },
                )
                return
            self._queue_json(session, self._state_payload())
            return

        if msg_type in {"write_state", "debug.set_state"}:
            if not session.hello_received:
                self._queue_error(session, "handshake_required", "hello must be sent first")
                return
            device_id = message.get("device")
            if device_id:
                self._debug.set_device_state(str(device_id), message.get("state", {}))
                result_state = self._debug.get_device_state(str(device_id))
            else:
                self._debug.write_state(message.get("state", {}))
                result_state = self._debug.read_state()
            self._queue_json(
                session,
                {
                    "type": "ack",
                    "ref": message.get("ref"),
                    "device": device_id,
                    "state": result_state,
                },
            )
            return

        if msg_type in {"read_memory", "debug.read_memory"}:
            if not session.hello_received:
                self._queue_error(session, "handshake_required", "hello must be sent first")
                return
            addr = int(message.get("addr", 0))
            count = max(1, int(message.get("count", 16)))
            data = self._debug.read_memory(addr, count)
            self._queue_json(session, {"type": "memory", "addr": addr, "data": data})
            return

        if msg_type in {"write_memory", "debug.write_memory"}:
            if not session.hello_received:
                self._queue_error(session, "handshake_required", "hello must be sent first")
                return
            addr = int(message.get("addr", 0))
            data = [int(b) for b in message.get("data", [])]
            self._debug.write_memory(addr, data)
            self._queue_json(session, {"type": "ack", "ref": message.get("ref")})
            return

        super()._handle_message(session, message)

    def _handle_hello(self, session, message: dict):
        super()._handle_hello(session, message)
        if not session.control_queue:
            return
        welcome = session.control_queue.pop()
        payload = welcome.decode("utf-8").strip()
        if not payload:
            return
        import json

        message_obj = json.loads(payload)
        message_obj["debug"] = {
            "enabled": True,
            "features": [
                "pause",
                "resume",
                "step",
                "list_devices",
                "get_state",
                "set_state",
                "read_memory",
                "write_memory",
            ],
        }
        session.control_queue.append(
            json.dumps(message_obj, separators=(",", ":")).encode("utf-8") + b"\n"
        )

    # ------------------------------------------------------------------
    # Debug helpers
    # ------------------------------------------------------------------

    def _execute_step(self):
        snapshot = self._debug.step()
        state = self._debug.read_state()

        if self._debug.frame_completed:
            frame_bytes = self.encode_framebuffer(
                getattr(self.backend, "framebuffer_rgb24", None)
            )
            audio_bytes = self.pop_audio_bytes()
            self.broadcast_stream_data(frame_bytes, audio_bytes)

        self._notify_all({
            "type": "stepped",
            "cpu": snapshot,
            "state": state,
            "tstates": self.machine.tstates,
            "frame_tstates": self.machine.frame_tstates,
            "cycles": self._debug.last_step_cycles,
        })

    def _paused_payload(self) -> dict:
        state = self._debug.read_state()
        return {
            "type": "paused",
            "cpu": state.get("cpu", self.machine.cpu.snapshot()),
            "state": state,
            "tstates": self.machine.tstates,
            "frame_tstates": self.machine.frame_tstates,
        }

    def _state_payload(self) -> dict:
        state = self._debug.read_state()
        return {
            "type": "state",
            "cpu": state.get("cpu", self.machine.cpu.snapshot()),
            "state": state,
            "tstates": self.machine.tstates,
            "frame_tstates": self.machine.frame_tstates,
            "frame_counter": self.machine.frame_counter,
        }

    def _notify_all(self, payload: dict):
        for session in self.clients.values():
            if session.hello_received:
                self._queue_json(session, payload)
