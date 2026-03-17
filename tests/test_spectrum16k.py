from machines.z80 import Spectrum16K


rom = bytes([0x00]) * 0x4000

m = Spectrum16K(rom)
m.reset()

m.poke(0x4000, 0x12)
assert m.peek(0x4000) == 0x12
assert m.peek(0x8000) == 0xFF

try:
    m.poke(0x8000, 0x34)
except ValueError:
    pass
else:
    raise AssertionError("Spectrum16K no debe permitir escritura en RAM no mapeada")

print(m.snapshot())
