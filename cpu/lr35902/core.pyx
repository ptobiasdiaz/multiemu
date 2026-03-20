# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""LR35902 core scaffolding.

The Game Boy CPU is similar to the Z80, but it is different enough that the
execution core lives in its own module instead of subclassing the Z80.
"""

from __future__ import annotations


cdef class LR35902Core:
    """Cythonized LR35902 CPU core."""

    cdef public object bus
    cdef public int A, F, B, C, D, E, H, L, SP, PC, cycles
    cdef public bint halted, ime

    def __init__(self, bus):
        self.bus = bus
        self.reset()

    cpdef void reset(self):
        self.A = 0x01
        self.F = 0xB0
        self.B = 0x00
        self.C = 0x13
        self.D = 0x00
        self.E = 0xD8
        self.H = 0x01
        self.L = 0x4D
        self.SP = 0xFFFE
        self.PC = 0x0100
        self.halted = False
        self.ime = False
        self.cycles = 0

    cdef inline int _get_BC(self):
        return (self.B << 8) | self.C

    cdef inline int _get_DE(self):
        return (self.D << 8) | self.E

    cdef inline int _get_HL(self):
        return (self.H << 8) | self.L

    cdef inline void _set_BC(self, int value):
        self.B = (value >> 8) & 0xFF
        self.C = value & 0xFF

    cdef inline void _set_DE(self, int value):
        self.D = (value >> 8) & 0xFF
        self.E = value & 0xFF

    cdef inline void _set_HL(self, int value):
        self.H = (value >> 8) & 0xFF
        self.L = value & 0xFF

    cdef inline int _fetch8(self):
        cdef int value = self.bus.read8(self.PC)
        self.PC = (self.PC + 1) & 0xFFFF
        return value

    cdef inline int _fetch16(self):
        cdef int lo = self._fetch8()
        cdef int hi = self._fetch8()
        return lo | (hi << 8)

    cdef inline int _pending_interrupt_mask(self):
        return self.bus.read8(0xFFFF) & self.bus.read8(0xFF0F) & 0x1F

    cdef int _service_interrupt(self, int pending):
        cdef tuple vectors = (0x40, 0x48, 0x50, 0x58, 0x60)
        cdef int bit, vector, mask
        for bit, vector in enumerate(vectors):
            mask = 1 << bit
            if pending & mask:
                self.ime = False
                self.halted = False
                self.bus.write8(0xFF0F, self.bus.read8(0xFF0F) & ~mask)
                self._push16(self.PC)
                self.PC = vector
                self.cycles += 20
                return 20
        return 0

    def _set_flags(self, z=None, n=None, h=None, c=None):
        cdef int f = self.F
        if z is not None:
            f = (f | 0x80) if z else (f & ~0x80)
        if n is not None:
            f = (f | 0x40) if n else (f & ~0x40)
        if h is not None:
            f = (f | 0x20) if h else (f & ~0x20)
        if c is not None:
            f = (f | 0x10) if c else (f & ~0x10)
        self.F = f & 0xF0

    cdef inline bint _get_flag_z(self):
        return (self.F & 0x80) != 0

    cdef inline bint _get_flag_c(self):
        return (self.F & 0x10) != 0

    cdef void _add16_hl(self, int value):
        cdef int hl = self._get_HL()
        cdef int result = hl + value
        self._set_flags(
            n=False,
            h=((hl & 0x0FFF) + (value & 0x0FFF)) > 0x0FFF,
            c=result > 0xFFFF,
        )
        self._set_HL(result & 0xFFFF)

    cdef int _add_sp_signed(self, int offset_byte):
        cdef int offset = offset_byte if offset_byte < 0x80 else offset_byte - 0x100
        cdef int sp = self.SP
        cdef int result = (sp + offset) & 0xFFFF
        cdef int unsigned_offset = offset_byte & 0xFF
        self._set_flags(
            z=False,
            n=False,
            h=((sp & 0x0F) + (unsigned_offset & 0x0F)) > 0x0F,
            c=((sp & 0xFF) + unsigned_offset) > 0xFF,
        )
        return result

    cdef void _push16(self, int value):
        self.SP = (self.SP - 1) & 0xFFFF
        self.bus.write8(self.SP, (value >> 8) & 0xFF)
        self.SP = (self.SP - 1) & 0xFFFF
        self.bus.write8(self.SP, value & 0xFF)

    cdef int _pop16(self):
        cdef int lo = self.bus.read8(self.SP)
        self.SP = (self.SP + 1) & 0xFFFF
        cdef int hi = self.bus.read8(self.SP)
        self.SP = (self.SP + 1) & 0xFFFF
        return lo | (hi << 8)

    cdef void _add8(self, int value, int carry=0):
        cdef int a = self.A
        cdef int result = a + value + carry
        self.A = result & 0xFF
        self._set_flags(
            z=self.A == 0,
            n=False,
            h=((a & 0x0F) + (value & 0x0F) + carry) > 0x0F,
            c=result > 0xFF,
        )

    cdef void _sub8(self, int value, int carry=0):
        cdef int a = self.A
        cdef int result = a - value - carry
        self.A = result & 0xFF
        self._set_flags(
            z=self.A == 0,
            n=True,
            h=((a & 0x0F) - (value & 0x0F) - carry) < 0,
            c=result < 0,
        )

    cdef void _cp8(self, int value):
        cdef int a = self.A
        cdef int result = a - value
        self._set_flags(
            z=(result & 0xFF) == 0,
            n=True,
            h=((a & 0x0F) - (value & 0x0F)) < 0,
            c=result < 0,
        )

    cdef int _inc8(self, int value):
        cdef int result = (value + 1) & 0xFF
        self._set_flags(
            z=result == 0,
            n=False,
            h=((value & 0x0F) + 1) > 0x0F,
        )
        return result

    cdef int _dec8(self, int value):
        cdef int result = (value - 1) & 0xFF
        self._set_flags(
            z=result == 0,
            n=True,
            h=(value & 0x0F) == 0,
        )
        return result

    cdef void _daa(self):
        cdef int adjust = 0
        cdef bint carry = self._get_flag_c()
        cdef bint subtract = (self.F & 0x40) != 0
        cdef bint half_carry = (self.F & 0x20) != 0

        if not subtract:
            if carry or self.A > 0x99:
                adjust |= 0x60
                carry = True
            if half_carry or (self.A & 0x0F) > 0x09:
                adjust |= 0x06
            self.A = (self.A + adjust) & 0xFF
        else:
            if carry:
                adjust |= 0x60
            if half_carry:
                adjust |= 0x06
            self.A = (self.A - adjust) & 0xFF

        self._set_flags(
            z=self.A == 0,
            h=False,
            c=carry,
        )

    cdef int _cb_rlc(self, int value):
        cdef int carry = (value >> 7) & 1
        cdef int result = ((value << 1) | carry) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=carry)
        return result

    cdef int _cb_rrc(self, int value):
        cdef int carry = value & 1
        cdef int result = ((carry << 7) | (value >> 1)) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=carry)
        return result

    cdef int _cb_rl(self, int value):
        cdef int carry_in = 1 if self._get_flag_c() else 0
        cdef int carry_out = (value >> 7) & 1
        cdef int result = ((value << 1) | carry_in) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=carry_out)
        return result

    cdef int _cb_rr(self, int value):
        cdef int carry_in = 0x80 if self._get_flag_c() else 0
        cdef int carry_out = value & 1
        cdef int result = ((value >> 1) | carry_in) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=carry_out)
        return result

    cdef int _cb_sla(self, int value):
        cdef int carry = (value >> 7) & 1
        cdef int result = (value << 1) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=carry)
        return result

    cdef int _cb_sra(self, int value):
        cdef int carry = value & 1
        cdef int result = ((value & 0x80) | (value >> 1)) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=carry)
        return result

    cdef int _cb_swap(self, int value):
        cdef int result = ((value >> 4) | ((value & 0x0F) << 4)) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=False)
        return result

    cdef int _cb_srl(self, int value):
        cdef int carry = value & 1
        cdef int result = (value >> 1) & 0xFF
        self._set_flags(z=result == 0, n=False, h=False, c=carry)
        return result

    cdef int _exec_cb(self):
        cdef int op = self._fetch8()
        cdef int reg = op & 0x07
        cdef int value = self._read_reg(reg)
        cdef int group, bit

        if op < 0x40:
            group = (op >> 3) & 0x07
            if group == 0:
                value = self._cb_rlc(value)
            elif group == 1:
                value = self._cb_rrc(value)
            elif group == 2:
                value = self._cb_rl(value)
            elif group == 3:
                value = self._cb_rr(value)
            elif group == 4:
                value = self._cb_sla(value)
            elif group == 5:
                value = self._cb_sra(value)
            elif group == 6:
                value = self._cb_swap(value)
            else:
                value = self._cb_srl(value)
            self._write_reg(reg, value)
            return 16 if reg == 6 else 8

        if op < 0x80:
            bit = (op >> 3) & 0x07
            self._set_flags(z=(value & (1 << bit)) == 0, n=False, h=True)
            return 12 if reg == 6 else 8

        if op < 0xC0:
            bit = (op >> 3) & 0x07
            self._write_reg(reg, value & ~(1 << bit))
            return 16 if reg == 6 else 8

        bit = (op >> 3) & 0x07
        self._write_reg(reg, value | (1 << bit))
        return 16 if reg == 6 else 8

    cdef int _read_reg(self, int reg_id):
        if reg_id == 0:
            return self.B
        if reg_id == 1:
            return self.C
        if reg_id == 2:
            return self.D
        if reg_id == 3:
            return self.E
        if reg_id == 4:
            return self.H
        if reg_id == 5:
            return self.L
        if reg_id == 6:
            return self.bus.read8(self._get_HL())
        return self.A

    cdef void _write_reg(self, int reg_id, int value):
        value &= 0xFF
        if reg_id == 0:
            self.B = value
        elif reg_id == 1:
            self.C = value
        elif reg_id == 2:
            self.D = value
        elif reg_id == 3:
            self.E = value
        elif reg_id == 4:
            self.H = value
        elif reg_id == 5:
            self.L = value
        elif reg_id == 6:
            self.bus.write8(self._get_HL(), value)
        else:
            self.A = value

    cpdef int step(self):
        cdef int pending = self._pending_interrupt_mask()
        cdef int pc, op, used, dst, src, value, hl, target, offset, vector

        if pending:
            if self.halted:
                self.halted = False
            if self.ime:
                return self._service_interrupt(pending)

        if self.halted:
            self.cycles += 4
            return 4

        pc = self.PC
        op = self._fetch8()

        try:
            if op == 0x00:
                used = 4
            elif op == 0x07:
                value = (self.A >> 7) & 1
                self.A = ((self.A << 1) | value) & 0xFF
                self._set_flags(z=False, n=False, h=False, c=value)
                used = 4
            elif op == 0x0F:
                value = self.A & 1
                self.A = ((value << 7) | (self.A >> 1)) & 0xFF
                self._set_flags(z=False, n=False, h=False, c=value)
                used = 4
            elif op == 0x17:
                src = 1 if self._get_flag_c() else 0
                value = (self.A >> 7) & 1
                self.A = ((self.A << 1) | src) & 0xFF
                self._set_flags(z=False, n=False, h=False, c=value)
                used = 4
            elif op == 0x1F:
                src = 0x80 if self._get_flag_c() else 0
                value = self.A & 1
                self.A = ((self.A >> 1) | src) & 0xFF
                self._set_flags(z=False, n=False, h=False, c=value)
                used = 4
            elif op == 0xF3:
                self.ime = False
                used = 4
            elif op == 0xFB:
                self.ime = True
                used = 4
            elif op == 0x76:
                self.halted = True
                used = 4
            elif op == 0xCB:
                used = self._exec_cb()
            elif 0x40 <= op <= 0x7F:
                dst = (op >> 3) & 0x07
                src = op & 0x07
                self._write_reg(dst, self._read_reg(src))
                used = 8 if 6 in {dst, src} else 4
            elif op == 0x3E:
                self.A = self._fetch8()
                used = 8
            elif op == 0x06:
                self.B = self._fetch8()
                used = 8
            elif op == 0x0E:
                self.C = self._fetch8()
                used = 8
            elif op == 0x16:
                self.D = self._fetch8()
                used = 8
            elif op == 0x14:
                self.D = self._inc8(self.D)
                used = 4
            elif op == 0x15:
                self.D = self._dec8(self.D)
                used = 4
            elif op == 0x1E:
                self.E = self._fetch8()
                used = 8
            elif op == 0x1C:
                self.E = self._inc8(self.E)
                used = 4
            elif op == 0x1D:
                self.E = self._dec8(self.E)
                used = 4
            elif op == 0x26:
                self.H = self._fetch8()
                used = 8
            elif op == 0x24:
                self.H = self._inc8(self.H)
                used = 4
            elif op == 0x25:
                self.H = self._dec8(self.H)
                used = 4
            elif op == 0x2E:
                self.L = self._fetch8()
                used = 8
            elif op == 0x27:
                self._daa()
                used = 4
            elif op == 0x2C:
                self.L = self._inc8(self.L)
                used = 4
            elif op == 0x2D:
                self.L = self._dec8(self.L)
                used = 4
            elif op == 0x21:
                self._set_HL(self._fetch16())
                used = 12
            elif op == 0x09:
                self._add16_hl(self._get_BC())
                used = 8
            elif op == 0x19:
                self._add16_hl(self._get_DE())
                used = 8
            elif op == 0x29:
                self._add16_hl(self._get_HL())
                used = 8
            elif op == 0x39:
                self._add16_hl(self.SP)
                used = 8
            elif op == 0x23:
                self._set_HL((self._get_HL() + 1) & 0xFFFF)
                used = 8
            elif op == 0x2B:
                self._set_HL((self._get_HL() - 1) & 0xFFFF)
                used = 8
            elif op == 0x31:
                self.SP = self._fetch16()
                used = 12
            elif op == 0xF9:
                self.SP = self._get_HL()
                used = 8
            elif op == 0xE8:
                self.SP = self._add_sp_signed(self._fetch8())
                used = 16
            elif op == 0xF8:
                self._set_HL(self._add_sp_signed(self._fetch8()))
                used = 12
            elif op == 0x33:
                self.SP = (self.SP + 1) & 0xFFFF
                used = 8
            elif op == 0x3B:
                self.SP = (self.SP - 1) & 0xFFFF
                used = 8
            elif op == 0x01:
                self._set_BC(self._fetch16())
                used = 12
            elif op == 0x03:
                self._set_BC((self._get_BC() + 1) & 0xFFFF)
                used = 8
            elif op == 0x0B:
                self._set_BC((self._get_BC() - 1) & 0xFFFF)
                used = 8
            elif op == 0x11:
                self._set_DE(self._fetch16())
                used = 12
            elif op == 0x13:
                self._set_DE((self._get_DE() + 1) & 0xFFFF)
                used = 8
            elif op == 0x1B:
                self._set_DE((self._get_DE() - 1) & 0xFFFF)
                used = 8
            elif op == 0x02:
                self.bus.write8(self._get_BC(), self.A)
                used = 8
            elif op == 0x0A:
                self.A = self.bus.read8(self._get_BC())
                used = 8
            elif op == 0x12:
                self.bus.write8(self._get_DE(), self.A)
                used = 8
            elif op == 0x1A:
                self.A = self.bus.read8(self._get_DE())
                used = 8
            elif op == 0x77:
                self.bus.write8(self._get_HL(), self.A)
                used = 8
            elif op == 0x34:
                self.bus.write8(self._get_HL(), self._inc8(self.bus.read8(self._get_HL())))
                used = 12
            elif op == 0x35:
                self.bus.write8(self._get_HL(), self._dec8(self.bus.read8(self._get_HL())))
                used = 12
            elif op == 0x36:
                self.bus.write8(self._get_HL(), self._fetch8())
                used = 12
            elif op == 0x7E:
                self.A = self.bus.read8(self._get_HL())
                used = 8
            elif op == 0x22:
                hl = self._get_HL()
                self.bus.write8(hl, self.A)
                self._set_HL((hl + 1) & 0xFFFF)
                used = 8
            elif op == 0x32:
                hl = self._get_HL()
                self.bus.write8(hl, self.A)
                self._set_HL((hl - 1) & 0xFFFF)
                used = 8
            elif op == 0x2A:
                hl = self._get_HL()
                self.A = self.bus.read8(hl)
                self._set_HL((hl + 1) & 0xFFFF)
                used = 8
            elif op == 0x3A:
                hl = self._get_HL()
                self.A = self.bus.read8(hl)
                self._set_HL((hl - 1) & 0xFFFF)
                used = 8
            elif op == 0xEA:
                self.bus.write8(self._fetch16(), self.A)
                used = 16
            elif op == 0xFA:
                self.A = self.bus.read8(self._fetch16())
                used = 16
            elif op == 0xE0:
                self.bus.write8(0xFF00 | self._fetch8(), self.A)
                used = 12
            elif op == 0xF0:
                self.A = self.bus.read8(0xFF00 | self._fetch8())
                used = 12
            elif op == 0xE2:
                self.bus.write8(0xFF00 | self.C, self.A)
                used = 8
            elif op == 0xF2:
                self.A = self.bus.read8(0xFF00 | self.C)
                used = 8
            elif op == 0xAF:
                self.A ^= self.A
                self._set_flags(z=True, n=False, h=False, c=False)
                used = 4
            elif 0xA0 <= op <= 0xA7:
                value = self._read_reg(op & 0x07)
                self.A &= value
                self._set_flags(z=self.A == 0, n=False, h=True, c=False)
                used = 8 if (op & 0x07) == 6 else 4
            elif 0xA8 <= op <= 0xAF:
                value = self._read_reg(op & 0x07)
                self.A ^= value
                self._set_flags(z=self.A == 0, n=False, h=False, c=False)
                used = 8 if (op & 0x07) == 6 else 4
            elif 0xB0 <= op <= 0xB7:
                value = self._read_reg(op & 0x07)
                self.A |= value
                self._set_flags(z=self.A == 0, n=False, h=False, c=False)
                used = 8 if (op & 0x07) == 6 else 4
            elif 0xB8 <= op <= 0xBF:
                value = self._read_reg(op & 0x07)
                self._cp8(value)
                used = 8 if (op & 0x07) == 6 else 4
            elif op == 0xE6:
                self.A &= self._fetch8()
                self._set_flags(z=self.A == 0, n=False, h=True, c=False)
                used = 8
            elif op == 0xEE:
                self.A ^= self._fetch8()
                self._set_flags(z=self.A == 0, n=False, h=False, c=False)
                used = 8
            elif op == 0xF6:
                self.A |= self._fetch8()
                self._set_flags(z=self.A == 0, n=False, h=False, c=False)
                used = 8
            elif op == 0xFE:
                self._cp8(self._fetch8())
                used = 8
            elif op == 0x3C:
                self.A = self._inc8(self.A)
                used = 4
            elif op == 0x3D:
                self.A = self._dec8(self.A)
                used = 4
            elif op == 0x04:
                self.B = self._inc8(self.B)
                used = 4
            elif op == 0x05:
                self.B = self._dec8(self.B)
                used = 4
            elif op == 0x0C:
                self.C = self._inc8(self.C)
                used = 4
            elif op == 0x0D:
                self.C = self._dec8(self.C)
                used = 4
            elif 0x80 <= op <= 0x87:
                value = self._read_reg(op & 0x07)
                self._add8(value)
                used = 8 if (op & 0x07) == 6 else 4
            elif 0x88 <= op <= 0x8F:
                value = self._read_reg(op & 0x07)
                self._add8(value, 1 if self._get_flag_c() else 0)
                used = 8 if (op & 0x07) == 6 else 4
            elif op == 0xC6:
                self._add8(self._fetch8())
                used = 8
            elif op == 0xCE:
                self._add8(self._fetch8(), 1 if self._get_flag_c() else 0)
                used = 8
            elif 0x90 <= op <= 0x97:
                value = self._read_reg(op & 0x07)
                self._sub8(value)
                used = 8 if (op & 0x07) == 6 else 4
            elif 0x98 <= op <= 0x9F:
                value = self._read_reg(op & 0x07)
                self._sub8(value, 1 if self._get_flag_c() else 0)
                used = 8 if (op & 0x07) == 6 else 4
            elif op == 0xD6:
                self._sub8(self._fetch8())
                used = 8
            elif op == 0xDE:
                self._sub8(self._fetch8(), 1 if self._get_flag_c() else 0)
                used = 8
            elif op == 0x2F:
                self.A ^= 0xFF
                self._set_flags(n=True, h=True)
                used = 4
            elif op == 0x37:
                self._set_flags(n=False, h=False, c=True)
                used = 4
            elif op == 0x3F:
                self._set_flags(n=False, h=False, c=not self._get_flag_c())
                used = 4
            elif op == 0xC3:
                self.PC = self._fetch16()
                used = 16
            elif op == 0xE9:
                self.PC = self._get_HL()
                used = 4
            elif op == 0xC2:
                target = self._fetch16()
                if not self._get_flag_z():
                    self.PC = target
                    used = 16
                else:
                    used = 12
            elif op == 0xCA:
                target = self._fetch16()
                if self._get_flag_z():
                    self.PC = target
                    used = 16
                else:
                    used = 12
            elif op == 0xD2:
                target = self._fetch16()
                if not self._get_flag_c():
                    self.PC = target
                    used = 16
                else:
                    used = 12
            elif op == 0xDA:
                target = self._fetch16()
                if self._get_flag_c():
                    self.PC = target
                    used = 16
                else:
                    used = 12
            elif op == 0xC9:
                self.PC = self._pop16()
                used = 16
            elif op == 0xD9:
                self.PC = self._pop16()
                self.ime = True
                used = 16
            elif op == 0xC0:
                if not self._get_flag_z():
                    self.PC = self._pop16()
                    used = 20
                else:
                    used = 8
            elif op == 0xC8:
                if self._get_flag_z():
                    self.PC = self._pop16()
                    used = 20
                else:
                    used = 8
            elif op == 0xD0:
                if not self._get_flag_c():
                    self.PC = self._pop16()
                    used = 20
                else:
                    used = 8
            elif op == 0xD8:
                if self._get_flag_c():
                    self.PC = self._pop16()
                    used = 20
                else:
                    used = 8
            elif op == 0xCD:
                target = self._fetch16()
                self._push16(self.PC)
                self.PC = target
                used = 24
            elif op in {0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF}:
                vector = op & 0x38
                self._push16(self.PC)
                self.PC = vector
                used = 16
            elif op == 0xC4:
                target = self._fetch16()
                if not self._get_flag_z():
                    self._push16(self.PC)
                    self.PC = target
                    used = 24
                else:
                    used = 12
            elif op == 0xCC:
                target = self._fetch16()
                if self._get_flag_z():
                    self._push16(self.PC)
                    self.PC = target
                    used = 24
                else:
                    used = 12
            elif op == 0xD4:
                target = self._fetch16()
                if not self._get_flag_c():
                    self._push16(self.PC)
                    self.PC = target
                    used = 24
                else:
                    used = 12
            elif op == 0xDC:
                target = self._fetch16()
                if self._get_flag_c():
                    self._push16(self.PC)
                    self.PC = target
                    used = 24
                else:
                    used = 12
            elif op == 0xC5:
                self._push16(self._get_BC())
                used = 16
            elif op == 0xD5:
                self._push16(self._get_DE())
                used = 16
            elif op == 0xE5:
                self._push16(self._get_HL())
                used = 16
            elif op == 0xF5:
                self._push16((self.A << 8) | self.F)
                used = 16
            elif op == 0xC1:
                self._set_BC(self._pop16())
                used = 12
            elif op == 0xD1:
                self._set_DE(self._pop16())
                used = 12
            elif op == 0xE1:
                self._set_HL(self._pop16())
                used = 12
            elif op == 0xF1:
                value = self._pop16()
                self.A = (value >> 8) & 0xFF
                self.F = value & 0xF0
                used = 12
            elif op == 0x18:
                offset = self._fetch8()
                if offset & 0x80:
                    offset -= 0x100
                self.PC = (self.PC + offset) & 0xFFFF
                used = 12
            elif op == 0x20:
                offset = self._fetch8()
                if not self._get_flag_z():
                    if offset & 0x80:
                        offset -= 0x100
                    self.PC = (self.PC + offset) & 0xFFFF
                    used = 12
                else:
                    used = 8
            elif op == 0x28:
                offset = self._fetch8()
                if self._get_flag_z():
                    if offset & 0x80:
                        offset -= 0x100
                    self.PC = (self.PC + offset) & 0xFFFF
                    used = 12
                else:
                    used = 8
            elif op == 0x30:
                offset = self._fetch8()
                if not self._get_flag_c():
                    if offset & 0x80:
                        offset -= 0x100
                    self.PC = (self.PC + offset) & 0xFFFF
                    used = 12
                else:
                    used = 8
            elif op == 0x38:
                offset = self._fetch8()
                if self._get_flag_c():
                    if offset & 0x80:
                        offset -= 0x100
                    self.PC = (self.PC + offset) & 0xFFFF
                    used = 12
                else:
                    used = 8
            else:
                raise NotImplementedError(f"opcode {op:02X}")
        except NotImplementedError as exc:
            raise NotImplementedError(
                f"LR35902 opcode {op:02X} en PC={pc:04X}: {exc}"
            ) from exc

        self.cycles += used
        return used

    cpdef int run_cycles(self, int cycles):
        cdef int target = max(0, int(cycles))
        cdef int used = 0
        while used < target:
            used += self.step()
        return used

    def snapshot(self) -> dict:
        return {
            "A": self.A,
            "F": self.F,
            "B": self.B,
            "C": self.C,
            "D": self.D,
            "E": self.E,
            "H": self.H,
            "L": self.L,
            "SP": self.SP,
            "PC": self.PC,
            "halted": self.halted,
            "ime": self.ime,
            "cycles": self.cycles,
        }
