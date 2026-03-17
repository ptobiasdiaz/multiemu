from machines.z80 import Spectrum48K

# ROM: JP 4000h
rom = bytes([
    0xC3, 0x00, 0x40
])
rom = rom + bytes(0x4000 - len(rom))

# Programa en RAM:
#   LD A,5
#   OUT (FEh),A
#   LD A,42h
#   HALT
ram_prog = bytes([
    0x3E, 0x05,
    0xD3, 0xFE,
    0x3E, 0x42,
    0x76
])

m = Spectrum48K(rom)
m.load_ram(0x4000, ram_prog)

m.reset()
m.run_cycles(200)

print(m.snapshot())
