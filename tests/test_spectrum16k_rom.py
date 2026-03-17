from pathlib import Path

from frontend.pygame_frontend import PygameFrontend
from machines.z80 import Spectrum16K


def main():
    rom_path = Path("cl-48.rom")
    rom = rom_path.read_bytes()

    machine = Spectrum16K(rom)
    machine.reset()

    app = PygameFrontend(
        machine,
        scale=2,
        window_title="MultiEmu - Spectrum 16K",
        fps_limit=50,
    )
    app.run()


if __name__ == "__main__":
    main()
