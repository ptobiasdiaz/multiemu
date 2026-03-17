from __future__ import annotations

from pathlib import Path

from frontend.tcp_frontend import TcpFrontend
from machines.z80 import Spectrum48K


def main():
    rom_path = Path("48E.rom")
    rom = rom_path.read_bytes()

    machine = Spectrum48K(rom)
    machine.reset()

    app = TcpFrontend(
        machine,
        host="127.0.0.1",
        port=8765,
        fps_limit=50,
        audio_sample_rate=44100,
        audio_chunk_size=512,
    )
    app.run()


if __name__ == "__main__":
    main()
