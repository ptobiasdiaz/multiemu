from machines.z80 import Spectrum48K

# Programa "ROM" mínimo:
#   LD A,2
#   OUT (FEh),A      ; cambia borde
#   LD A,9
#   LD (4000h),A     ; escribe en RAM
#   LD A,(4000h)
#   HALT
rom = bytes([
    0x3E, 0x02,             # LD A,02h
    0xD3, 0xFE,             # OUT (FEh),A
    0x3E, 0x09,             # LD A,09h
    0x32, 0x00, 0x40,       # LD (4000h),A
    0x3A, 0x00, 0x40,       # LD A,(4000h)
    0x76,                   # HALT
])

rom = rom + bytes(0x4000 - len(rom))

m = Spectrum48K(rom)
m.reset()
m.run_cycles(200)

print(m.snapshot())
