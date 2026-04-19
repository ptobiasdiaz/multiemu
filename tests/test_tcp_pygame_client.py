from __future__ import annotations

import pygame

from frontend.tcp_pygame_client import TcpPygameClient


def test_tcp_client_welcome_accepts_none_fps():
    client = TcpPygameClient()

    client._configure_from_welcome(
        {
            "type": "welcome",
            "video": {
                "width": 160,
                "height": 144,
                "pixel_format": "rgb24",
                "fps": None,
            },
            "audio": {
                "format": "s16le",
                "sample_rate": 44100,
                "chunk_samples": 512,
            },
            "machine": {"id": "gameboy"},
            "input_devices": [{"device_id": "keyboard_0", "device_type": "key_matrix"}],
            "frontend": {"keymap": None, "gamepad_map": "gameboy"},
        }
    )

    assert client.fps_limit == 50
    assert client.gamepad_map["button_south"] == (1, 0)


def test_tcp_client_welcome_records_joystick_devices():
    client = TcpPygameClient()

    client._configure_from_welcome(
        {
            "type": "welcome",
            "video": {"width": 160, "height": 144, "pixel_format": "rgb24", "fps": 50},
            "audio": {"format": "s16le", "sample_rate": 44100, "chunk_samples": 512},
            "machine": {"id": "spectrum48k"},
            "input_devices": [
                {"device_id": "keyboard_0", "device_type": "key_matrix"},
                {"device_id": "joystick_0", "device_type": "joystick"},
                {"device_id": "joystick_1", "device_type": "joystick"},
            ],
            "frontend": {"keymap": "spectrum48k", "gamepad_map": "spectrum"},
        }
    )

    assert client.joystick_device_ids == ["joystick_0", "joystick_1"]


def test_tcp_client_prefers_requested_joystick_player_for_assignment():
    client = TcpPygameClient(joystick_player=2)
    client.joystick_device_ids = ["joystick_0", "joystick_1"]

    assert client._next_gamepad_assignment() == 1


def test_tcp_client_falls_back_to_other_joystick_when_preferred_is_taken():
    client = TcpPygameClient(joystick_player=2)
    client.joystick_device_ids = ["joystick_0", "joystick_1"]
    client._gamepad_assignments[10] = 1

    assert client._next_gamepad_assignment() == 0


def test_tcp_client_welcome_accepts_inline_keymap_spec():
    client = TcpPygameClient()

    client._configure_from_welcome(
        {
            "type": "welcome",
            "video": {"width": 160, "height": 144, "pixel_format": "rgb24", "fps": 50},
            "audio": {"format": "s16le", "sample_rate": 44100, "chunk_samples": 512},
            "machine": {"id": "spectrum128k"},
            "input_devices": [{"device_id": "keyboard_0", "device_type": "key_matrix"}],
            "frontend": {
                "keymap": "spectrum128k",
                "gamepad_map": "spectrum",
                "keymap_spec": {
                    "id": "custom_spectrum",
                    "base": "spectrum128k",
                    "keys": {"K_a": [9, 9]},
                },
            },
        }
    )

    assert client.keymap_name == "spectrum128k"
    assert client.keymap[97] == (9, 9)
    assert client.gamepad_map["button_south"] == 16


def test_tcp_client_keeps_shift_pressed_for_cpc_shifted_keys(monkeypatch):
    client = TcpPygameClient()
    client.keymap_name = "cpc"
    client.input_maps = client.input_maps = __import__("frontend.keymap", fromlist=["load_pygame_input_maps"]).load_pygame_input_maps("cpc")
    client.keymap = client.input_maps.keymap
    client.combo_keymap = client.input_maps.combo_keymap
    client.unicode_combo_keymap = client.input_maps.unicode_combo_keymap

    class _ShiftDown:
        type = pygame.KEYDOWN
        key = pygame.K_LSHIFT
        mod = pygame.KMOD_SHIFT
        unicode = ""

    class _ADown:
        type = pygame.KEYDOWN
        key = pygame.K_a
        mod = pygame.KMOD_SHIFT
        unicode = "A"

    monkeypatch.setattr("pygame.event.get", lambda: [_ShiftDown(), _ADown()])
    client._handle_local_events()

    assert pygame.K_LSHIFT in client._keyboard_key_bindings
    assert client._keyboard_key_bindings[pygame.K_LSHIFT] == ((2, 5),)
    assert (2, 5) in client.active_keyboard_controls
