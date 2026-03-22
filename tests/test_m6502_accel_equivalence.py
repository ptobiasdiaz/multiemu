from __future__ import annotations

import pytest

from cpu.m6502 import M6502Bus, M6502Core, RAMBlock, ROMBlock
from tests.fallbacks.m6502_core_reference import M6502Core as M6502CoreReference


def _active_core_is_cython() -> bool:
    module_file = getattr(__import__("cpu.m6502.core", fromlist=["M6502Core"]), "__file__", "")
    return module_file.endswith((".so", ".pyd"))


def _make_rom(program: bytes, *, base: int = 0xF800, size: int = 0x0800) -> ROMBlock:
    rom = ROMBlock(size)
    rom_bytes = bytearray([0xEA] * size)
    rom_bytes[0:len(program)] = program
    rom_bytes[-6] = base & 0xFF
    rom_bytes[-5] = (base >> 8) & 0xFF
    rom_bytes[-4] = base & 0xFF
    rom_bytes[-3] = (base >> 8) & 0xFF
    rom_bytes[-2] = base & 0xFF
    rom_bytes[-1] = (base >> 8) & 0xFF
    rom.load_bytes(bytes(rom_bytes))
    return rom


def _build_cpu_pair(program: bytes):
    accel_bus = M6502Bus()
    ref_bus = M6502Bus()
    accel_ram = RAMBlock(0x0800)
    ref_ram = RAMBlock(0x0800)
    accel_rom = _make_rom(program)
    ref_rom = _make_rom(program)

    accel_bus.map_block(0x0000, accel_ram, size=accel_ram.size)
    ref_bus.map_block(0x0000, ref_ram, size=ref_ram.size)
    accel_bus.map_block(0xF800, accel_rom, size=accel_rom.size)
    ref_bus.map_block(0xF800, ref_rom, size=ref_rom.size)

    accel = M6502Core(accel_bus, stop_on_brk=True)
    reference = M6502CoreReference(ref_bus, stop_on_brk=True)
    return accel, accel_bus, accel_ram, reference, ref_bus, ref_ram


@pytest.mark.skipif(not _active_core_is_cython(), reason="requiere cpu.m6502.core compilado con Cython")
def test_m6502_accel_matches_python_reference_for_stateful_program():
    program = bytes(
        [
            0xF8,              # SED
            0x18,              # CLC
            0xA9, 0x45,        # LDA #$45
            0x69, 0x55,        # ADC #$55
            0x38,              # SEC
            0xE9, 0x01,        # SBC #$01
            0xA2, 0x03,        # LDX #$03
            0xA0, 0x02,        # LDY #$02
            0x85, 0x10,        # STA $10
            0x95, 0x10,        # STA $10,X
            0x99, 0x00, 0x02,  # STA $0200,Y
            0x26, 0x10,        # ROL $10
            0xF6, 0x10,        # INC $10,X
            0xD8,              # CLD
            0x00,              # BRK
        ]
    )
    accel, _accel_bus, accel_ram, reference, _ref_bus, ref_ram = _build_cpu_pair(program)

    accel.run_cycles(128)
    reference.run_cycles(128)

    assert accel.snapshot() == reference.snapshot()
    for addr in (0x0010, 0x0013, 0x0202):
        assert accel_ram.peek(addr) == ref_ram.peek(addr)


@pytest.mark.skipif(not _active_core_is_cython(), reason="requiere cpu.m6502.core compilado con Cython")
def test_m6502_accel_matches_python_reference_for_interrupt_flow():
    program = bytes(
        [
            0x58,              # F800: CLI
            0xEA,              # F801: NOP
            0xEA,              # F802: NOP
            0xEA,              # F803: NOP
            0xEA,              # F804
            0x40,              # F805: RTI
            0xEA,              # F806
            0x40,              # F807: RTI
            0x00,              # F808: BRK if reached
        ]
    )
    accel, accel_bus, _accel_ram, reference, ref_bus, _ref_ram = _build_cpu_pair(program)

    accel.step()      # CLI
    reference.step()
    accel_bus.request_irq()
    ref_bus.request_irq()
    assert accel.step() == reference.step()
    accel_bus.clear_irq()
    ref_bus.clear_irq()
    assert accel.snapshot() == reference.snapshot()

    assert accel.step() == reference.step()  # RTI
    accel_bus.request_nmi()
    ref_bus.request_nmi()
    assert accel.step() == reference.step()
    assert accel.snapshot() == reference.snapshot()
