from __future__ import annotations

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
            "frontend": {"keymap": None},
        }
    )

    assert client.fps_limit == 50
