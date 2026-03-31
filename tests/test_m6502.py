from __future__ import annotations

import pytest

from cpu.m6502 import M6502Bus, M6502Core, RAMBlock, ROMBlock
from cpu.m6502.core import FLAG_B, FLAG_C, FLAG_D, FLAG_I, FLAG_N, FLAG_U, FLAG_V, FLAG_Z


def _make_rom(
    program: bytes,
    *,
    base: int = 0xF800,
    size: int = 0x0800,
    nmi_vector: int | None = None,
    reset_vector: int | None = None,
    irq_vector: int | None = None,
) -> ROMBlock:
    rom = ROMBlock(size)
    rom_bytes = bytearray([0xEA] * size)
    rom_bytes[0:len(program)] = program
    if nmi_vector is None:
        nmi_vector = base
    if reset_vector is None:
        reset_vector = base
    if irq_vector is None:
        irq_vector = base
    rom_bytes[-6] = nmi_vector & 0xFF
    rom_bytes[-5] = (nmi_vector >> 8) & 0xFF
    rom_bytes[-4] = reset_vector & 0xFF
    rom_bytes[-3] = (reset_vector >> 8) & 0xFF
    rom_bytes[-2] = irq_vector & 0xFF
    rom_bytes[-1] = (irq_vector >> 8) & 0xFF
    rom.load_bytes(bytes(rom_bytes))
    return rom


def _make_test_cpu(program: bytes, *, base: int = 0xF800, size: int = 0x0800) -> tuple[M6502Bus, M6502Core]:
    bus = M6502Bus()
    rom = _make_rom(program, base=base, size=size)
    bus.map_block(base, rom, size=rom.size)
    cpu = M6502Core(bus, stop_on_brk=True)
    return bus, cpu


def test_m6502_reset_vector_is_loaded_from_fffc():
    bus, cpu = _make_test_cpu(b"\xEA")

    assert cpu.snapshot()["PC"] == 0xF800


def test_m6502_can_store_accumulator_to_absolute_memory():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0xA9, 0x42,        # LDA #42
                0x8D, 0x00, 0x02,  # STA $0200
                0x00,              # BRK
            ]
        )
    )
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)

    cpu.run_cycles(16)

    assert ram.peek(0x0200) == 0x42
    assert cpu.snapshot()["halted"] is True


def test_m6502_jmp_absolute_loops_to_target():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0x4C, 0x03, 0xF8,  # JMP $F803
                0xEA,              # NOP
                0xEA,              # NOP
                0x4C, 0x03, 0xF8,  # JMP $F803
            ]
        )
    )

    cpu.run_cycles(10)

    assert cpu.snapshot()["PC"] == 0xF803


def test_m6502_jsr_rts_roundtrip_and_stack_usage():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0x20, 0x07, 0xF8,  # JSR $F807
                0x8D, 0x00, 0x02,  # STA $0200
                0x00,              # BRK
                0xA9, 0x55,        # LDA #$55
                0x60,              # RTS
            ]
        )
    )
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)

    cpu.run_cycles(32)

    assert ram.peek(0x0200) == 0x55
    assert cpu.snapshot()["SP"] == 0xFD


def test_m6502_adc_sbc_and_compare_update_flags():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0x18,              # CLC
                0xA9, 0x0F,        # LDA #$0F
                0x69, 0x01,        # ADC #$01
                0x38,              # SEC
                0xE9, 0x01,        # SBC #$01
                0xC9, 0x0F,        # CMP #$0F
                0x00,              # BRK
            ]
        )
    )

    cpu.run_cycles(32)
    snap = cpu.snapshot()

    assert snap["A"] == 0x0F
    assert (snap["P"] & FLAG_C) != 0
    assert (snap["P"] & FLAG_Z) != 0


def test_m6502_adc_and_sbc_honor_decimal_mode():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0xF8,              # SED
                0x18,              # CLC
                0xA9, 0x45,        # LDA #$45
                0x69, 0x55,        # ADC #$55 -> $00, C=1
                0x38,              # SEC
                0xE9, 0x01,        # SBC #$01 -> $99
                0xD8,              # CLD
                0x00,              # BRK
            ]
        )
    )

    cpu.run_cycles(32)
    snap = cpu.snapshot()

    assert snap["A"] == 0x99
    assert (snap["P"] & FLAG_D) == 0
    assert (snap["P"] & FLAG_C) == 0
    assert (snap["P"] & FLAG_Z) == 0


def test_m6502_decimal_adc_preserves_binary_overflow_flag_semantics():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0xF8,              # SED
                0x18,              # CLC
                0xA9, 0x50,        # LDA #$50
                0x69, 0x50,        # ADC #$50
                0x00,              # BRK
            ]
        )
    )

    cpu.run_cycles(16)
    snap = cpu.snapshot()

    assert snap["A"] == 0x00
    assert (snap["P"] & FLAG_C) != 0
    assert (snap["P"] & FLAG_V) != 0
    assert (snap["P"] & FLAG_Z) != 0


def test_m6502_branch_and_transfer_instructions_work_together():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0xA9, 0x00,        # LDA #$00
                0xAA,              # TAX
                0xE8,              # INX
                0x8A,              # TXA
                0xD0, 0x02,        # BNE +2
                0xA9, 0x7F,        # skipped
                0xA8,              # TAY
                0x88,              # DEY
                0x98,              # TYA
                0x00,              # BRK
            ]
        )
    )

    cpu.run_cycles(32)
    snap = cpu.snapshot()

    assert snap["A"] == 0x00
    assert snap["X"] == 0x01
    assert snap["Y"] == 0x00
    assert (snap["P"] & FLAG_Z) != 0


def test_m6502_bvc_and_bvs_follow_overflow_flag():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0x18,              # CLC
                0xA9, 0x50,        # LDA #$50
                0x69, 0x50,        # ADC #$50 -> V=1
                0x70, 0x02,        # BVS +2
                0xA9, 0x00,        # skipped
                0xB8,              # CLV
                0x50, 0x02,        # BVC +2
                0xA9, 0x01,        # skipped
                0xA9, 0x7E,        # executed
                0x00,              # BRK
            ]
        )
    )

    cpu.run_cycles(32)
    snap = cpu.snapshot()

    assert snap["A"] == 0x7E
    assert (snap["P"] & FLAG_V) == 0


def test_m6502_branch_cycle_counts_include_page_cross():
    bus, cpu = _make_test_cpu(bytes([0xEA] * 0xFD + [0xD0, 0x02, 0xEA, 0xEA]))
    cpu.PC = 0xF8FD
    cpu.P &= ~FLAG_Z

    cycles = cpu.step()

    assert cycles == 4
    assert cpu.snapshot()["PC"] == 0xF901


@pytest.mark.parametrize(
    ("program", "setup", "expected_cycles"),
    [
            (
                bytes([0xBD, 0xFF, 0x01, 0x00]),  # LDA $01FF,X
                lambda bus, cpu, ram: (
                    setattr(cpu, "X", 0x01),
                    ram.write(0x0200, 0x42),
                ),
                5,
            ),
        (
                bytes([0xB9, 0xFF, 0x01, 0x00]),  # LDA $01FF,Y
                lambda bus, cpu, ram: (
                    setattr(cpu, "Y", 0x01),
                    ram.write(0x0200, 0x42),
                ),
                5,
            ),
        (
                bytes([0xB1, 0x10, 0x00]),  # LDA ($10),Y
                lambda bus, cpu, ram: (
                    setattr(cpu, "Y", 0x01),
                    ram.write(0x0010, 0xFF),
                    ram.write(0x0011, 0x01),
                    ram.write(0x0200, 0x42),
                ),
                6,
            ),
        (
                bytes([0x79, 0xFF, 0x01, 0x00]),  # ADC $01FF,Y
                lambda bus, cpu, ram: (
                    setattr(cpu, "Y", 0x01),
                    setattr(cpu, "A", 0x01),
                    ram.write(0x0200, 0x01),
                ),
                5,
            ),
        (
                bytes([0xDD, 0xFF, 0x01, 0x00]),  # CMP $01FF,X
                lambda bus, cpu, ram: (
                    setattr(cpu, "X", 0x01),
                    setattr(cpu, "A", 0x42),
                    ram.write(0x0200, 0x42),
                ),
                5,
            ),
        (
                bytes([0xBE, 0xFF, 0x01, 0x00]),  # LDX $01FF,Y
                lambda bus, cpu, ram: (
                    setattr(cpu, "Y", 0x01),
                    ram.write(0x0200, 0x42),
                ),
                5,
            ),
        (
                bytes([0xBC, 0xFF, 0x01, 0x00]),  # LDY $01FF,X
                lambda bus, cpu, ram: (
                    setattr(cpu, "X", 0x01),
                    ram.write(0x0200, 0x42),
                ),
                5,
            ),
    ],
)
def test_m6502_indexed_read_cycle_counts_include_page_cross(program, setup, expected_cycles):
    bus, cpu = _make_test_cpu(program)
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)
    setup(bus, cpu, ram)

    cycles = cpu.step()

    assert cycles == expected_cycles


def test_m6502_zero_page_and_absolute_indexed_modes_can_load_and_store():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0xA2, 0x03,        # LDX #$03
                0xA0, 0x02,        # LDY #$02
                0xA9, 0x44,        # LDA #$44
                0x85, 0x10,        # STA $10
                0x95, 0x10,        # STA $10,X -> $13
                0x99, 0x00, 0x02,  # STA $0200,Y -> $0202
                0xA5, 0x10,        # LDA $10
                0x8D, 0x10, 0x02,  # STA $0210
                0xB5, 0x10,        # LDA $10,X
                0x8D, 0x11, 0x02,  # STA $0211
                0xB9, 0x00, 0x02,  # LDA $0200,Y
                0x8D, 0x12, 0x02,  # STA $0212
                0x00,              # BRK
            ]
        )
    )
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)

    cpu.run_cycles(96)

    assert ram.peek(0x0010) == 0x44
    assert ram.peek(0x0013) == 0x44
    assert ram.peek(0x0202) == 0x44
    assert ram.peek(0x0210) == 0x44
    assert ram.peek(0x0211) == 0x44
    assert ram.peek(0x0212) == 0x44


def test_m6502_rol_zero_page_rotates_through_carry():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0x38,        # SEC
                0x26, 0x10,  # ROL $10
                0x00,        # BRK
            ]
        )
    )
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)
    ram.load(0x0010, b"\x80")

    cpu.run_cycles(16)

    assert ram.peek(0x0010) == 0x01
    assert (cpu.snapshot()["P"] & FLAG_C) != 0


def test_m6502_memory_shift_rotate_variants_update_memory_and_flags():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0x38,              # SEC
                0x06, 0x10,        # ASL $10      ; 0x40 -> 0x80
                0x26, 0x11,        # ROL $11      ; 0x80 + C(0) -> 0x00, C=1
                0x46, 0x12,        # LSR $12      ; 0x01 -> 0x00, C=1
                0x66, 0x13,        # ROR $13      ; 0x02 + C -> 0x81
                0x00,
            ]
        )
    )
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)
    ram.load(0x0010, b"\x40")
    ram.load(0x0011, b"\x80")
    ram.load(0x0012, b"\x01")
    ram.load(0x0013, b"\x02")
    cpu.run_cycles(32)
    snap = cpu.snapshot()

    assert ram.peek(0x0010) == 0x80
    assert ram.peek(0x0011) == 0x00
    assert ram.peek(0x0012) == 0x00
    assert ram.peek(0x0013) == 0x81
    assert (snap["P"] & FLAG_N) != 0


def test_m6502_inc_dec_variants_update_memory():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0xA2, 0x01,        # LDX #1
                0xE6, 0x10,        # INC $10
                0xF6, 0x10,        # INC $10,X -> $11
                0xC6, 0x12,        # DEC $12
                0xD6, 0x12,        # DEC $12,X -> $13
                0x00,
            ]
        )
    )
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)
    ram.load(0x0010, b"\x00")
    ram.load(0x0011, b"\x7F")
    ram.load(0x0012, b"\x01")
    ram.load(0x0013, b"\x00")
    cpu.run_cycles(32)

    assert ram.peek(0x0010) == 0x01
    assert ram.peek(0x0011) == 0x80
    assert ram.peek(0x0012) == 0x00
    assert ram.peek(0x0013) == 0xFF


def test_m6502_official_alu_addressing_modes_cover_zero_page_absolute_and_indexed():
    bus, cpu = _make_test_cpu(
        bytes(
            [
                0x18,              # CLC
                0xA9, 0x01,        # LDA #1
                0x65, 0x10,        # ADC $10
                0x75, 0x10,        # ADC $10,X
                0x6D, 0x00, 0x02,  # ADC $0200
                0x29, 0x0F,        # AND #$0F
                0x25, 0x11,        # AND $11
                0x0D, 0x02, 0x02,  # ORA $0202
                0x45, 0x12,        # EOR $12
                0xC5, 0x13,        # CMP $13
                0xE4, 0x14,        # CPX $14
                0xC4, 0x15,        # CPY $15
                0x00,
            ]
        )
    )
    ram = RAMBlock(0x0800)
    bus.map_block(0x0000, ram, size=ram.size)
    ram.load(0x0010, b"\x01\x0F\x03\x09\x01\x00")
    ram.load(0x0200, b"\x01\x00\x80")
    cpu.X = 1
    cpu.Y = 0

    cpu.run_cycles(64)
    snap = cpu.snapshot()

    assert snap["A"] == 0x81
    assert (snap["P"] & FLAG_C) != 0
    assert (snap["P"] & FLAG_Z) != 0


def test_m6502_brk_pushes_pc_and_status_and_vectors_via_fffe():
    bus = M6502Bus()
    ram = RAMBlock(0x0800)
    rom = _make_rom(
        bytes(
            [
                0xEA,              # F800: NOP
                0x00,              # F801: BRK
                0xEA,              # F802: BRK padding byte
                0xEA,              # F803
                0xEA,              # F804
                0x40,              # F805: RTI
            ]
        ),
        irq_vector=0xF805,
    )
    bus.map_block(0x0000, ram, size=ram.size)
    bus.map_block(0xF800, rom, size=rom.size)
    cpu = M6502Core(bus)

    cpu.step()  # NOP
    cycles = cpu.step()  # BRK

    assert cycles == 7
    assert cpu.snapshot()["PC"] == 0xF805
    assert cpu.snapshot()["SP"] == 0xFA
    assert ram.peek(0x01FD) == 0xF8
    assert ram.peek(0x01FC) == 0x03
    assert (ram.peek(0x01FB) & FLAG_B) != 0
    assert (ram.peek(0x01FB) & FLAG_U) != 0
    assert (cpu.snapshot()["P"] & FLAG_I) != 0


def test_m6502_rti_restores_pc_and_status_after_brk_handler():
    bus = M6502Bus()
    ram = RAMBlock(0x0800)
    rom = _make_rom(
        bytes(
            [
                0x18,              # F800: CLC
                0x00,              # F801: BRK
                0xEA,              # F802: padding
                0x38,              # F803: SEC
                0xEA,              # F804: NOP after RTI target
                0x40,              # F805: RTI
            ]
        ),
        irq_vector=0xF805,
    )
    bus.map_block(0x0000, ram, size=ram.size)
    bus.map_block(0xF800, rom, size=rom.size)
    cpu = M6502Core(bus)

    cpu.step()  # CLC
    cpu.step()  # BRK -> handler
    cycles = cpu.step()  # RTI
    snap = cpu.snapshot()

    assert cycles == 6
    assert snap["PC"] == 0xF803
    assert (snap["P"] & FLAG_C) == 0
    assert (snap["P"] & FLAG_B) == 0
    assert (snap["P"] & FLAG_U) != 0


def test_m6502_irq_after_cli_is_delayed_one_instruction_and_sei_uses_previous_mask():
    bus = M6502Bus()
    ram = RAMBlock(0x0800)
    rom = _make_rom(
        bytes(
            [
                0x58,              # F800: CLI
                0xEA,              # F801: NOP
                0x78,              # F802: SEI
                0xEA,              # F803: NOP
                0xEA,              # F804
                0x40,              # F805: RTI
            ]
        ),
        irq_vector=0xF805,
    )
    bus.map_block(0x0000, ram, size=ram.size)
    bus.map_block(0xF800, rom, size=rom.size)
    cpu = M6502Core(bus)

    cpu.step()  # CLI
    bus.request_irq()
    cycles = cpu.step()  # NOP at F801, IRQ still delayed by CLI
    assert cycles == 2
    assert cpu.snapshot()["PC"] == 0xF802

    cycles = cpu.step()  # service IRQ before SEI at F802
    snap = cpu.snapshot()

    assert cycles == 7
    assert snap["PC"] == 0xF805
    assert snap["SP"] == 0xFA
    assert ram.peek(0x01FD) == 0xF8
    assert ram.peek(0x01FC) == 0x02
    assert (ram.peek(0x01FB) & FLAG_B) == 0

    bus.clear_irq()
    cpu.step()  # RTI
    cpu.step()  # SEI
    bus.request_irq()
    cycles = cpu.step()  # IRQ still sees pre-SEI mask and fires before F803

    assert cycles == 7
    assert cpu.snapshot()["PC"] == 0xF805

    bus.clear_irq()
    cpu.step()  # RTI
    cycles = cpu.step()  # NOP at F803, IRQ now masked
    assert cycles == 2
    assert cpu.snapshot()["PC"] == 0xF804


def test_m6502_nmi_ignores_i_flag_and_uses_nmi_vector():
    bus = M6502Bus()
    ram = RAMBlock(0x0800)
    rom = _make_rom(
        bytes(
            [
                0x78,              # F800: SEI
                0xEA,              # F801: NOP
                0xEA,              # F802
                0xEA,              # F803
                0xEA,              # F804
                0x40,              # F805: RTI
                0xEA,              # F806
                0x40,              # F807: RTI for NMI
            ]
        ),
        nmi_vector=0xF807,
        irq_vector=0xF805,
    )
    bus.map_block(0x0000, ram, size=ram.size)
    bus.map_block(0xF800, rom, size=rom.size)
    cpu = M6502Core(bus)

    cpu.step()  # SEI
    bus.request_nmi()
    cycles = cpu.step()  # service NMI before NOP at F801
    snap = cpu.snapshot()

    assert cycles == 7
    assert snap["PC"] == 0xF807
    assert ram.peek(0x01FD) == 0xF8
    assert ram.peek(0x01FC) == 0x01
    assert (ram.peek(0x01FB) & FLAG_B) == 0


def test_m6502_plp_delays_irq_recognition_by_one_instruction():
    bus = M6502Bus()
    ram = RAMBlock(0x0800)
    rom = _make_rom(
        bytes(
            [
                0x08,              # F800: PHP
                0x28,              # F801: PLP
                0xEA,              # F802: NOP
                0xEA,              # F803
                0xEA,              # F804
                0x40,              # F805: RTI
            ]
        ),
        irq_vector=0xF805,
    )
    bus.map_block(0x0000, ram, size=ram.size)
    bus.map_block(0xF800, rom, size=rom.size)
    cpu = M6502Core(bus)

    cpu.P &= ~FLAG_I
    cpu.step()  # PHP pushes I=0
    cpu.P |= FLAG_I
    cpu.step()  # PLP restores I=0, but IRQ decision still uses old I=1 once
    bus.request_irq()

    cycles = cpu.step()  # NOP at F802, IRQ delayed by PLP
    assert cycles == 2
    assert cpu.snapshot()["PC"] == 0xF803

    cycles = cpu.step()  # IRQ now visible
    assert cycles == 7
    assert cpu.snapshot()["PC"] == 0xF805
