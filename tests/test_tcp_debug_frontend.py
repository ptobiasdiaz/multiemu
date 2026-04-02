from __future__ import annotations

import json
from collections import deque

from frontend.tcp_debug_frontend import TcpDebugFrontend


class _FakeCPU:
    def __init__(self):
        self.state = {"PC": 0x1000, "A": 0x01}

    def step(self):
        self.state["PC"] += 1
        return 4

    def snapshot(self):
        return dict(self.state)

    def read_state(self):
        return dict(self.state)

    def write_state(self, state):
        self.state = dict(state)


class _FakeBus:
    def __init__(self):
        self.mem = bytearray(range(256))

    def read8(self, addr):
        return self.mem[addr & 0xFF]

    def write8(self, addr, value):
        self.mem[addr & 0xFF] = value & 0xFF

    def read_state(self):
        return {"data": list(self.mem)}

    def write_state(self, state):
        self.mem[:] = bytes(state["data"])


class _FakeChip:
    def __init__(self):
        self.value = 7

    def read_state(self):
        return {"value": self.value}

    def write_state(self, state):
        self.value = int(state["value"])


class _FakeMachine:
    def __init__(self):
        self.machine_id = "fake"
        self.display_name = "Fake Machine"
        self.frame_counter = 0
        self.frame_width = 1
        self.frame_height = 1
        self.framebuffer_rgb24 = b"\x00\x00\x00"
        self.input_keymap_name = None
        self.tstates = 0
        self.frame_tstates = 0
        self.cpu = _FakeCPU()
        self.bus = _FakeBus()
        self.vic = _FakeChip()

    def render_frame(self):
        return self.framebuffer_rgb24

    def run_frame(self):
        return 0

    def clear_input_state(self):
        return None

    def handle_input_event(self, event):
        return None

    def get_audio_buffered_samples(self):
        return 0

    def pop_audio_samples(self, count):
        from array import array
        return array("h")

    def read_state(self):
        return {
            "tstates": self.tstates,
            "frame_tstates": self.frame_tstates,
            "frame_counter": self.frame_counter,
            "cpu": self.cpu.read_state(),
            "bus": self.bus.read_state(),
        }

    def write_state(self, state):
        self.tstates = int(state["tstates"])
        self.frame_tstates = int(state["frame_tstates"])
        self.frame_counter = int(state["frame_counter"])
        self.cpu.write_state(state["cpu"])
        self.bus.write_state(state["bus"])


class _Session:
    def __init__(self, *, hello_received=False):
        self.hello_received = hello_received
        self.control_queue = deque()
        self.client_id = "c1"
        self.wants_video = True
        self.wants_audio = True
        self.wants_input = True


def _pop_json(session):
    return json.loads(session.control_queue.popleft().decode("utf-8"))


def test_tcp_debug_frontend_welcome_announces_debug_capabilities():
    frontend = TcpDebugFrontend(_FakeMachine())
    session = _Session()

    frontend._handle_hello(session, {"type": "hello", "protocol": 1, "capabilities": {}})
    payload = _pop_json(session)

    assert payload["type"] == "welcome"
    assert payload["debug"]["enabled"] is True
    assert "list_devices" in payload["debug"]["features"]


def test_tcp_debug_frontend_lists_devices_and_reads_device_state():
    frontend = TcpDebugFrontend(_FakeMachine())
    session = _Session(hello_received=True)

    frontend._handle_message(session, {"type": "debug.list_devices"})
    devices = _pop_json(session)
    assert devices["type"] == "debug.devices"
    assert any(device["id"] == "cpu" for device in devices["devices"])
    assert any(device["id"] == "vic" for device in devices["devices"])

    frontend._handle_message(session, {"type": "debug.get_state", "device": "vic"})
    state = _pop_json(session)
    assert state == {"type": "debug.state", "device": "vic", "state": {"value": 7}}


def test_tcp_debug_frontend_writes_device_state():
    frontend = TcpDebugFrontend(_FakeMachine())
    session = _Session(hello_received=True)

    frontend._handle_message(
        session,
        {"type": "debug.set_state", "device": "vic", "state": {"value": 99}, "ref": "r1"},
    )
    ack = _pop_json(session)

    assert ack["type"] == "ack"
    assert ack["ref"] == "r1"
    assert ack["device"] == "vic"
    assert ack["state"] == {"value": 99}
