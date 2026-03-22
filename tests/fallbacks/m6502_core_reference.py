from __future__ import annotations

from cpu.m6502.bus import M6502Bus


FLAG_C = 0x01
FLAG_Z = 0x02
FLAG_I = 0x04
FLAG_D = 0x08
FLAG_B = 0x10
FLAG_U = 0x20
FLAG_V = 0x40
FLAG_N = 0x80


class M6502Core:
    def __init__(self, bus: M6502Bus, *, stop_on_brk: bool = False):
        self.bus = bus
        self.stop_on_brk = stop_on_brk
        self.reset()

    def reset(self):
        self.A = 0x00
        self.X = 0x00
        self.Y = 0x00
        self.SP = 0xFD
        self.P = FLAG_I | FLAG_U
        self.PC = self.bus.read16(0xFFFC)
        self.halted = False

    def _fetch8(self) -> int:
        value = self.bus.read8(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        return value

    def _fetch16(self) -> int:
        lo = self._fetch8()
        hi = self._fetch8()
        return lo | (hi << 8)

    def _set_zn(self, value: int) -> None:
        value &= 0xFF
        self.P &= ~(FLAG_Z | FLAG_N)
        if value == 0:
            self.P |= FLAG_Z
        if value & 0x80:
            self.P |= FLAG_N

    def _set_flag(self, mask: int, enabled: bool) -> None:
        if enabled:
            self.P |= mask
        else:
            self.P &= ~mask

    def _read_zp(self) -> int:
        return self.bus.read8(self._fetch8())

    def _read_zp_x(self) -> int:
        return self.bus.read8((self._fetch8() + self.X) & 0xFF)

    def _read_zp_y(self) -> int:
        return self.bus.read8((self._fetch8() + self.Y) & 0xFF)

    def _read_abs(self) -> int:
        return self.bus.read8(self._fetch16())

    def _read_abs_x(self) -> int:
        return self.bus.read8((self._fetch16() + self.X) & 0xFFFF)

    def _read_abs_y(self) -> int:
        return self.bus.read8((self._fetch16() + self.Y) & 0xFFFF)

    def _read_ind_x(self) -> int:
        zp_addr = (self._fetch8() + self.X) & 0xFF
        addr = self.bus.read8(zp_addr) | (self.bus.read8((zp_addr + 1) & 0xFF) << 8)
        return self.bus.read8(addr)

    def _read_ind_y(self) -> int:
        zp_addr = self._fetch8()
        base = self.bus.read8(zp_addr) | (self.bus.read8((zp_addr + 1) & 0xFF) << 8)
        return self.bus.read8((base + self.Y) & 0xFFFF)

    def _write_zp(self, value: int) -> None:
        self.bus.write8(self._fetch8(), value)

    def _write_zp_x(self, value: int) -> None:
        self.bus.write8((self._fetch8() + self.X) & 0xFF, value)

    def _write_zp_y(self, value: int) -> None:
        self.bus.write8((self._fetch8() + self.Y) & 0xFF, value)

    def _write_abs(self, value: int) -> None:
        self.bus.write8(self._fetch16(), value)

    def _write_abs_x(self, value: int) -> None:
        self.bus.write8((self._fetch16() + self.X) & 0xFFFF, value)

    def _write_abs_y(self, value: int) -> None:
        self.bus.write8((self._fetch16() + self.Y) & 0xFFFF, value)

    def _write_ind_x(self, value: int) -> None:
        zp_addr = (self._fetch8() + self.X) & 0xFF
        addr = self.bus.read8(zp_addr) | (self.bus.read8((zp_addr + 1) & 0xFF) << 8)
        self.bus.write8(addr, value)

    def _write_ind_y(self, value: int) -> None:
        zp_addr = self._fetch8()
        base = self.bus.read8(zp_addr) | (self.bus.read8((zp_addr + 1) & 0xFF) << 8)
        self.bus.write8((base + self.Y) & 0xFFFF, value)

    def _push8(self, value: int) -> None:
        self.bus.write8(0x0100 | self.SP, value & 0xFF)
        self.SP = (self.SP - 1) & 0xFF

    def _pop8(self) -> int:
        self.SP = (self.SP + 1) & 0xFF
        return self.bus.read8(0x0100 | self.SP)

    def _push16(self, value: int) -> None:
        self._push8((value >> 8) & 0xFF)
        self._push8(value & 0xFF)

    def _pop16(self) -> int:
        lo = self._pop8()
        hi = self._pop8()
        return lo | (hi << 8)

    def _adc(self, value: int) -> None:
        value &= 0xFF
        carry_in = 1 if (self.P & FLAG_C) else 0
        total = self.A + value + carry_in
        result = total & 0xFF
        overflow = (~(self.A ^ value) & (self.A ^ result) & 0x80) != 0
        if self.P & FLAG_D:
            lo = (self.A & 0x0F) + (value & 0x0F) + carry_in
            carry_lo = 0
            if lo > 9:
                lo += 6
                carry_lo = 1
            hi = (self.A >> 4) + (value >> 4) + carry_lo
            self._set_flag(FLAG_C, hi > 9)
            if hi > 9:
                hi += 6
            self.A = ((hi << 4) | (lo & 0x0F)) & 0xFF
        else:
            self._set_flag(FLAG_C, total > 0xFF)
            self.A = result
        self._set_flag(FLAG_V, overflow)
        self._set_zn(self.A)

    def _sbc(self, value: int) -> None:
        value &= 0xFF
        carry_in = 1 if (self.P & FLAG_C) else 0
        total = self.A - value - (1 - carry_in)
        result = total & 0xFF
        overflow = ((self.A ^ result) & (self.A ^ value) & 0x80) != 0
        if self.P & FLAG_D:
            borrow = 1 - carry_in
            lo = (self.A & 0x0F) - (value & 0x0F) - borrow
            borrow_hi = 0
            if lo < 0:
                lo -= 6
                borrow_hi = 1
            hi = (self.A >> 4) - (value >> 4) - borrow_hi
            if hi < 0:
                hi -= 6
            self.A = ((hi << 4) | (lo & 0x0F)) & 0xFF
        else:
            self.A = result
        self._set_flag(FLAG_C, total >= 0)
        self._set_flag(FLAG_V, overflow)
        self._set_zn(self.A)

    def _compare(self, reg: int, value: int) -> None:
        result = (reg - (value & 0xFF)) & 0x1FF
        self._set_flag(FLAG_C, reg >= (value & 0xFF))
        self._set_zn(result & 0xFF)

    def _branch(self, condition: bool) -> int:
        offset = self._fetch8()
        if not condition:
            return 2
        old_pc = self.PC
        if offset & 0x80:
            offset -= 0x100
        self.PC = (self.PC + offset) & 0xFFFF
        if (old_pc & 0xFF00) != (self.PC & 0xFF00):
            return 4
        return 3

    def _asl_value(self, value: int) -> int:
        self._set_flag(FLAG_C, (value & 0x80) != 0)
        value = (value << 1) & 0xFF
        self._set_zn(value)
        return value

    def _lsr_value(self, value: int) -> int:
        self._set_flag(FLAG_C, (value & 0x01) != 0)
        value = (value >> 1) & 0xFF
        self._set_zn(value)
        return value

    def _rol_value(self, value: int) -> int:
        carry_in = 1 if (self.P & FLAG_C) else 0
        self._set_flag(FLAG_C, (value & 0x80) != 0)
        value = ((value << 1) | carry_in) & 0xFF
        self._set_zn(value)
        return value

    def _ror_value(self, value: int) -> int:
        carry_in = 0x80 if (self.P & FLAG_C) else 0x00
        self._set_flag(FLAG_C, (value & 0x01) != 0)
        value = ((value >> 1) | carry_in) & 0xFF
        self._set_zn(value)
        return value

    def _inc_value(self, value: int) -> int:
        value = (value + 1) & 0xFF
        self._set_zn(value)
        return value

    def _dec_value(self, value: int) -> int:
        value = (value - 1) & 0xFF
        self._set_zn(value)
        return value

    def _service_interrupt(self, vector: int, *, pushed_status: int) -> int:
        self._push16(self.PC)
        self._push8((pushed_status | FLAG_U) & 0xFF)
        self.P = (self.P | FLAG_I | FLAG_U) & ~FLAG_B
        self.PC = self.bus.read16(vector)
        return 7

    def _service_pending_interrupts(self) -> int | None:
        if self.bus.pull_nmi():
            return self._service_interrupt(0xFFFA, pushed_status=self.P & ~FLAG_B)
        if self.bus.irq_pending and (self.P & FLAG_I) == 0:
            return self._service_interrupt(0xFFFE, pushed_status=self.P & ~FLAG_B)
        return None

    def step(self) -> int:
        if self.halted:
            return 1

        interrupt_cycles = self._service_pending_interrupts()
        if interrupt_cycles is not None:
            return interrupt_cycles

        op = self._fetch8()

        if op == 0x00:  # BRK
            if self.stop_on_brk:
                self.halted = True
                return 7
            self.PC = (self.PC + 1) & 0xFFFF
            return self._service_interrupt(0xFFFE, pushed_status=self.P | FLAG_B)
        if op == 0x40:  # RTI
            self.P = (self._pop8() | FLAG_U) & ~FLAG_B
            self.PC = self._pop16()
            return 6
        if op == 0x01:  # ORA (zp,X)
            self.A |= self._read_ind_x()
            self._set_zn(self.A)
            return 6
        if op == 0x05:  # ORA zp
            self.A |= self._read_zp()
            self._set_zn(self.A)
            return 3
        if op == 0x0D:  # ORA abs
            self.A |= self._read_abs()
            self._set_zn(self.A)
            return 4
        if op == 0x11:  # ORA (zp),Y
            self.A |= self._read_ind_y()
            self._set_zn(self.A)
            return 5
        if op == 0x15:  # ORA zp,X
            self.A |= self._read_zp_x()
            self._set_zn(self.A)
            return 4
        if op == 0x17:  # unofficial SLO zp,X
            addr = (self._fetch8() + self.X) & 0xFF
            value = self._asl_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            self.A |= value
            self._set_zn(self.A)
            return 6
        if op == 0x04 or op == 0x44 or op == 0x64:  # unofficial NOP zp
            self._fetch8()
            return 3
        if op == 0x1F:  # unofficial SLO abs,X
            addr = (self._fetch16() + self.X) & 0xFFFF
            value = self._asl_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            self.A |= value
            self._set_zn(self.A)
            return 7
        if op == 0x14 or op == 0x34 or op == 0x54 or op == 0x74 or op == 0xD4 or op == 0xF4:  # unofficial NOP zp,X
            self._fetch8()
            return 4
        if op == 0x06:  # ASL zp
            addr = self._fetch8()
            value = self._asl_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 5
        if op == 0x0C:  # unofficial NOP abs
            self._fetch16()
            return 4
        if op == 0x0E:  # ASL abs
            addr = self._fetch16()
            value = self._asl_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0x16:  # ASL zp,X
            addr = (self._fetch8() + self.X) & 0xFF
            value = self._asl_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0x24:  # BIT zp
            value = self._read_zp()
            self._set_flag(FLAG_Z, (self.A & value) == 0)
            self._set_flag(FLAG_V, (value & 0x40) != 0)
            self._set_flag(FLAG_N, (value & 0x80) != 0)
            return 3
        if op == 0x26:  # ROL zp
            addr = self._fetch8()
            value = self._rol_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 5
        if op == 0x2E:  # ROL abs
            addr = self._fetch16()
            value = self._rol_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0x2C:  # BIT abs
            value = self._read_abs()
            self._set_flag(FLAG_Z, (self.A & value) == 0)
            self._set_flag(FLAG_V, (value & 0x40) != 0)
            self._set_flag(FLAG_N, (value & 0x80) != 0)
            return 4
        if op == 0x2A:  # ROL A
            self.A = self._rol_value(self.A)
            return 2
        if op == 0x36:  # ROL zp,X
            addr = (self._fetch8() + self.X) & 0xFF
            value = self._rol_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0x46:  # LSR zp
            addr = self._fetch8()
            value = self._lsr_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 5
        if op == 0x4E:  # LSR abs
            addr = self._fetch16()
            value = self._lsr_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0x4A:  # LSR A
            self.A = self._lsr_value(self.A)
            return 2
        if op == 0x56:  # LSR zp,X
            addr = (self._fetch8() + self.X) & 0xFF
            value = self._lsr_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0x5D:  # EOR abs,X
            self.A ^= self._read_abs_x()
            self._set_zn(self.A)
            return 4
        if op == 0x1C or op == 0x3C or op == 0x5C or op == 0x7C or op == 0xDC or op == 0xFC:  # unofficial NOP abs,X
            self._fetch16()
            return 4
        if op == 0x55:  # EOR zp,X
            self.A ^= self._read_zp_x()
            self._set_zn(self.A)
            return 4
        if op == 0x4D:  # EOR abs
            self.A ^= self._read_abs()
            self._set_zn(self.A)
            return 4
        if op == 0x6A:  # ROR A
            self.A = self._ror_value(self.A)
            return 2
        if op == 0x66:  # ROR zp
            addr = self._fetch8()
            value = self._ror_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 5
        if op == 0x0A:  # ASL A
            self.A = self._asl_value(self.A)
            return 2
        if op == 0x6E:  # ROR abs
            addr = self._fetch16()
            value = self._ror_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0x76:  # ROR zp,X
            addr = (self._fetch8() + self.X) & 0xFF
            value = self._ror_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0xEA:  # NOP
            return 2
        if op == 0x80 or op == 0x82 or op == 0x89 or op == 0xC2 or op == 0xE2:  # unofficial NOP #imm
            self._fetch8()
            return 2
        if op == 0xEB:  # unofficial SBC #imm
            self._sbc(self._fetch8())
            return 2
        if op == 0x18:  # CLC
            self._set_flag(FLAG_C, False)
            return 2
        if op == 0x38:  # SEC
            self._set_flag(FLAG_C, True)
            return 2
        if op == 0x58:  # CLI
            self._set_flag(FLAG_I, False)
            return 2
        if op == 0x78:  # SEI
            self._set_flag(FLAG_I, True)
            return 2
        if op == 0xB8:  # CLV
            self._set_flag(FLAG_V, False)
            return 2
        if op == 0xD8:  # CLD
            self._set_flag(FLAG_D, False)
            return 2
        if op == 0xF8:  # SED
            self._set_flag(FLAG_D, True)
            return 2
        if op == 0xA9:  # LDA #imm
            self.A = self._fetch8()
            self._set_zn(self.A)
            return 2
        if op == 0xA1:  # LDA (zp,X)
            self.A = self._read_ind_x()
            self._set_zn(self.A)
            return 6
        if op == 0xA5:  # LDA zp
            self.A = self._read_zp()
            self._set_zn(self.A)
            return 3
        if op == 0xB1:  # LDA (zp),Y
            self.A = self._read_ind_y()
            self._set_zn(self.A)
            return 5
        if op == 0xB5:  # LDA zp,X
            self.A = self._read_zp_x()
            self._set_zn(self.A)
            return 4
        if op == 0xAD:  # LDA abs
            self.A = self._read_abs()
            self._set_zn(self.A)
            return 4
        if op == 0xBD:  # LDA abs,X
            self.A = self._read_abs_x()
            self._set_zn(self.A)
            return 4
        if op == 0xB9:  # LDA abs,Y
            self.A = self._read_abs_y()
            self._set_zn(self.A)
            return 4
        if op == 0xA2:  # LDX #imm
            self.X = self._fetch8()
            self._set_zn(self.X)
            return 2
        if op == 0xA6:  # LDX zp
            self.X = self._read_zp()
            self._set_zn(self.X)
            return 3
        if op == 0xB6:  # LDX zp,Y
            self.X = self._read_zp_y()
            self._set_zn(self.X)
            return 4
        if op == 0xAE:  # LDX abs
            self.X = self._read_abs()
            self._set_zn(self.X)
            return 4
        if op == 0xBE:  # LDX abs,Y
            self.X = self._read_abs_y()
            self._set_zn(self.X)
            return 4
        if op == 0xA0:  # LDY #imm
            self.Y = self._fetch8()
            self._set_zn(self.Y)
            return 2
        if op == 0xA4:  # LDY zp
            self.Y = self._read_zp()
            self._set_zn(self.Y)
            return 3
        if op == 0xB4:  # LDY zp,X
            self.Y = self._read_zp_x()
            self._set_zn(self.Y)
            return 4
        if op == 0xAC:  # LDY abs
            self.Y = self._read_abs()
            self._set_zn(self.Y)
            return 4
        if op == 0xBC:  # LDY abs,X
            self.Y = self._read_abs_x()
            self._set_zn(self.Y)
            return 4
        if op == 0x85:  # STA zp
            self._write_zp(self.A)
            return 3
        if op == 0x81:  # STA (zp,X)
            self._write_ind_x(self.A)
            return 6
        if op == 0x91:  # STA (zp),Y
            self._write_ind_y(self.A)
            return 6
        if op == 0x95:  # STA zp,X
            self._write_zp_x(self.A)
            return 4
        if op == 0x8D:  # STA abs
            self._write_abs(self.A)
            return 4
        if op == 0x9D:  # STA abs,X
            self._write_abs_x(self.A)
            return 5
        if op == 0x99:  # STA abs,Y
            self._write_abs_y(self.A)
            return 5
        if op == 0x86:  # STX zp
            self._write_zp(self.X)
            return 3
        if op == 0x96:  # STX zp,Y
            self._write_zp_y(self.X)
            return 4
        if op == 0x8E:  # STX abs
            self._write_abs(self.X)
            return 4
        if op == 0x84:  # STY zp
            self._write_zp(self.Y)
            return 3
        if op == 0x94:  # STY zp,X
            self._write_zp_x(self.Y)
            return 4
        if op == 0x8C:  # STY abs
            self._write_abs(self.Y)
            return 4
        if op == 0xAA:  # TAX
            self.X = self.A
            self._set_zn(self.X)
            return 2
        if op == 0x8A:  # TXA
            self.A = self.X
            self._set_zn(self.A)
            return 2
        if op == 0xA8:  # TAY
            self.Y = self.A
            self._set_zn(self.Y)
            return 2
        if op == 0x98:  # TYA
            self.A = self.Y
            self._set_zn(self.A)
            return 2
        if op == 0xBA:  # TSX
            self.X = self.SP
            self._set_zn(self.X)
            return 2
        if op == 0x9A:  # TXS
            self.SP = self.X
            return 2
        if op == 0xE8:  # INX
            self.X = (self.X + 1) & 0xFF
            self._set_zn(self.X)
            return 2
        if op == 0xEE:  # INC abs
            addr = self._fetch16()
            value = (self.bus.read8(addr) + 1) & 0xFF
            self.bus.write8(addr, value)
            self._set_zn(value)
            return 6
        if op == 0xCA:  # DEX
            self.X = (self.X - 1) & 0xFF
            self._set_zn(self.X)
            return 2
        if op == 0xC8:  # INY
            self.Y = (self.Y + 1) & 0xFF
            self._set_zn(self.Y)
            return 2
        if op == 0x88:  # DEY
            self.Y = (self.Y - 1) & 0xFF
            self._set_zn(self.Y)
            return 2
        if op == 0x48:  # PHA
            self._push8(self.A)
            return 3
        if op == 0x68:  # PLA
            self.A = self._pop8()
            self._set_zn(self.A)
            return 4
        if op == 0x08:  # PHP
            self._push8(self.P | FLAG_B | FLAG_U)
            return 3
        if op == 0x28:  # PLP
            self.P = (self._pop8() | FLAG_U) & 0xEF
            return 4
        if op == 0x69:  # ADC #imm
            self._adc(self._fetch8())
            return 2
        if op == 0x61:  # ADC (zp,X)
            self._adc(self._read_ind_x())
            return 6
        if op == 0x65:  # ADC zp
            self._adc(self._read_zp())
            return 3
        if op == 0x71:  # ADC (zp),Y
            self._adc(self._read_ind_y())
            return 5
        if op == 0x6D:  # ADC abs
            self._adc(self._read_abs())
            return 4
        if op == 0x75:  # ADC zp,X
            self._adc(self._read_zp_x())
            return 4
        if op == 0x7D:  # ADC abs,X
            self._adc(self._read_abs_x())
            return 4
        if op == 0x79:  # ADC abs,Y
            self._adc(self._read_abs_y())
            return 4
        if op == 0xE9:  # SBC #imm
            self._sbc(self._fetch8())
            return 2
        if op == 0xE1:  # SBC (zp,X)
            self._sbc(self._read_ind_x())
            return 6
        if op == 0xE5:  # SBC zp
            self._sbc(self._read_zp())
            return 3
        if op == 0xF1:  # SBC (zp),Y
            self._sbc(self._read_ind_y())
            return 5
        if op == 0xED:  # SBC abs
            self._sbc(self._read_abs())
            return 4
        if op == 0xF9:  # SBC abs,Y
            self._sbc(self._read_abs_y())
            return 4
        if op == 0xF5:  # SBC zp,X
            self._sbc(self._read_zp_x())
            return 4
        if op == 0xFD:  # SBC abs,X
            self._sbc(self._read_abs_x())
            return 4
        if op == 0x29:  # AND #imm
            self.A &= self._fetch8()
            self._set_zn(self.A)
            return 2
        if op == 0x25:  # AND zp
            self.A &= self._read_zp()
            self._set_zn(self.A)
            return 3
        if op == 0x2D:  # AND abs
            self.A &= self._read_abs()
            self._set_zn(self.A)
            return 4
        if op == 0x35:  # AND zp,X
            self.A &= self._read_zp_x()
            self._set_zn(self.A)
            return 4
        if op == 0x21:  # AND (zp,X)
            self.A &= self._read_ind_x()
            self._set_zn(self.A)
            return 6
        if op == 0x31:  # AND (zp),Y
            self.A &= self._read_ind_y()
            self._set_zn(self.A)
            return 5
        if op == 0x39:  # AND abs,Y
            self.A &= self._read_abs_y()
            self._set_zn(self.A)
            return 4
        if op == 0x3D:  # AND abs,X
            self.A &= self._read_abs_x()
            self._set_zn(self.A)
            return 4
        if op == 0x09:  # ORA #imm
            self.A |= self._fetch8()
            self._set_zn(self.A)
            return 2
        if op == 0x19:  # ORA abs,Y
            self.A |= self._read_abs_y()
            self._set_zn(self.A)
            return 4
        if op == 0x1D:  # ORA abs,X
            self.A |= self._read_abs_x()
            self._set_zn(self.A)
            return 4
        if op == 0x49:  # EOR #imm
            self.A ^= self._fetch8()
            self._set_zn(self.A)
            return 2
        if op == 0x45:  # EOR zp
            self.A ^= self._read_zp()
            self._set_zn(self.A)
            return 3
        if op == 0x41:  # EOR (zp,X)
            self.A ^= self._read_ind_x()
            self._set_zn(self.A)
            return 6
        if op == 0x51:  # EOR (zp),Y
            self.A ^= self._read_ind_y()
            self._set_zn(self.A)
            return 5
        if op == 0x59:  # EOR abs,Y
            self.A ^= self._read_abs_y()
            self._set_zn(self.A)
            return 4
        if op == 0xC9:  # CMP #imm
            self._compare(self.A, self._fetch8())
            return 2
        if op == 0xC5:  # CMP zp
            self._compare(self.A, self._read_zp())
            return 3
        if op == 0xC1:  # CMP (zp,X)
            self._compare(self.A, self._read_ind_x())
            return 6
        if op == 0xD1:  # CMP (zp),Y
            self._compare(self.A, self._read_ind_y())
            return 5
        if op == 0xD5:  # CMP zp,X
            self._compare(self.A, self._read_zp_x())
            return 4
        if op == 0xCD:  # CMP abs
            self._compare(self.A, self._read_abs())
            return 4
        if op == 0xD9:  # CMP abs,Y
            self._compare(self.A, self._read_abs_y())
            return 4
        if op == 0xDD:  # CMP abs,X
            self._compare(self.A, self._read_abs_x())
            return 4
        if op == 0xE0:  # CPX #imm
            self._compare(self.X, self._fetch8())
            return 2
        if op == 0xE4:  # CPX zp
            self._compare(self.X, self._read_zp())
            return 3
        if op == 0xEC:  # CPX abs
            self._compare(self.X, self._read_abs())
            return 4
        if op == 0xC0:  # CPY #imm
            self._compare(self.Y, self._fetch8())
            return 2
        if op == 0xC4:  # CPY zp
            self._compare(self.Y, self._read_zp())
            return 3
        if op == 0xCC:  # CPY abs
            self._compare(self.Y, self._read_abs())
            return 4
        if op == 0x20:  # JSR abs
            target = self._fetch16()
            self._push16((self.PC - 1) & 0xFFFF)
            self.PC = target
            return 6
        if op == 0x1E:  # ASL abs,X
            addr = (self._fetch16() + self.X) & 0xFFFF
            value = self._asl_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 7
        if op == 0x3E:  # ROL abs,X
            addr = (self._fetch16() + self.X) & 0xFFFF
            value = self._rol_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 7
        if op == 0x5E:  # LSR abs,X
            addr = (self._fetch16() + self.X) & 0xFFFF
            value = self._lsr_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 7
        if op == 0x7E:  # ROR abs,X
            addr = (self._fetch16() + self.X) & 0xFFFF
            value = self._ror_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 7
        if op == 0x4C:  # JMP abs
            self.PC = self._fetch16()
            return 3
        if op == 0x6C:  # JMP (abs)
            ptr = self._fetch16()
            lo = self.bus.read8(ptr)
            hi = self.bus.read8((ptr & 0xFF00) | ((ptr + 1) & 0x00FF))
            self.PC = lo | (hi << 8)
            return 5
        if op == 0x60:  # RTS
            self.PC = (self._pop16() + 1) & 0xFFFF
            return 6
        if op == 0xC6:  # DEC zp
            addr = self._fetch8()
            value = self._dec_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 5
        if op == 0xCE:  # DEC abs
            addr = self._fetch16()
            value = self._dec_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0xD6:  # DEC zp,X
            addr = (self._fetch8() + self.X) & 0xFF
            value = self._dec_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0xDE:  # DEC abs,X
            addr = (self._fetch16() + self.X) & 0xFFFF
            value = self._dec_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 7
        if op == 0xE6:  # INC zp
            addr = self._fetch8()
            value = self._inc_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 5
        if op == 0x10:  # BPL
            return self._branch((self.P & FLAG_N) == 0)
        if op == 0xF6:  # INC zp,X
            addr = (self._fetch8() + self.X) & 0xFF
            value = self._inc_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 6
        if op == 0xFE:  # INC abs,X
            addr = (self._fetch16() + self.X) & 0xFFFF
            value = self._inc_value(self.bus.read8(addr))
            self.bus.write8(addr, value)
            return 7
        if op == 0x30:  # BMI
            return self._branch((self.P & FLAG_N) != 0)
        if op == 0x90:  # BCC
            return self._branch((self.P & FLAG_C) == 0)
        if op == 0x50:  # BVC
            return self._branch((self.P & FLAG_V) == 0)
        if op == 0x70:  # BVS
            return self._branch((self.P & FLAG_V) != 0)
        if op == 0xB0:  # BCS
            return self._branch((self.P & FLAG_C) != 0)
        if op == 0xD0:  # BNE
            return self._branch((self.P & FLAG_Z) == 0)
        if op == 0xF0:  # BEQ
            return self._branch((self.P & FLAG_Z) != 0)

        raise NotImplementedError(f"opcode 6502 no implementado: {op:02X}")

    def run_cycles(self, cycles: int) -> int:
        used = 0
        while used < cycles:
            used += self.step()
            if self.halted:
                break
        return used

    def snapshot(self) -> dict:
        return {
            "A": self.A,
            "X": self.X,
            "Y": self.Y,
            "SP": self.SP,
            "PC": self.PC,
            "P": self.P,
            "halted": self.halted,
            "irq_pending": self.bus.irq_pending,
            "nmi_pending": self.bus.nmi_pending,
        }
