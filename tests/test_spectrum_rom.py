from pathlib import Path

from machines.z80 import Spectrum48K
from frontend.pygame_frontend import PygameFrontend


def main():
    rom_path = Path("48E.rom")
    rom = rom_path.read_bytes()

    machine = Spectrum48K(rom)
    machine.reset()

    app = PygameFrontend(
        machine,
        scale=2,
        window_title="MultiEmu - Spectrum 48K",
        fps_limit=50,
    )
    app.run()


if __name__ == "__main__":
    main()
