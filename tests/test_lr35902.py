from __future__ import annotations

from cpu.lr35902 import LR35902Bus, LR35902Core
from devices.gameboy import GameBoyCartridge
from machines.gameboy import DMG


def _make_test_rom(program: bytes, *, size: int = 0x8000, cartridge_type: int = 0x00) -> bytes:
    rom = bytearray(size)
    rom[0x0100 : 0x0100 + len(program)] = program
    rom[0x0134:0x013A] = b"TESTGB"
    rom[0x0147] = cartridge_type
    rom[0x0148] = 0x00 if size <= 0x8000 else 0x01
    rom[0x0149] = 0x00
    return bytes(rom)


def test_lr35902_can_store_and_load_through_memory():
    program = bytes(
        [
            0x21, 0x00, 0xC0,  # LD HL,C000h
            0x3E, 0x42,        # LD A,42h
            0x77,              # LD (HL),A
            0x3E, 0x00,        # LD A,00h
            0x7E,              # LD A,(HL)
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    cpu.run_cycles(64)
    snap = cpu.snapshot()

    assert bus.read8(0xC000) == 0x42
    assert snap["A"] == 0x42
    assert snap["halted"] is True


def test_lr35902_can_branch_with_jr_nz():
    program = bytes(
        [
            0x3E, 0x01,        # LD A,01h
            0xFE, 0x00,        # CP 00h
            0x20, 0x02,        # JR NZ,+2
            0x3E, 0x99,        # LD A,99h (skipped)
            0x3E, 0x55,        # LD A,55h
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    cpu.run_cycles(64)

    assert cpu.snapshot()["A"] == 0x55


def test_lr35902_ldh_roundtrip_works():
    program = bytes(
        [
            0x3E, 0x77,        # LD A,77h
            0xE0, 0x80,        # LDH (80h),A -> FF80
            0xAF,              # XOR A
            0xF0, 0x80,        # LDH A,(80h)
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    cpu.run_cycles(64)

    assert cpu.snapshot()["A"] == 0x77


def test_lr35902_daa_after_addition_produces_bcd_result():
    program = bytes(
        [
            0x3E, 0x15,        # LD A,15h
            0xC6, 0x27,        # ADD A,27h
            0x27,              # DAA
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    cpu.run_cycles(64)
    snap = cpu.snapshot()

    assert snap["A"] == 0x42
    assert (snap["F"] & 0x80) == 0
    assert (snap["F"] & 0x10) == 0


def test_lr35902_daa_after_subtraction_produces_bcd_result():
    program = bytes(
        [
            0x3E, 0x45,        # LD A,45h
            0xD6, 0x12,        # SUB 12h
            0x27,              # DAA
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    cpu.run_cycles(64)
    snap = cpu.snapshot()

    assert snap["A"] == 0x33
    assert (snap["F"] & 0x40) != 0


def test_lr35902_adc_immediate_uses_carry_flag():
    program = bytes(
        [
            0x3E, 0x0F,        # LD A,0Fh
            0x37,              # SCF
            0xCE, 0x00,        # ADC A,00h
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    cpu.run_cycles(64)
    snap = cpu.snapshot()

    assert snap["A"] == 0x10
    assert (snap["F"] & 0x20) != 0


def test_lr35902_sbc_immediate_uses_carry_flag():
    program = bytes(
        [
            0x3E, 0x10,        # LD A,10h
            0x37,              # SCF
            0xDE, 0x00,        # SBC A,00h
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    cpu.run_cycles(64)
    snap = cpu.snapshot()

    assert snap["A"] == 0x0F
    assert (snap["F"] & 0x20) != 0


def test_lr35902_add_sp_signed_updates_sp_and_flags():
    program = bytes(
        [
            0xE8, 0x08,        # ADD SP,+8
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)
    cpu.SP = 0xFFF8

    cpu.run_cycles(32)
    snap = cpu.snapshot()

    assert snap["SP"] == 0x0000
    assert (snap["F"] & 0x80) == 0
    assert (snap["F"] & 0x40) == 0
    assert (snap["F"] & 0x20) != 0
    assert (snap["F"] & 0x10) != 0


def test_lr35902_ld_hl_sp_plus_signed_stores_result_in_hl():
    program = bytes(
        [
            0xF8, 0xFE,        # LD HL,SP-2
            0x76,              # HALT
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)
    cpu.SP = 0x1234

    cpu.run_cycles(32)
    snap = cpu.snapshot()

    assert snap["H"] == 0x12
    assert snap["L"] == 0x32
    assert snap["SP"] == 0x1234
    assert (snap["F"] & 0x80) == 0
    assert (snap["F"] & 0x40) == 0


def test_lr35902_stop_consumes_padding_byte_and_halts():
    program = bytes(
        [
            0x10, 0x00,        # STOP 00
            0x00,              # NOP (not executed before halt)
        ]
    )
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(program)))
    cpu = LR35902Core(bus)

    used = cpu.step()
    snap = cpu.snapshot()

    assert used == 4
    assert snap["PC"] == 0x0102
    assert snap["halted"] is True


def test_gameboy_cartridge_mbc1_switches_rom_banks():
    rom = bytearray(0x10000)
    rom[0x0134:0x0138] = b"MBC1"
    rom[0x0147] = 0x01
    rom[0x0148] = 0x01
    rom[0x0149] = 0x00
    rom[0x4000] = 0x11
    rom[0x8000] = 0x22

    cart = GameBoyCartridge(bytes(rom))

    assert cart.read(0x4000) == 0x11
    cart.write(0x2000, 0x02)
    assert cart.read(0x4000) == 0x22


def test_gameboy_cartridge_mbc1_supports_external_ram_banking():
    rom = bytearray(0x10000)
    rom[0x0134:0x0138] = b"M1RA"
    rom[0x0147] = 0x03
    rom[0x0148] = 0x01
    rom[0x0149] = 0x03

    cart = GameBoyCartridge(bytes(rom))

    cart.write(0x0000, 0x0A)
    cart.write(0x6000, 0x01)
    cart.write(0x4000, 0x01)
    cart.write(0xA000, 0x55)
    cart.write(0x4000, 0x02)
    cart.write(0xA000, 0xAA)

    cart.write(0x4000, 0x01)
    assert cart.read(0xA000) == 0x55
    cart.write(0x4000, 0x02)
    assert cart.read(0xA000) == 0xAA


def test_gameboy_cartridge_reports_mbc3_type():
    rom = bytearray(0x8000)
    rom[0x0134:0x0138] = b"MBC3"
    rom[0x0147] = 0x13
    rom[0x0148] = 0x00
    rom[0x0149] = 0x03

    cart = GameBoyCartridge(bytes(rom))

    assert cart.cartridge_type_name == "MBC3+RAM+BATTERY"


def test_gameboy_cartridge_reports_mbc2_type():
    rom = bytearray(0x8000)
    rom[0x0134:0x0138] = b"MBC2"
    rom[0x0147] = 0x05
    rom[0x0148] = 0x00
    rom[0x0149] = 0x00

    cart = GameBoyCartridge(bytes(rom))

    assert cart.cartridge_type_name == "MBC2"


def test_gameboy_cartridge_mbc2_switches_rom_banks_only_when_a8_is_set():
    rom = bytearray(0x10000)
    rom[0x0134:0x0138] = b"MBC2"
    rom[0x0147] = 0x05
    rom[0x0148] = 0x01
    rom[0x0149] = 0x00
    rom[0x4000] = 0x11
    rom[0x8000] = 0x22

    cart = GameBoyCartridge(bytes(rom))

    assert cart.read(0x4000) == 0x11
    cart.write(0x0000, 0x02)
    assert cart.read(0x4000) == 0x11
    cart.write(0x2100, 0x02)
    assert cart.read(0x4000) == 0x22


def test_gameboy_cartridge_mbc2_exposes_internal_nibble_ram():
    rom = bytearray(0x8000)
    rom[0x0134:0x0138] = b"MBC2"
    rom[0x0147] = 0x06
    rom[0x0148] = 0x00
    rom[0x0149] = 0x00

    cart = GameBoyCartridge(bytes(rom))

    assert cart.read(0xA000) == 0xFF
    cart.write(0x0000, 0x0A)
    cart.write(0xA000, 0xAB)
    cart.write(0xA200, 0x05)

    assert cart.read(0xA000) == 0xF5
    assert cart.read(0xA200) == 0xF5


def test_gameboy_cartridge_reports_mbc5_type():
    rom = bytearray(0x8000)
    rom[0x0134:0x0138] = b"MBC5"
    rom[0x0147] = 0x1B
    rom[0x0148] = 0x00
    rom[0x0149] = 0x03

    cart = GameBoyCartridge(bytes(rom))

    assert cart.cartridge_type_name == "MBC5+RAM+BATTERY"


def test_gameboy_cartridge_mbc5_switches_rom_banks_with_ninth_bit():
    rom = bytearray(0x404000)
    rom[0x0134:0x0138] = b"MBC5"
    rom[0x0147] = 0x19
    rom[0x0148] = 0x07
    rom[0x0149] = 0x00
    rom[0x4000] = 0x01
    rom[0x8000] = 0x02
    rom[0x4000 * 0x100] = 0x33

    cart = GameBoyCartridge(bytes(rom))

    assert cart.read(0x4000) == 0x01
    cart.write(0x2000, 0x02)
    assert cart.read(0x4000) == 0x02
    cart.write(0x2000, 0x00)
    cart.write(0x3000, 0x01)
    assert cart.read(0x4000) == 0x33


def test_gameboy_cartridge_mbc5_supports_external_ram_banking():
    rom = bytearray(0x8000)
    rom[0x0134:0x0138] = b"MBC5"
    rom[0x0147] = 0x1B
    rom[0x0148] = 0x00
    rom[0x0149] = 0x03

    cart = GameBoyCartridge(bytes(rom))

    cart.write(0x0000, 0x0A)
    cart.write(0x4000, 0x01)
    cart.write(0xA000, 0x44)
    cart.write(0x4000, 0x02)
    cart.write(0xA000, 0x88)

    cart.write(0x4000, 0x01)
    assert cart.read(0xA000) == 0x44
    cart.write(0x4000, 0x02)
    assert cart.read(0xA000) == 0x88


def test_gameboy_cartridge_huc1_uses_mbc1_compatible_banking():
    rom = bytearray(0x10000)
    rom[0x0134:0x0138] = b"HUC1"
    rom[0x0147] = 0xFF
    rom[0x0148] = 0x01
    rom[0x0149] = 0x03
    rom[0x4000] = 0x11
    rom[0x8000] = 0x22

    cart = GameBoyCartridge(bytes(rom))

    assert cart.cartridge_type_name == "HuC1+RAM+BATTERY"
    assert cart.read(0x4000) == 0x11
    cart.write(0x2000, 0x02)
    assert cart.read(0x4000) == 0x22
    cart.write(0x4000, 0x01)
    cart.write(0xA000, 0x55)
    assert cart.read(0xA000) == 0x55


def test_gameboy_cartridge_huc1_exposes_ir_register_in_ir_mode():
    rom = bytearray(0x8000)
    rom[0x0134:0x0138] = b"HUC1"
    rom[0x0147] = 0xFF
    rom[0x0148] = 0x00
    rom[0x0149] = 0x03

    cart = GameBoyCartridge(bytes(rom))

    cart.write(0xA000, 0x12)
    assert cart.read(0xA000) == 0x12
    cart.write(0x0000, 0x0E)
    assert cart.read(0xA000) == 0xC0
    cart.write(0xA000, 0x01)
    assert cart.mapper.ir_transmitter_on is True


def test_gameboy_cartridge_mbc3_switches_rom_banks():
    rom = bytearray(0x10000)
    rom[0x0134:0x0138] = b"MBC3"
    rom[0x0147] = 0x13
    rom[0x0148] = 0x01
    rom[0x0149] = 0x03
    rom[0x4000] = 0x11
    rom[0x8000] = 0x22

    cart = GameBoyCartridge(bytes(rom))

    assert cart.read(0x4000) == 0x11
    cart.write(0x2000, 0x02)
    assert cart.read(0x4000) == 0x22


def test_gameboy_cartridge_mbc3_supports_external_ram_and_rtc_register_selection():
    rom = bytearray(0x10000)
    rom[0x0134:0x0138] = b"MBC3"
    rom[0x0147] = 0x13
    rom[0x0148] = 0x01
    rom[0x0149] = 0x03

    cart = GameBoyCartridge(bytes(rom))

    cart.write(0x0000, 0x0A)
    cart.write(0x4000, 0x01)
    cart.write(0xA000, 0x66)
    cart.write(0x4000, 0x02)
    cart.write(0xA000, 0x99)

    cart.write(0x4000, 0x01)
    assert cart.read(0xA000) == 0x66
    cart.write(0x4000, 0x02)
    assert cart.read(0xA000) == 0x99

    cart.write(0x4000, 0x08)
    assert cart.read(0xA000) == 0x00
    cart.write(0xA000, 0x12)
    assert cart.read(0xA000) == 0x12


def test_lr35902_reports_opcode_and_pc_for_unimplemented_instructions():
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(bytes([0xD3]))))
    cpu = LR35902Core(bus)

    try:
        cpu.step()
    except NotImplementedError as exc:
        message = str(exc)
        assert "LR35902 opcode D3" in message
        assert "PC=0100" in message
    else:
        raise AssertionError("expected NotImplementedError")


def test_lr35902_services_enabled_interrupts():
    machine = DMG(_make_test_rom(bytes([0x00])))
    machine.cpu.PC = 0x1234
    machine.cpu.SP = 0xFFFE
    machine.cpu.ime = True
    machine.bus.interrupt_enable = 0x01
    machine.interrupts.interrupt_flags = 0x01

    used = machine.cpu.step()

    assert used == 20
    assert machine.cpu.PC == 0x40
    assert machine.cpu.SP == 0xFFFC
    assert machine.bus.read8(0xFFFC) == 0x34
    assert machine.bus.read8(0xFFFD) == 0x12
    assert machine.interrupts.interrupt_flags & 0x01 == 0


def test_lr35902_reti_restores_pc_and_enables_ime():
    bus = LR35902Bus(GameBoyCartridge(_make_test_rom(bytes([0xD9]))))
    cpu = LR35902Core(bus)
    cpu.SP = 0xFFFC
    bus.write8(0xFFFC, 0x78)
    bus.write8(0xFFFD, 0x56)
    cpu.ime = False

    used = cpu.step()

    assert used == 16
    assert cpu.PC == 0x5678
    assert cpu.SP == 0xFFFE
    assert cpu.ime is True
