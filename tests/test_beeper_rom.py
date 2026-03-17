from pathlib import Path

from machines.z80 import Spectrum48K
from frontend.pygame_frontend import PygameFrontend


def build_test_rom() -> bytes:
    # Tono bastante más audible:
    #
    # DI
    # loop:
    #   LD A,10h
    #   OUT (FEh),A
    #   LD B,40h
    # d1:
    #   DJNZ d1
    #
    #   XOR A
    #   OUT (FEh),A
    #   LD B,40h
    # d2:
    #   DJNZ d2
    #
    #   JP loop

    code = bytes([
        0xF3,             # DI

        0x3E, 0x10,       # loop: LD A,10h
        0xD3, 0xFE,       #       OUT (FEh),A
        0x06, 0x40,       #       LD B,40h
        0x10, 0xFE,       # d1:   DJNZ d1

        0xAF,             #       XOR A
        0xD3, 0xFE,       #       OUT (FEh),A
        0x06, 0x40,       #       LD B,40h
        0x10, 0xFE,       # d2:   DJNZ d2

        0xC3, 0x01, 0x00, #       JP loop
    ])

    return code + bytes(0x4000 - len(code))


def main():
    rom = build_test_rom()
    Path("beeper_test_fast.rom").write_bytes(rom)

    machine = Spectrum48K(rom)
    machine.reset()

    app = PygameFrontend(
        machine,
        scale=2,
        window_title="MultiEmu - Fast Beeper Test",
        fps_limit=50,
    )
    app.run()


if __name__ == "__main__":
    main()
