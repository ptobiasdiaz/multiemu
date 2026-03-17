# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from .types cimport uint8_t, uint16_t, int8_t
from .core cimport Z80Core

cdef int FLAG_S  = 0x80
cdef int FLAG_Z  = 0x40
cdef int FLAG_H  = 0x10
cdef int FLAG_PV = 0x04
cdef int FLAG_N  = 0x02
cdef int FLAG_C  = 0x01


cdef class Z80Core:

    def __init__(self, bus):
        self.bus = bus
        self.reset()

    cpdef reset(self):
        self.A = self.F = 0
        self.B = self.C = 0
        self.D = self.E = 0
        self.H = self.L = 0

        self.A2 = self.F2 = 0
        self.B2 = self.C2 = 0
        self.D2 = self.E2 = 0
        self.H2 = self.L2 = 0

        self.IX = 0
        self.IY = 0
        self.I = 0
        self.R = 0

        self.PC = 0
        self.SP = 0xFFFF

        self.halted = False
        self.iff1 = False
        self.iff2 = False
        self.im = 0
        self.ei_pending = False

    cpdef interrupt(self):
        cdef uint16_t addr
        cdef uint8_t lo
        cdef uint8_t hi

        if not self.iff1:
            return

        self.halted = False
        self.iff1 = False
        self.iff2 = False

        if self.im == 0 or self.im == 1:
            self.push16(self.PC)
            self.PC = 0x0038
        elif self.im == 2:
            addr = <uint16_t>(((self.I << 8) | 0xFF) & 0xFFFF)
            lo = self.bus.mem_read(addr)
            hi = self.bus.mem_read(<uint16_t>((addr + 1) & 0xFFFF))
            self.push16(self.PC)
            self.PC = <uint16_t>(lo | (hi << 8))

    cdef uint8_t fetch8(self):
        cdef uint8_t v = self.bus.mem_read(self.PC)
        self.PC = <uint16_t>((self.PC + 1) & 0xFFFF)
        self.R = <uint8_t>((self.R + 1) & 0x7F)
        return v

    cdef uint16_t fetch16(self):
        cdef uint8_t lo = self.fetch8()
        cdef uint8_t hi = self.fetch8()
        return <uint16_t>(lo | (hi << 8))

    cdef uint16_t get_BC(self):
        return <uint16_t>((self.B << 8) | self.C)

    cdef uint16_t get_DE(self):
        return <uint16_t>((self.D << 8) | self.E)

    cdef uint16_t get_HL(self):
        return <uint16_t>((self.H << 8) | self.L)

    cdef void set_BC(self, uint16_t v):
        self.B = <uint8_t>((v >> 8) & 0xFF)
        self.C = <uint8_t>(v & 0xFF)

    cdef void set_DE(self, uint16_t v):
        self.D = <uint8_t>((v >> 8) & 0xFF)
        self.E = <uint8_t>(v & 0xFF)

    cdef void set_HL(self, uint16_t v):
        self.H = <uint8_t>((v >> 8) & 0xFF)
        self.L = <uint8_t>(v & 0xFF)

    cdef uint8_t get_IXH(self):
        return <uint8_t>((self.IX >> 8) & 0xFF)

    cdef uint8_t get_IXL(self):
        return <uint8_t>(self.IX & 0xFF)

    cdef uint8_t get_IYH(self):
        return <uint8_t>((self.IY >> 8) & 0xFF)

    cdef uint8_t get_IYL(self):
        return <uint8_t>(self.IY & 0xFF)

    cdef void set_IXH(self, uint8_t v):
        self.IX = <uint16_t>(((v << 8) | (self.IX & 0x00FF)) & 0xFFFF)

    cdef void set_IXL(self, uint8_t v):
        self.IX = <uint16_t>(((self.IX & 0xFF00) | v) & 0xFFFF)

    cdef void set_IYH(self, uint8_t v):
        self.IY = <uint16_t>(((v << 8) | (self.IY & 0x00FF)) & 0xFFFF)

    cdef void set_IYL(self, uint8_t v):
        self.IY = <uint16_t>(((self.IY & 0xFF00) | v) & 0xFFFF)

    cdef uint8_t parity_even(self, uint8_t v):
        cdef uint8_t x = v
        x ^= x >> 4
        x ^= x >> 2
        x ^= x >> 1
        return <uint8_t>(((~x) & 1) != 0)

    cdef uint8_t add8(self, uint8_t a, uint8_t b):
        cdef uint16_t r = a + b
        cdef uint8_t rr = <uint8_t>(r & 0xFF)

        self.F = 0
        if rr & 0x80:
            self.F |= FLAG_S
        if rr == 0:
            self.F |= FLAG_Z
        if ((a & 0x0F) + (b & 0x0F)) > 0x0F:
            self.F |= FLAG_H
        if (((a ^ rr) & (b ^ rr) & 0x80) != 0):
            self.F |= FLAG_PV
        if r > 0xFF:
            self.F |= FLAG_C
        return rr

    cdef uint8_t adc8(self, uint8_t a, uint8_t b):
        cdef uint8_t carry = 1 if (self.F & FLAG_C) else 0
        cdef uint16_t r = a + b + carry
        cdef uint8_t rr = <uint8_t>(r & 0xFF)

        self.F = 0
        if rr & 0x80:
            self.F |= FLAG_S
        if rr == 0:
            self.F |= FLAG_Z
        if ((a & 0x0F) + (b & 0x0F) + carry) > 0x0F:
            self.F |= FLAG_H
        if (((a ^ rr) & (b ^ rr) & 0x80) != 0):
            self.F |= FLAG_PV
        if r > 0xFF:
            self.F |= FLAG_C
        return rr

    cdef uint8_t sub8(self, uint8_t a, uint8_t b):
        cdef int r = a - b
        cdef uint8_t rr = <uint8_t>(r & 0xFF)

        self.F = FLAG_N
        if rr & 0x80:
            self.F |= FLAG_S
        if rr == 0:
            self.F |= FLAG_Z
        if (a & 0x0F) < (b & 0x0F):
            self.F |= FLAG_H
        if (((a ^ b) & (a ^ rr) & 0x80) != 0):
            self.F |= FLAG_PV
        if r < 0:
            self.F |= FLAG_C
        return rr

    cdef uint8_t sbc8(self, uint8_t a, uint8_t b):
        cdef uint8_t carry = 1 if (self.F & FLAG_C) else 0
        cdef int r = a - b - carry
        cdef uint8_t rr = <uint8_t>(r & 0xFF)

        self.F = FLAG_N
        if rr & 0x80:
            self.F |= FLAG_S
        if rr == 0:
            self.F |= FLAG_Z
        if (a & 0x0F) < ((b & 0x0F) + carry):
            self.F |= FLAG_H
        if (((a ^ b) & (a ^ rr) & 0x80) != 0):
            self.F |= FLAG_PV
        if r < 0:
            self.F |= FLAG_C
        return rr

    cdef uint16_t adc16(self, uint16_t a, uint16_t b):
        cdef uint16_t carry = 1 if (self.F & FLAG_C) else 0
        cdef unsigned int r = a + b + carry
        cdef uint16_t rr = <uint16_t>(r & 0xFFFF)

        self.F = 0
        if rr & 0x8000:
            self.F |= FLAG_S
        if rr == 0:
            self.F |= FLAG_Z
        if ((a & 0x0FFF) + (b & 0x0FFF) + carry) > 0x0FFF:
            self.F |= FLAG_H
        if (((a ^ rr) & (b ^ rr) & 0x8000) != 0):
            self.F |= FLAG_PV
        if r > 0xFFFF:
            self.F |= FLAG_C
        return rr

    cdef uint16_t sbc16(self, uint16_t a, uint16_t b):
        cdef uint16_t carry = 1 if (self.F & FLAG_C) else 0
        cdef int r = a - b - carry
        cdef uint16_t rr = <uint16_t>(r & 0xFFFF)

        self.F = FLAG_N
        if rr & 0x8000:
            self.F |= FLAG_S
        if rr == 0:
            self.F |= FLAG_Z
        if (a & 0x0FFF) < ((b & 0x0FFF) + carry):
            self.F |= FLAG_H
        if (((a ^ b) & (a ^ rr) & 0x8000) != 0):
            self.F |= FLAG_PV
        if r < 0:
            self.F |= FLAG_C
        return rr

    cdef uint16_t add16(self, uint16_t a, uint16_t b):
        cdef unsigned int r = a + b
        cdef uint16_t rr = <uint16_t>(r & 0xFFFF)
        cdef uint8_t keep = self.F & (FLAG_S | FLAG_Z | FLAG_PV)

        self.F = keep
        if ((a & 0x0FFF) + (b & 0x0FFF)) > 0x0FFF:
            self.F |= FLAG_H
        if r > 0xFFFF:
            self.F |= FLAG_C
        return rr

    cdef uint8_t and8(self, uint8_t a, uint8_t b):
        cdef uint8_t r = a & b
        self.F = FLAG_H
        if r & 0x80:
            self.F |= FLAG_S
        if r == 0:
            self.F |= FLAG_Z
        if self.parity_even(r):
            self.F |= FLAG_PV
        return r

    cdef uint8_t or8(self, uint8_t a, uint8_t b):
        cdef uint8_t r = a | b
        self.F = 0
        if r & 0x80:
            self.F |= FLAG_S
        if r == 0:
            self.F |= FLAG_Z
        if self.parity_even(r):
            self.F |= FLAG_PV
        return r

    cdef uint8_t xor8(self, uint8_t a, uint8_t b):
        cdef uint8_t r = a ^ b
        self.F = 0
        if r & 0x80:
            self.F |= FLAG_S
        if r == 0:
            self.F |= FLAG_Z
        if self.parity_even(r):
            self.F |= FLAG_PV
        return r

    cdef void cp8(self, uint8_t a, uint8_t b):
        cdef int r = a - b
        cdef uint8_t rr = <uint8_t>(r & 0xFF)

        self.F = FLAG_N
        if rr & 0x80:
            self.F |= FLAG_S
        if rr == 0:
            self.F |= FLAG_Z
        if (a & 0x0F) < (b & 0x0F):
            self.F |= FLAG_H
        if (((a ^ b) & (a ^ rr) & 0x80) != 0):
            self.F |= FLAG_PV
        if r < 0:
            self.F |= FLAG_C

    cdef uint8_t inc8(self, uint8_t v):
        cdef uint8_t old_c = self.F & FLAG_C
        cdef uint8_t r = <uint8_t>((v + 1) & 0xFF)

        self.F = old_c
        if r & 0x80:
            self.F |= FLAG_S
        if r == 0:
            self.F |= FLAG_Z
        if ((v & 0x0F) + 1) > 0x0F:
            self.F |= FLAG_H
        if v == 0x7F:
            self.F |= FLAG_PV
        return r

    cdef uint8_t dec8(self, uint8_t v):
        cdef uint8_t old_c = self.F & FLAG_C
        cdef uint8_t r = <uint8_t>((v - 1) & 0xFF)

        self.F = old_c | FLAG_N
        if r & 0x80:
            self.F |= FLAG_S
        if r == 0:
            self.F |= FLAG_Z
        if (v & 0x0F) == 0:
            self.F |= FLAG_H
        if v == 0x80:
            self.F |= FLAG_PV
        return r

    cdef void daa(self):
        cdef uint8_t a = self.A
        cdef uint8_t correction = 0
        cdef uint8_t carry_out = 0
        cdef uint8_t old_c = <uint8_t>(1 if (self.F & FLAG_C) else 0)
        cdef uint8_t old_h = <uint8_t>(1 if (self.F & FLAG_H) else 0)
        cdef uint8_t n_flag = <uint8_t>(1 if (self.F & FLAG_N) else 0)

        if not n_flag:
            if old_h or ((a & 0x0F) > 9):
                correction |= 0x06
            if old_c or (a > 0x99):
                correction |= 0x60
                carry_out = 1
            a = <uint8_t>((a + correction) & 0xFF)
        else:
            if old_h:
                correction |= 0x06
            if old_c:
                correction |= 0x60
                carry_out = 1
            a = <uint8_t>((a - correction) & 0xFF)

        self.A = a
        self.F &= FLAG_N
        if a & 0x80:
            self.F |= FLAG_S
        if a == 0:
            self.F |= FLAG_Z
        if self.parity_even(a):
            self.F |= FLAG_PV
        if carry_out:
            self.F |= FLAG_C
        if correction & 0x06:
            self.F |= FLAG_H

    cdef uint8_t rlc8(self, uint8_t v):
        cdef uint8_t c = <uint8_t>((v >> 7) & 1)
        cdef uint8_t r = <uint8_t>(((v << 1) | c) & 0xFF)
        self.F = 0
        if r & 0x80: self.F |= FLAG_S
        if r == 0: self.F |= FLAG_Z
        if self.parity_even(r): self.F |= FLAG_PV
        if c: self.F |= FLAG_C
        return r

    cdef uint8_t rrc8(self, uint8_t v):
        cdef uint8_t c = <uint8_t>(v & 1)
        cdef uint8_t r = <uint8_t>(((v >> 1) | (c << 7)) & 0xFF)
        self.F = 0
        if r & 0x80: self.F |= FLAG_S
        if r == 0: self.F |= FLAG_Z
        if self.parity_even(r): self.F |= FLAG_PV
        if c: self.F |= FLAG_C
        return r

    cdef uint8_t rl8(self, uint8_t v):
        cdef uint8_t old_c = <uint8_t>(1 if (self.F & FLAG_C) else 0)
        cdef uint8_t c = <uint8_t>((v >> 7) & 1)
        cdef uint8_t r = <uint8_t>(((v << 1) | old_c) & 0xFF)
        self.F = 0
        if r & 0x80: self.F |= FLAG_S
        if r == 0: self.F |= FLAG_Z
        if self.parity_even(r): self.F |= FLAG_PV
        if c: self.F |= FLAG_C
        return r

    cdef uint8_t rr8(self, uint8_t v):
        cdef uint8_t old_c = <uint8_t>(1 if (self.F & FLAG_C) else 0)
        cdef uint8_t c = <uint8_t>(v & 1)
        cdef uint8_t r = <uint8_t>(((v >> 1) | (old_c << 7)) & 0xFF)
        self.F = 0
        if r & 0x80: self.F |= FLAG_S
        if r == 0: self.F |= FLAG_Z
        if self.parity_even(r): self.F |= FLAG_PV
        if c: self.F |= FLAG_C
        return r

    cdef uint8_t sla8(self, uint8_t v):
        cdef uint8_t c = <uint8_t>((v >> 7) & 1)
        cdef uint8_t r = <uint8_t>((v << 1) & 0xFF)
        self.F = 0
        if r & 0x80: self.F |= FLAG_S
        if r == 0: self.F |= FLAG_Z
        if self.parity_even(r): self.F |= FLAG_PV
        if c: self.F |= FLAG_C
        return r

    cdef uint8_t sra8(self, uint8_t v):
        cdef uint8_t c = <uint8_t>(v & 1)
        cdef uint8_t r = <uint8_t>(((v >> 1) | (v & 0x80)) & 0xFF)
        self.F = 0
        if r & 0x80: self.F |= FLAG_S
        if r == 0: self.F |= FLAG_Z
        if self.parity_even(r): self.F |= FLAG_PV
        if c: self.F |= FLAG_C
        return r

    cdef uint8_t srl8(self, uint8_t v):
        cdef uint8_t c = <uint8_t>(v & 1)
        cdef uint8_t r = <uint8_t>((v >> 1) & 0x7F)
        self.F = 0
        if r & 0x80: self.F |= FLAG_S
        if r == 0: self.F |= FLAG_Z
        if self.parity_even(r): self.F |= FLAG_PV
        if c: self.F |= FLAG_C
        return r

    cdef void bit8(self, uint8_t bit, uint8_t v):
        cdef uint8_t mask = <uint8_t>(1 << bit)
        cdef uint8_t old_c = self.F & FLAG_C
        self.F = old_c | FLAG_H
        if bit == 7 and (v & 0x80):
            self.F |= FLAG_S
        if (v & mask) == 0:
            self.F |= FLAG_Z | FLAG_PV

    cdef void push16(self, uint16_t v):
        self.SP = <uint16_t>((self.SP - 1) & 0xFFFF)
        self.bus.mem_write(self.SP, <uint8_t>((v >> 8) & 0xFF))
        self.SP = <uint16_t>((self.SP - 1) & 0xFFFF)
        self.bus.mem_write(self.SP, <uint8_t>(v & 0xFF))

    cdef uint16_t pop16(self):
        cdef uint8_t lo = self.bus.mem_read(self.SP)
        cdef uint8_t hi
        self.SP = <uint16_t>((self.SP + 1) & 0xFFFF)
        hi = self.bus.mem_read(self.SP)
        self.SP = <uint16_t>((self.SP + 1) & 0xFFFF)
        return <uint16_t>(lo | (hi << 8))

    cdef bint cond_nz(self):
        return (self.F & FLAG_Z) == 0

    cdef bint cond_z(self):
        return (self.F & FLAG_Z) != 0

    cdef bint cond_nc(self):
        return (self.F & FLAG_C) == 0

    cdef bint cond_c(self):
        return (self.F & FLAG_C) != 0

    cdef bint cond_po(self):
        return (self.F & FLAG_PV) == 0

    cdef bint cond_pe(self):
        return (self.F & FLAG_PV) != 0

    cdef bint cond_p(self):
        return (self.F & FLAG_S) == 0

    cdef bint cond_m(self):
        return (self.F & FLAG_S) != 0

    cdef int exec_cb(self):
        cdef uint8_t op = self.fetch8()
        cdef uint8_t group = op >> 6
        cdef uint8_t y = (op >> 3) & 0x07
        cdef uint8_t z = op & 0x07
        cdef uint8_t v
        cdef uint16_t hl

        if z == 0:
            v = self.B
        elif z == 1:
            v = self.C
        elif z == 2:
            v = self.D
        elif z == 3:
            v = self.E
        elif z == 4:
            v = self.H
        elif z == 5:
            v = self.L
        elif z == 6:
            hl = self.get_HL()
            v = self.bus.mem_read(hl)
        else:
            v = self.A

        if group == 0:
            if y == 0:
                v = self.rlc8(v)
            elif y == 1:
                v = self.rrc8(v)
            elif y == 2:
                v = self.rl8(v)
            elif y == 3:
                v = self.rr8(v)
            elif y == 4:
                v = self.sla8(v)
            elif y == 5:
                v = self.sra8(v)
            elif y == 7:
                v = self.srl8(v)
            else:
                raise NotImplementedError(f"CB opcode {op:02X}")

            if z == 0:
                self.B = v; return 8
            elif z == 1:
                self.C = v; return 8
            elif z == 2:
                self.D = v; return 8
            elif z == 3:
                self.E = v; return 8
            elif z == 4:
                self.H = v; return 8
            elif z == 5:
                self.L = v; return 8
            elif z == 6:
                self.bus.mem_write(self.get_HL(), v); return 15
            else:
                self.A = v; return 8

        elif group == 1:
            self.bit8(y, v)
            if z == 6:
                return 12
            return 8

        elif group == 2:
            v = <uint8_t>(v & (~(1 << y)))
            if z == 0:
                self.B = v; return 8
            elif z == 1:
                self.C = v; return 8
            elif z == 2:
                self.D = v; return 8
            elif z == 3:
                self.E = v; return 8
            elif z == 4:
                self.H = v; return 8
            elif z == 5:
                self.L = v; return 8
            elif z == 6:
                self.bus.mem_write(self.get_HL(), v); return 15
            else:
                self.A = v; return 8

        else:
            v = <uint8_t>(v | (1 << y))
            if z == 0:
                self.B = v; return 8
            elif z == 1:
                self.C = v; return 8
            elif z == 2:
                self.D = v; return 8
            elif z == 3:
                self.E = v; return 8
            elif z == 4:
                self.H = v; return 8
            elif z == 5:
                self.L = v; return 8
            elif z == 6:
                self.bus.mem_write(self.get_HL(), v); return 15
            else:
                self.A = v; return 8

    cdef int exec_ed(self):
        cdef uint8_t op = self.fetch8()
        cdef uint16_t bc, de, hl, nn, tmp16
        cdef uint8_t val, old_c
        cdef int r
        cdef uint8_t res

        if op in (0x44, 0x4C, 0x54, 0x5C, 0x64, 0x6C, 0x74, 0x7C):
            # NEG
            self.A = self.sub8(0, self.A)
            return 8

        elif op in (0x45, 0x55, 0x65, 0x75):
            # RETN
            self.PC = self.pop16()
            self.iff1 = self.iff2
            return 14

        elif op in (0x4D, 0x5D, 0x6D, 0x7D):
            # RETI
            self.PC = self.pop16()
            self.iff1 = self.iff2
            return 14

        elif op in (0x46, 0x4E, 0x66, 0x6E):
            # IM 0
            self.im = 0
            return 8

        elif op in (0x56, 0x76):
            # IM 1
            self.im = 1
            return 8

        elif op in (0x5E, 0x7E):
            # IM 2
            self.im = 2
            return 8

        elif op == 0x4A:
            # ADC HL,BC
            self.set_HL(self.adc16(self.get_HL(), self.get_BC()))
            return 15

        elif op == 0x5A:
            # ADC HL,DE
            self.set_HL(self.adc16(self.get_HL(), self.get_DE()))
            return 15

        elif op == 0x6A:
            # ADC HL,HL
            self.set_HL(self.adc16(self.get_HL(), self.get_HL()))
            return 15

        elif op == 0x7A:
            # ADC HL,SP
            self.set_HL(self.adc16(self.get_HL(), self.SP))
            return 15

        elif op == 0x42:
            # SBC HL,BC
            self.set_HL(self.sbc16(self.get_HL(), self.get_BC()))
            return 15

        elif op == 0x52:
            # SBC HL,DE
            self.set_HL(self.sbc16(self.get_HL(), self.get_DE()))
            return 15

        elif op == 0x62:
            # SBC HL,HL
            self.set_HL(self.sbc16(self.get_HL(), self.get_HL()))
            return 15

        elif op == 0x72:
            # SBC HL,SP
            self.set_HL(self.sbc16(self.get_HL(), self.SP))
            return 15

        elif op == 0x43:
            # LD (nn),BC
            nn = self.fetch16()
            bc = self.get_BC()
            self.bus.mem_write(nn, <uint8_t>(bc & 0xFF))
            self.bus.mem_write(<uint16_t>((nn + 1) & 0xFFFF), <uint8_t>((bc >> 8) & 0xFF))
            return 20

        elif op == 0x53:
            # LD (nn),DE
            nn = self.fetch16()
            de = self.get_DE()
            self.bus.mem_write(nn, <uint8_t>(de & 0xFF))
            self.bus.mem_write(<uint16_t>((nn + 1) & 0xFFFF), <uint8_t>((de >> 8) & 0xFF))
            return 20

        elif op == 0x63:
            # LD (nn),HL
            nn = self.fetch16()
            hl = self.get_HL()
            self.bus.mem_write(nn, <uint8_t>(hl & 0xFF))
            self.bus.mem_write(<uint16_t>((nn + 1) & 0xFFFF), <uint8_t>((hl >> 8) & 0xFF))
            return 20

        elif op == 0x73:
            # LD (nn),SP
            nn = self.fetch16()
            self.bus.mem_write(nn, <uint8_t>(self.SP & 0xFF))
            self.bus.mem_write(<uint16_t>((nn + 1) & 0xFFFF), <uint8_t>((self.SP >> 8) & 0xFF))
            return 20

        elif op == 0x4B:
            # LD BC,(nn)
            nn = self.fetch16()
            tmp16 = <uint16_t>(
                self.bus.mem_read(nn) |
                (self.bus.mem_read(<uint16_t>((nn + 1) & 0xFFFF)) << 8)
            )
            self.set_BC(tmp16)
            return 20

        elif op == 0x5B:
            # LD DE,(nn)
            nn = self.fetch16()
            tmp16 = <uint16_t>(
                self.bus.mem_read(nn) |
                (self.bus.mem_read(<uint16_t>((nn + 1) & 0xFFFF)) << 8)
            )
            self.set_DE(tmp16)
            return 20

        elif op == 0x6B:
            # LD HL,(nn)
            nn = self.fetch16()
            tmp16 = <uint16_t>(
                self.bus.mem_read(nn) |
                (self.bus.mem_read(<uint16_t>((nn + 1) & 0xFFFF)) << 8)
            )
            self.set_HL(tmp16)
            return 20

        elif op == 0x7B:
            # LD SP,(nn)
            nn = self.fetch16()
            self.SP = <uint16_t>(
                self.bus.mem_read(nn) |
                (self.bus.mem_read(<uint16_t>((nn + 1) & 0xFFFF)) << 8)
            )
            return 20

        elif op == 0x47:
            # LD I,A
            self.I = self.A
            return 9

        elif op == 0x4F:
            # LD R,A
            self.R = self.A
            return 9

        elif op == 0x57:
            # LD A,I
            self.A = self.I
            old_c = self.F & FLAG_C
            self.F = old_c
            if self.A & 0x80:
                self.F |= FLAG_S
            if self.A == 0:
                self.F |= FLAG_Z
            if self.iff2:
                self.F |= FLAG_PV
            return 9

        elif op == 0x5F:
            # LD A,R
            self.A = self.R
            old_c = self.F & FLAG_C
            self.F = old_c
            if self.A & 0x80:
                self.F |= FLAG_S
            if self.A == 0:
                self.F |= FLAG_Z
            if self.iff2:
                self.F |= FLAG_PV
            return 9

        elif op == 0xA0:
            # LDI
            val = self.bus.mem_read(self.get_HL())
            self.bus.mem_write(self.get_DE(), val)

            self.set_HL(<uint16_t>((self.get_HL() + 1) & 0xFFFF))
            self.set_DE(<uint16_t>((self.get_DE() + 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(self.F & (FLAG_S | FLAG_Z | FLAG_C))
            if self.get_BC() != 0:
                self.F |= FLAG_PV
            return 16

        elif op == 0xB0:
            # LDIR
            val = self.bus.mem_read(self.get_HL())
            self.bus.mem_write(self.get_DE(), val)

            self.set_HL(<uint16_t>((self.get_HL() + 1) & 0xFFFF))
            self.set_DE(<uint16_t>((self.get_DE() + 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(self.F & (FLAG_S | FLAG_Z | FLAG_C))
            if self.get_BC() != 0:
                self.F |= FLAG_PV
                self.PC = <uint16_t>((self.PC - 2) & 0xFFFF)
                return 21
            return 16

        elif op == 0xA8:
            # LDD
            val = self.bus.mem_read(self.get_HL())
            self.bus.mem_write(self.get_DE(), val)

            self.set_HL(<uint16_t>((self.get_HL() - 1) & 0xFFFF))
            self.set_DE(<uint16_t>((self.get_DE() - 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(self.F & (FLAG_S | FLAG_Z | FLAG_C))
            if self.get_BC() != 0:
                self.F |= FLAG_PV
            return 16

        elif op == 0xB8:
            # LDDR
            val = self.bus.mem_read(self.get_HL())
            self.bus.mem_write(self.get_DE(), val)

            self.set_HL(<uint16_t>((self.get_HL() - 1) & 0xFFFF))
            self.set_DE(<uint16_t>((self.get_DE() - 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(self.F & (FLAG_S | FLAG_Z | FLAG_C))
            if self.get_BC() != 0:
                self.F |= FLAG_PV
                self.PC = <uint16_t>((self.PC - 2) & 0xFFFF)
                return 21
            return 16

        elif op == 0xA1:
            # CPI
            val = self.bus.mem_read(self.get_HL())
            old_c = self.F & FLAG_C
            r = self.A - val
            res = <uint8_t>(r & 0xFF)

            self.set_HL(<uint16_t>((self.get_HL() + 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(old_c | FLAG_N)
            if res & 0x80:
                self.F |= FLAG_S
            if res == 0:
                self.F |= FLAG_Z
            if (self.A & 0x0F) < (val & 0x0F):
                self.F |= FLAG_H
            if self.get_BC() != 0:
                self.F |= FLAG_PV
            return 16

        elif op == 0xB1:
            # CPIR
            val = self.bus.mem_read(self.get_HL())
            old_c = self.F & FLAG_C
            r = self.A - val
            res = <uint8_t>(r & 0xFF)

            self.set_HL(<uint16_t>((self.get_HL() + 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(old_c | FLAG_N)
            if res & 0x80:
                self.F |= FLAG_S
            if res == 0:
                self.F |= FLAG_Z
            if (self.A & 0x0F) < (val & 0x0F):
                self.F |= FLAG_H
            if self.get_BC() != 0:
                self.F |= FLAG_PV

            if self.get_BC() != 0 and res != 0:
                self.PC = <uint16_t>((self.PC - 2) & 0xFFFF)
                return 21
            return 16

        elif op == 0xA9:
            # CPD
            val = self.bus.mem_read(self.get_HL())
            old_c = self.F & FLAG_C
            r = self.A - val
            res = <uint8_t>(r & 0xFF)

            self.set_HL(<uint16_t>((self.get_HL() - 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(old_c | FLAG_N)
            if res & 0x80:
                self.F |= FLAG_S
            if res == 0:
                self.F |= FLAG_Z
            if (self.A & 0x0F) < (val & 0x0F):
                self.F |= FLAG_H
            if self.get_BC() != 0:
                self.F |= FLAG_PV
            return 16

        elif op == 0xB9:
            # CPDR
            val = self.bus.mem_read(self.get_HL())
            old_c = self.F & FLAG_C
            r = self.A - val
            res = <uint8_t>(r & 0xFF)

            self.set_HL(<uint16_t>((self.get_HL() - 1) & 0xFFFF))
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF))

            self.F = <uint8_t>(old_c | FLAG_N)
            if res & 0x80:
                self.F |= FLAG_S
            if res == 0:
                self.F |= FLAG_Z
            if (self.A & 0x0F) < (val & 0x0F):
                self.F |= FLAG_H
            if self.get_BC() != 0:
                self.F |= FLAG_PV

            if self.get_BC() != 0 and res != 0:
                self.PC = <uint16_t>((self.PC - 2) & 0xFFFF)
                return 21
            return 16

        elif op == 0x40:
            val = self.bus.io_read(self.get_BC())
            self.B = val
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x48:
            val = self.bus.io_read(self.get_BC())
            self.C = val
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x50:
            val = self.bus.io_read(self.get_BC())
            self.D = val
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x58:
            val = self.bus.io_read(self.get_BC())
            self.E = val
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x60:
            val = self.bus.io_read(self.get_BC())
            self.H = val
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x68:
            val = self.bus.io_read(self.get_BC())
            self.L = val
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x70:
            val = self.bus.io_read(self.get_BC())
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x78:
            val = self.bus.io_read(self.get_BC())
            self.A = val
            old_c = self.F & FLAG_C
            self.F = old_c
            if val & 0x80:
                self.F |= FLAG_S
            if val == 0:
                self.F |= FLAG_Z
            if self.parity_even(val):
                self.F |= FLAG_PV
            return 12

        elif op == 0x41:
            self.bus.io_write(self.get_BC(), self.B)
            return 12

        elif op == 0x49:
            self.bus.io_write(self.get_BC(), self.C)
            return 12

        elif op == 0x51:
            self.bus.io_write(self.get_BC(), self.D)
            return 12

        elif op == 0x59:
            self.bus.io_write(self.get_BC(), self.E)
            return 12

        elif op == 0x61:
            self.bus.io_write(self.get_BC(), self.H)
            return 12

        elif op == 0x69:
            self.bus.io_write(self.get_BC(), self.L)
            return 12

        elif op == 0x71:
            self.bus.io_write(self.get_BC(), 0)
            return 12

        elif op == 0x79:
            self.bus.io_write(self.get_BC(), self.A)
            return 12

        else:
            raise NotImplementedError(f"ED opcode {op:02X}")

    cdef int exec_index_cb(self, bint use_iy):
        cdef int8_t d = <int8_t>self.fetch8()
        cdef uint8_t op = self.fetch8()
        cdef uint8_t group = op >> 6
        cdef uint8_t y = (op >> 3) & 0x07
        cdef uint8_t z = op & 0x07
        cdef uint16_t base = self.IY if use_iy else self.IX
        cdef uint16_t addr = <uint16_t>((base + d) & 0xFFFF)
        cdef uint8_t v = self.bus.mem_read(addr)

        if group == 0:
            if y == 0:
                v = self.rlc8(v)
            elif y == 1:
                v = self.rrc8(v)
            elif y == 2:
                v = self.rl8(v)
            elif y == 3:
                v = self.rr8(v)
            elif y == 4:
                v = self.sla8(v)
            elif y == 5:
                v = self.sra8(v)
            elif y == 7:
                v = self.srl8(v)
            else:
                raise NotImplementedError(f"{'FD' if use_iy else 'DD'}CB opcode {op:02X}")

            self.bus.mem_write(addr, v)

            if z == 0:
                self.B = v
            elif z == 1:
                self.C = v
            elif z == 2:
                self.D = v
            elif z == 3:
                self.E = v
            elif z == 4:
                self.H = v
            elif z == 5:
                self.L = v
            elif z == 7:
                self.A = v

            return 23

        elif group == 1:
            self.bit8(y, v)
            return 20

        elif group == 2:
            v = <uint8_t>(v & (~(1 << y)))
            self.bus.mem_write(addr, v)

            if z == 0:
                self.B = v
            elif z == 1:
                self.C = v
            elif z == 2:
                self.D = v
            elif z == 3:
                self.E = v
            elif z == 4:
                self.H = v
            elif z == 5:
                self.L = v
            elif z == 7:
                self.A = v

            return 23

        else:
            v = <uint8_t>(v | (1 << y))
            self.bus.mem_write(addr, v)

            if z == 0:
                self.B = v
            elif z == 1:
                self.C = v
            elif z == 2:
                self.D = v
            elif z == 3:
                self.E = v
            elif z == 4:
                self.H = v
            elif z == 5:
                self.L = v
            elif z == 7:
                self.A = v

            return 23

    cdef int exec_index(self, uint8_t op, bint use_iy):
        cdef uint16_t idx
        cdef uint16_t nn
        cdef uint16_t addr
        cdef int8_t d
        cdef uint8_t val

        idx = self.IY if use_iy else self.IX

        if (not use_iy and op == 0xDD) or (use_iy and op == 0xFD):
            return self.exec_index(self.fetch8(), use_iy)

        if op == 0xCB:
            return self.exec_index_cb(use_iy)

        elif op == 0x21:
            idx = self.fetch16()
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 14

        elif op == 0x22:
            nn = self.fetch16()
            self.bus.mem_write(nn, <uint8_t>(idx & 0xFF))
            self.bus.mem_write(<uint16_t>((nn + 1) & 0xFFFF), <uint8_t>((idx >> 8) & 0xFF))
            return 20

        elif op == 0x2A:
            nn = self.fetch16()
            idx = <uint16_t>(self.bus.mem_read(nn) | (self.bus.mem_read(<uint16_t>((nn + 1) & 0xFFFF)) << 8))
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 20

        elif op == 0xE5:
            self.push16(idx); return 15
        elif op == 0xE1:
            idx = self.pop16()
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 14
        elif op == 0xE9:
            self.PC = idx; return 8
        elif op == 0xF9:
            self.SP = idx; return 10

        elif op == 0x23:
            idx = <uint16_t>((idx + 1) & 0xFFFF)
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 10
        elif op == 0x2B:
            idx = <uint16_t>((idx - 1) & 0xFFFF)
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 10

        elif op == 0x09:
            idx = self.add16(idx, self.get_BC())
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 15
        elif op == 0x19:
            idx = self.add16(idx, self.get_DE())
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 15
        elif op == 0x29:
            idx = self.add16(idx, idx)
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 15
        elif op == 0x39:
            idx = self.add16(idx, self.SP)
            if use_iy: self.IY = idx
            else: self.IX = idx
            return 15

        elif op == 0x24:
            if use_iy: self.set_IYH(self.inc8(self.get_IYH()))
            else: self.set_IXH(self.inc8(self.get_IXH()))
            return 8
        elif op == 0x25:
            if use_iy: self.set_IYH(self.dec8(self.get_IYH()))
            else: self.set_IXH(self.dec8(self.get_IXH()))
            return 8
        elif op == 0x26:
            val = self.fetch8()
            if use_iy: self.set_IYH(val)
            else: self.set_IXH(val)
            return 11
        elif op == 0x2C:
            if use_iy: self.set_IYL(self.inc8(self.get_IYL()))
            else: self.set_IXL(self.inc8(self.get_IXL()))
            return 8
        elif op == 0x2D:
            if use_iy: self.set_IYL(self.dec8(self.get_IYL()))
            else: self.set_IXL(self.dec8(self.get_IXL()))
            return 8
        elif op == 0x2E:
            val = self.fetch8()
            if use_iy: self.set_IYL(val)
            else: self.set_IXL(val)
            return 11

        elif op == 0x44:
            self.B = self.get_IYH() if use_iy else self.get_IXH(); return 8
        elif op == 0x45:
            self.B = self.get_IYL() if use_iy else self.get_IXL(); return 8
        elif op == 0x4C:
            self.C = self.get_IYH() if use_iy else self.get_IXH(); return 8
        elif op == 0x4D:
            self.C = self.get_IYL() if use_iy else self.get_IXL(); return 8
        elif op == 0x54:
            self.D = self.get_IYH() if use_iy else self.get_IXH(); return 8
        elif op == 0x55:
            self.D = self.get_IYL() if use_iy else self.get_IXL(); return 8
        elif op == 0x5C:
            self.E = self.get_IYH() if use_iy else self.get_IXH(); return 8
        elif op == 0x5D:
            self.E = self.get_IYL() if use_iy else self.get_IXL(); return 8
        elif op == 0x67:
            if use_iy: self.set_IYH(self.A)
            else: self.set_IXH(self.A)
            return 8
        elif op == 0x6F:
            if use_iy: self.set_IYL(self.A)
            else: self.set_IXL(self.A)
            return 8
        elif op == 0x7C:
            self.A = self.get_IYH() if use_iy else self.get_IXH(); return 8
        elif op == 0x7D:
            self.A = self.get_IYL() if use_iy else self.get_IXL(); return 8

        elif op in (0x46, 0x4E, 0x56, 0x5E, 0x66, 0x6E, 0x7E):
            d = <int8_t>self.fetch8()
            addr = <uint16_t>((idx + d) & 0xFFFF)
            val = self.bus.mem_read(addr)

            if op == 0x46: self.B = val
            elif op == 0x4E: self.C = val
            elif op == 0x56: self.D = val
            elif op == 0x5E: self.E = val
            elif op == 0x66: self.H = val
            elif op == 0x6E: self.L = val
            else: self.A = val
            return 19

        elif op in (0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x77):
            d = <int8_t>self.fetch8()
            addr = <uint16_t>((idx + d) & 0xFFFF)
            if op == 0x70: self.bus.mem_write(addr, self.B)
            elif op == 0x71: self.bus.mem_write(addr, self.C)
            elif op == 0x72: self.bus.mem_write(addr, self.D)
            elif op == 0x73: self.bus.mem_write(addr, self.E)
            elif op == 0x74: self.bus.mem_write(addr, self.H)
            elif op == 0x75: self.bus.mem_write(addr, self.L)
            else: self.bus.mem_write(addr, self.A)
            return 19

        elif op == 0x36:
            d = <int8_t>self.fetch8()
            val = self.fetch8()
            addr = <uint16_t>((idx + d) & 0xFFFF)
            self.bus.mem_write(addr, val)
            return 19

        elif op == 0x34:
            d = <int8_t>self.fetch8()
            addr = <uint16_t>((idx + d) & 0xFFFF)
            val = self.bus.mem_read(addr)
            val = self.inc8(val)
            self.bus.mem_write(addr, val)
            return 23

        elif op == 0x35:
            d = <int8_t>self.fetch8()
            addr = <uint16_t>((idx + d) & 0xFFFF)
            val = self.bus.mem_read(addr)
            val = self.dec8(val)
            self.bus.mem_write(addr, val)
            return 23

        elif op in (0x86, 0x8E, 0x96, 0x9E, 0xA6, 0xAE, 0xB6, 0xBE):
            d = <int8_t>self.fetch8()
            addr = <uint16_t>((idx + d) & 0xFFFF)
            val = self.bus.mem_read(addr)

            if op == 0x86:
                self.A = self.add8(self.A, val)
            elif op == 0x8E:
                self.A = self.adc8(self.A, val)
            elif op == 0x96:
                self.A = self.sub8(self.A, val)
            elif op == 0x9E:
                self.A = self.sbc8(self.A, val)
            elif op == 0xA6:
                self.A = self.and8(self.A, val)
            elif op == 0xAE:
                self.A = self.xor8(self.A, val)
            elif op == 0xB6:
                self.A = self.or8(self.A, val)
            else:
                self.cp8(self.A, val)
            return 19

        else:
            raise NotImplementedError(f"{'FD' if use_iy else 'DD'} opcode {op:02X}")

    cdef int exec_dd(self):
        return self.exec_index(self.fetch8(), False)

    cdef int exec_fd(self):
        return self.exec_index(self.fetch8(), True)

    cdef int exec_main(self, uint8_t op):
        cdef uint16_t addr
        cdef uint16_t nn
        cdef uint16_t tmp16
        cdef uint16_t tmpw
        cdef int8_t disp
        cdef uint8_t tmp8
        cdef uint8_t tmp_hi
        cdef uint16_t memv
        cdef uint16_t hlv

        if op == 0x00:
            return 4
        elif op == 0x76:
            self.halted = True
            return 4
        elif op == 0xCB:
            return self.exec_cb()
        elif op == 0xED:
            return self.exec_ed()
        elif op == 0xDD:
            return self.exec_dd()
        elif op == 0xFD:
            return self.exec_fd()

        elif op == 0x02:
            self.bus.mem_write(self.get_BC(), self.A)
            return 7
        elif op == 0x0A:
            self.A = self.bus.mem_read(self.get_BC())
            return 7
        elif op == 0x12:
            self.bus.mem_write(self.get_DE(), self.A)
            return 7
        elif op == 0x1A:
            self.A = self.bus.mem_read(self.get_DE())
            return 7

        elif op == 0x3E:
            self.A = self.fetch8(); return 7
        elif op == 0x06:
            self.B = self.fetch8(); return 7
        elif op == 0x0E:
            self.C = self.fetch8(); return 7
        elif op == 0x16:
            self.D = self.fetch8(); return 7
        elif op == 0x1E:
            self.E = self.fetch8(); return 7
        elif op == 0x26:
            self.H = self.fetch8(); return 7
        elif op == 0x2E:
            self.L = self.fetch8(); return 7

        elif op == 0x01:
            self.set_BC(self.fetch16()); return 10
        elif op == 0x11:
            self.set_DE(self.fetch16()); return 10
        elif op == 0x21:
            self.set_HL(self.fetch16()); return 10
        elif op == 0x31:
            self.SP = self.fetch16(); return 10

        elif op == 0x40:
            return 4
        elif op == 0x41:
            self.B = self.C; return 4
        elif op == 0x42:
            self.B = self.D; return 4
        elif op == 0x43:
            self.B = self.E; return 4
        elif op == 0x44:
            self.B = self.H; return 4
        elif op == 0x45:
            self.B = self.L; return 4
        elif op == 0x46:
            self.B = self.bus.mem_read(self.get_HL()); return 7
        elif op == 0x47:
            self.B = self.A; return 4

        elif op == 0x48:
            self.C = self.B; return 4
        elif op == 0x49:
            return 4
        elif op == 0x4A:
            self.C = self.D; return 4
        elif op == 0x4B:
            self.C = self.E; return 4
        elif op == 0x4C:
            self.C = self.H; return 4
        elif op == 0x4D:
            self.C = self.L; return 4
        elif op == 0x4E:
            self.C = self.bus.mem_read(self.get_HL()); return 7
        elif op == 0x4F:
            self.C = self.A; return 4

        elif op == 0x50:
            self.D = self.B; return 4
        elif op == 0x51:
            self.D = self.C; return 4
        elif op == 0x52:
            return 4
        elif op == 0x53:
            self.D = self.E; return 4
        elif op == 0x54:
            self.D = self.H; return 4
        elif op == 0x55:
            self.D = self.L; return 4
        elif op == 0x56:
            self.D = self.bus.mem_read(self.get_HL()); return 7
        elif op == 0x57:
            self.D = self.A; return 4

        elif op == 0x58:
            self.E = self.B; return 4
        elif op == 0x59:
            self.E = self.C; return 4
        elif op == 0x5A:
            self.E = self.D; return 4
        elif op == 0x5B:
            return 4
        elif op == 0x5C:
            self.E = self.H; return 4
        elif op == 0x5D:
            self.E = self.L; return 4
        elif op == 0x5E:
            self.E = self.bus.mem_read(self.get_HL()); return 7
        elif op == 0x5F:
            self.E = self.A; return 4

        elif op == 0x60:
            self.H = self.B; return 4
        elif op == 0x61:
            self.H = self.C; return 4
        elif op == 0x62:
            self.H = self.D; return 4
        elif op == 0x63:
            self.H = self.E; return 4
        elif op == 0x64:
            return 4
        elif op == 0x65:
            self.H = self.L; return 4
        elif op == 0x66:
            self.H = self.bus.mem_read(self.get_HL()); return 7
        elif op == 0x67:
            self.H = self.A; return 4

        elif op == 0x68:
            self.L = self.B; return 4
        elif op == 0x69:
            self.L = self.C; return 4
        elif op == 0x6A:
            self.L = self.D; return 4
        elif op == 0x6B:
            self.L = self.E; return 4
        elif op == 0x6C:
            self.L = self.H; return 4
        elif op == 0x6D:
            return 4
        elif op == 0x6E:
            self.L = self.bus.mem_read(self.get_HL()); return 7
        elif op == 0x6F:
            self.L = self.A; return 4

        elif op == 0x70:
            self.bus.mem_write(self.get_HL(), self.B); return 7
        elif op == 0x71:
            self.bus.mem_write(self.get_HL(), self.C); return 7
        elif op == 0x72:
            self.bus.mem_write(self.get_HL(), self.D); return 7
        elif op == 0x73:
            self.bus.mem_write(self.get_HL(), self.E); return 7
        elif op == 0x74:
            self.bus.mem_write(self.get_HL(), self.H); return 7
        elif op == 0x75:
            self.bus.mem_write(self.get_HL(), self.L); return 7
        elif op == 0x77:
            self.bus.mem_write(self.get_HL(), self.A); return 7

        elif op == 0x78:
            self.A = self.B; return 4
        elif op == 0x79:
            self.A = self.C; return 4
        elif op == 0x7A:
            self.A = self.D; return 4
        elif op == 0x7B:
            self.A = self.E; return 4
        elif op == 0x7C:
            self.A = self.H; return 4
        elif op == 0x7D:
            self.A = self.L; return 4
        elif op == 0x7E:
            self.A = self.bus.mem_read(self.get_HL()); return 7
        elif op == 0x7F:
            return 4

        elif op == 0x32:
            addr = self.fetch16(); self.bus.mem_write(addr, self.A); return 13
        elif op == 0x3A:
            addr = self.fetch16(); self.A = self.bus.mem_read(addr); return 13
        elif op == 0x22:
            nn = self.fetch16()
            self.bus.mem_write(nn, self.L)
            self.bus.mem_write(<uint16_t>((nn + 1) & 0xFFFF), self.H)
            return 16
        elif op == 0x2A:
            nn = self.fetch16()
            self.L = self.bus.mem_read(nn)
            self.H = self.bus.mem_read(<uint16_t>((nn + 1) & 0xFFFF))
            return 16
        elif op == 0x36:
            self.bus.mem_write(self.get_HL(), self.fetch8()); return 10

        elif op == 0x3C:
            self.A = self.inc8(self.A); return 4
        elif op == 0x04:
            self.B = self.inc8(self.B); return 4
        elif op == 0x0C:
            self.C = self.inc8(self.C); return 4
        elif op == 0x14:
            self.D = self.inc8(self.D); return 4
        elif op == 0x1C:
            self.E = self.inc8(self.E); return 4
        elif op == 0x24:
            self.H = self.inc8(self.H); return 4
        elif op == 0x2C:
            self.L = self.inc8(self.L); return 4
        elif op == 0x34:
            addr = self.get_HL()
            tmp8 = self.bus.mem_read(addr)
            tmp8 = self.inc8(tmp8)
            self.bus.mem_write(addr, tmp8)
            return 11

        elif op == 0x3D:
            self.A = self.dec8(self.A); return 4
        elif op == 0x05:
            self.B = self.dec8(self.B); return 4
        elif op == 0x0D:
            self.C = self.dec8(self.C); return 4
        elif op == 0x15:
            self.D = self.dec8(self.D); return 4
        elif op == 0x1D:
            self.E = self.dec8(self.E); return 4
        elif op == 0x25:
            self.H = self.dec8(self.H); return 4
        elif op == 0x2D:
            self.L = self.dec8(self.L); return 4
        elif op == 0x35:
            addr = self.get_HL()
            tmp8 = self.bus.mem_read(addr)
            tmp8 = self.dec8(tmp8)
            self.bus.mem_write(addr, tmp8)
            return 11

        elif op == 0x03:
            self.set_BC(<uint16_t>((self.get_BC() + 1) & 0xFFFF)); return 6
        elif op == 0x13:
            self.set_DE(<uint16_t>((self.get_DE() + 1) & 0xFFFF)); return 6
        elif op == 0x23:
            self.set_HL(<uint16_t>((self.get_HL() + 1) & 0xFFFF)); return 6
        elif op == 0x33:
            self.SP = <uint16_t>((self.SP + 1) & 0xFFFF); return 6
        elif op == 0x0B:
            self.set_BC(<uint16_t>((self.get_BC() - 1) & 0xFFFF)); return 6
        elif op == 0x1B:
            self.set_DE(<uint16_t>((self.get_DE() - 1) & 0xFFFF)); return 6
        elif op == 0x2B:
            self.set_HL(<uint16_t>((self.get_HL() - 1) & 0xFFFF)); return 6
        elif op == 0x3B:
            self.SP = <uint16_t>((self.SP - 1) & 0xFFFF); return 6

        elif op == 0x09:
            self.set_HL(self.add16(self.get_HL(), self.get_BC())); return 11
        elif op == 0x19:
            self.set_HL(self.add16(self.get_HL(), self.get_DE())); return 11
        elif op == 0x29:
            self.set_HL(self.add16(self.get_HL(), self.get_HL())); return 11
        elif op == 0x39:
            self.set_HL(self.add16(self.get_HL(), self.SP)); return 11

        elif op == 0xE3:
            addr = self.SP
            tmp8 = self.bus.mem_read(addr)
            tmp_hi = self.bus.mem_read(<uint16_t>((addr + 1) & 0xFFFF))
            memv = <uint16_t>(tmp8 | (tmp_hi << 8))
            hlv = self.get_HL()

            self.bus.mem_write(addr, <uint8_t>(hlv & 0xFF))
            self.bus.mem_write(<uint16_t>((addr + 1) & 0xFFFF), <uint8_t>((hlv >> 8) & 0xFF))

            self.set_HL(memv)
            return 19

        elif op == 0xEB:
            tmpw = self.get_DE()
            self.set_DE(self.get_HL())
            self.set_HL(tmpw)
            return 4

        elif op == 0xF9:
            self.SP = self.get_HL()
            return 6

        elif op == 0x07:
            tmp8 = <uint8_t>((self.A >> 7) & 1)
            self.A = <uint8_t>(((self.A << 1) | tmp8) & 0xFF)
            self.F = <uint8_t>((self.F & (FLAG_S | FLAG_Z | FLAG_PV)) | (FLAG_C if tmp8 else 0))
            return 4

        elif op == 0x0F:
            tmp8 = <uint8_t>(self.A & 1)
            self.A = <uint8_t>(((self.A >> 1) | (tmp8 << 7)) & 0xFF)
            self.F = <uint8_t>((self.F & (FLAG_S | FLAG_Z | FLAG_PV)) | (FLAG_C if tmp8 else 0))
            return 4

        elif op == 0x17:
            tmp8 = <uint8_t>((self.A >> 7) & 1)
            self.A = <uint8_t>(((self.A << 1) | (1 if (self.F & FLAG_C) else 0)) & 0xFF)
            self.F = <uint8_t>((self.F & (FLAG_S | FLAG_Z | FLAG_PV)) | (FLAG_C if tmp8 else 0))
            return 4

        elif op == 0x1F:
            tmp8 = <uint8_t>(self.A & 1)
            self.A = <uint8_t>(((self.A >> 1) | ((1 if (self.F & FLAG_C) else 0) << 7)) & 0xFF)
            self.F = <uint8_t>((self.F & (FLAG_S | FLAG_Z | FLAG_PV)) | (FLAG_C if tmp8 else 0))
            return 4

        elif op == 0x87:
            self.A = self.add8(self.A, self.A); return 4
        elif op == 0x80:
            self.A = self.add8(self.A, self.B); return 4
        elif op == 0x81:
            self.A = self.add8(self.A, self.C); return 4
        elif op == 0x82:
            self.A = self.add8(self.A, self.D); return 4
        elif op == 0x83:
            self.A = self.add8(self.A, self.E); return 4
        elif op == 0x84:
            self.A = self.add8(self.A, self.H); return 4
        elif op == 0x85:
            self.A = self.add8(self.A, self.L); return 4
        elif op == 0x86:
            self.A = self.add8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xC6:
            self.A = self.add8(self.A, self.fetch8()); return 7

        elif op == 0x8F:
            self.A = self.adc8(self.A, self.A); return 4
        elif op == 0x88:
            self.A = self.adc8(self.A, self.B); return 4
        elif op == 0x89:
            self.A = self.adc8(self.A, self.C); return 4
        elif op == 0x8A:
            self.A = self.adc8(self.A, self.D); return 4
        elif op == 0x8B:
            self.A = self.adc8(self.A, self.E); return 4
        elif op == 0x8C:
            self.A = self.adc8(self.A, self.H); return 4
        elif op == 0x8D:
            self.A = self.adc8(self.A, self.L); return 4
        elif op == 0x8E:
            self.A = self.adc8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xCE:
            self.A = self.adc8(self.A, self.fetch8()); return 7

        elif op == 0x97:
            self.A = self.sub8(self.A, self.A); return 4
        elif op == 0x90:
            self.A = self.sub8(self.A, self.B); return 4
        elif op == 0x91:
            self.A = self.sub8(self.A, self.C); return 4
        elif op == 0x92:
            self.A = self.sub8(self.A, self.D); return 4
        elif op == 0x93:
            self.A = self.sub8(self.A, self.E); return 4
        elif op == 0x94:
            self.A = self.sub8(self.A, self.H); return 4
        elif op == 0x95:
            self.A = self.sub8(self.A, self.L); return 4
        elif op == 0x96:
            self.A = self.sub8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xD6:
            self.A = self.sub8(self.A, self.fetch8()); return 7

        elif op == 0x9F:
            self.A = self.sbc8(self.A, self.A); return 4
        elif op == 0x98:
            self.A = self.sbc8(self.A, self.B); return 4
        elif op == 0x99:
            self.A = self.sbc8(self.A, self.C); return 4
        elif op == 0x9A:
            self.A = self.sbc8(self.A, self.D); return 4
        elif op == 0x9B:
            self.A = self.sbc8(self.A, self.E); return 4
        elif op == 0x9C:
            self.A = self.sbc8(self.A, self.H); return 4
        elif op == 0x9D:
            self.A = self.sbc8(self.A, self.L); return 4
        elif op == 0x9E:
            self.A = self.sbc8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xDE:
            self.A = self.sbc8(self.A, self.fetch8()); return 7

        elif op == 0xA7:
            self.A = self.and8(self.A, self.A); return 4
        elif op == 0xA0:
            self.A = self.and8(self.A, self.B); return 4
        elif op == 0xA1:
            self.A = self.and8(self.A, self.C); return 4
        elif op == 0xA2:
            self.A = self.and8(self.A, self.D); return 4
        elif op == 0xA3:
            self.A = self.and8(self.A, self.E); return 4
        elif op == 0xA4:
            self.A = self.and8(self.A, self.H); return 4
        elif op == 0xA5:
            self.A = self.and8(self.A, self.L); return 4
        elif op == 0xA6:
            self.A = self.and8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xE6:
            self.A = self.and8(self.A, self.fetch8()); return 7

        elif op == 0xB7:
            self.A = self.or8(self.A, self.A); return 4
        elif op == 0xB0:
            self.A = self.or8(self.A, self.B); return 4
        elif op == 0xB1:
            self.A = self.or8(self.A, self.C); return 4
        elif op == 0xB2:
            self.A = self.or8(self.A, self.D); return 4
        elif op == 0xB3:
            self.A = self.or8(self.A, self.E); return 4
        elif op == 0xB4:
            self.A = self.or8(self.A, self.H); return 4
        elif op == 0xB5:
            self.A = self.or8(self.A, self.L); return 4
        elif op == 0xB6:
            self.A = self.or8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xF6:
            self.A = self.or8(self.A, self.fetch8()); return 7

        elif op == 0xAF:
            self.A = self.xor8(self.A, self.A); return 4
        elif op == 0xA8:
            self.A = self.xor8(self.A, self.B); return 4
        elif op == 0xA9:
            self.A = self.xor8(self.A, self.C); return 4
        elif op == 0xAA:
            self.A = self.xor8(self.A, self.D); return 4
        elif op == 0xAB:
            self.A = self.xor8(self.A, self.E); return 4
        elif op == 0xAC:
            self.A = self.xor8(self.A, self.H); return 4
        elif op == 0xAD:
            self.A = self.xor8(self.A, self.L); return 4
        elif op == 0xAE:
            self.A = self.xor8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xEE:
            self.A = self.xor8(self.A, self.fetch8()); return 7

        elif op == 0xBF:
            self.cp8(self.A, self.A); return 4
        elif op == 0xB8:
            self.cp8(self.A, self.B); return 4
        elif op == 0xB9:
            self.cp8(self.A, self.C); return 4
        elif op == 0xBA:
            self.cp8(self.A, self.D); return 4
        elif op == 0xBB:
            self.cp8(self.A, self.E); return 4
        elif op == 0xBC:
            self.cp8(self.A, self.H); return 4
        elif op == 0xBD:
            self.cp8(self.A, self.L); return 4
        elif op == 0xBE:
            self.cp8(self.A, self.bus.mem_read(self.get_HL())); return 7
        elif op == 0xFE:
            self.cp8(self.A, self.fetch8()); return 7

        elif op == 0x10:
            disp = <int8_t>self.fetch8()
            self.B = <uint8_t>((self.B - 1) & 0xFF)
            if self.B != 0:
                self.PC = <uint16_t>((self.PC + disp) & 0xFFFF); return 13
            return 8

        elif op == 0x18:
            disp = <int8_t>self.fetch8(); self.PC = <uint16_t>((self.PC + disp) & 0xFFFF); return 12
        elif op == 0x20:
            disp = <int8_t>self.fetch8()
            if self.cond_nz(): self.PC = <uint16_t>((self.PC + disp) & 0xFFFF); return 12
            return 7
        elif op == 0x28:
            disp = <int8_t>self.fetch8()
            if self.cond_z(): self.PC = <uint16_t>((self.PC + disp) & 0xFFFF); return 12
            return 7
        elif op == 0x30:
            disp = <int8_t>self.fetch8()
            if self.cond_nc(): self.PC = <uint16_t>((self.PC + disp) & 0xFFFF); return 12
            return 7
        elif op == 0x38:
            disp = <int8_t>self.fetch8()
            if self.cond_c(): self.PC = <uint16_t>((self.PC + disp) & 0xFFFF); return 12
            return 7

        elif op == 0xC3:
            self.PC = self.fetch16(); return 10
        elif op == 0xC2:
            nn = self.fetch16()
            if self.cond_nz(): self.PC = nn
            return 10
        elif op == 0xCA:
            nn = self.fetch16()
            if self.cond_z(): self.PC = nn
            return 10
        elif op == 0xD2:
            nn = self.fetch16()
            if self.cond_nc(): self.PC = nn
            return 10
        elif op == 0xDA:
            nn = self.fetch16()
            if self.cond_c(): self.PC = nn
            return 10
        elif op == 0xE2:
            nn = self.fetch16()
            if self.cond_po(): self.PC = nn
            return 10
        elif op == 0xEA:
            nn = self.fetch16()
            if self.cond_pe(): self.PC = nn
            return 10
        elif op == 0xF2:
            nn = self.fetch16()
            if self.cond_p(): self.PC = nn
            return 10
        elif op == 0xFA:
            nn = self.fetch16()
            if self.cond_m(): self.PC = nn
            return 10
        elif op == 0xE9:
            self.PC = self.get_HL(); return 4

        elif op == 0xCD:
            nn = self.fetch16(); self.push16(self.PC); self.PC = nn; return 17
        elif op == 0xC4:
            nn = self.fetch16()
            if self.cond_nz(): self.push16(self.PC); self.PC = nn; return 17
            return 10
        elif op == 0xCC:
            nn = self.fetch16()
            if self.cond_z(): self.push16(self.PC); self.PC = nn; return 17
            return 10
        elif op == 0xD4:
            nn = self.fetch16()
            if self.cond_nc(): self.push16(self.PC); self.PC = nn; return 17
            return 10
        elif op == 0xDC:
            nn = self.fetch16()
            if self.cond_c(): self.push16(self.PC); self.PC = nn; return 17
            return 10
        elif op == 0xE4:
            nn = self.fetch16()
            if self.cond_po(): self.push16(self.PC); self.PC = nn; return 17
            return 10
        elif op == 0xEC:
            nn = self.fetch16()
            if self.cond_pe(): self.push16(self.PC); self.PC = nn; return 17
            return 10
        elif op == 0xF4:
            nn = self.fetch16()
            if self.cond_p(): self.push16(self.PC); self.PC = nn; return 17
            return 10
        elif op == 0xFC:
            nn = self.fetch16()
            if self.cond_m(): self.push16(self.PC); self.PC = nn; return 17
            return 10

        elif op == 0xC9:
            self.PC = self.pop16(); return 10
        elif op == 0xC0:
            if self.cond_nz(): self.PC = self.pop16(); return 11
            return 5
        elif op == 0xC8:
            if self.cond_z(): self.PC = self.pop16(); return 11
            return 5
        elif op == 0xD0:
            if self.cond_nc(): self.PC = self.pop16(); return 11
            return 5
        elif op == 0xD8:
            if self.cond_c(): self.PC = self.pop16(); return 11
            return 5
        elif op == 0xE0:
            if self.cond_po(): self.PC = self.pop16(); return 11
            return 5
        elif op == 0xE8:
            if self.cond_pe(): self.PC = self.pop16(); return 11
            return 5
        elif op == 0xF0:
            if self.cond_p(): self.PC = self.pop16(); return 11
            return 5
        elif op == 0xF8:
            if self.cond_m(): self.PC = self.pop16(); return 11
            return 5

        elif op == 0xC7:
            self.push16(self.PC); self.PC = 0x0000; return 11
        elif op == 0xCF:
            self.push16(self.PC); self.PC = 0x0008; return 11
        elif op == 0xD7:
            self.push16(self.PC); self.PC = 0x0010; return 11
        elif op == 0xDF:
            self.push16(self.PC); self.PC = 0x0018; return 11
        elif op == 0xE7:
            self.push16(self.PC); self.PC = 0x0020; return 11
        elif op == 0xEF:
            self.push16(self.PC); self.PC = 0x0028; return 11
        elif op == 0xF7:
            self.push16(self.PC); self.PC = 0x0030; return 11
        elif op == 0xFF:
            self.push16(self.PC); self.PC = 0x0038; return 11

        elif op == 0x2F:
            self.A = <uint8_t>(self.A ^ 0xFF)
            self.F = <uint8_t>((self.F & (FLAG_S | FLAG_Z | FLAG_PV | FLAG_C)) | FLAG_H | FLAG_N)
            return 4
        elif op == 0x37:
            self.F = <uint8_t>((self.F & (FLAG_S | FLAG_Z | FLAG_PV)) | FLAG_C); return 4
        elif op == 0x3F:
            tmp8 = <uint8_t>(1 if (self.F & FLAG_C) else 0)
            self.F = <uint8_t>(self.F & (FLAG_S | FLAG_Z | FLAG_PV))
            if tmp8: self.F |= FLAG_H
            else: self.F |= FLAG_C
            return 4
        elif op == 0x27:
            self.daa(); return 4

        elif op == 0xC5:
            self.push16(self.get_BC()); return 11
        elif op == 0xD5:
            self.push16(self.get_DE()); return 11
        elif op == 0xE5:
            self.push16(self.get_HL()); return 11
        elif op == 0xF5:
            self.push16(<uint16_t>((self.A << 8) | self.F)); return 11
        elif op == 0xC1:
            self.set_BC(self.pop16()); return 10
        elif op == 0xD1:
            self.set_DE(self.pop16()); return 10
        elif op == 0xE1:
            self.set_HL(self.pop16()); return 10
        elif op == 0xF1:
            tmp16 = self.pop16()
            self.A = <uint8_t>((tmp16 >> 8) & 0xFF)
            self.F = <uint8_t>(tmp16 & 0xFF)
            return 10

        elif op == 0x08:
            tmp8 = self.A; self.A = self.A2; self.A2 = tmp8
            tmp8 = self.F; self.F = self.F2; self.F2 = tmp8
            return 4
        elif op == 0xD9:
            tmp8 = self.B; self.B = self.B2; self.B2 = tmp8
            tmp8 = self.C; self.C = self.C2; self.C2 = tmp8
            tmp8 = self.D; self.D = self.D2; self.D2 = tmp8
            tmp8 = self.E; self.E = self.E2; self.E2 = tmp8
            tmp8 = self.H; self.H = self.H2; self.H2 = tmp8
            tmp8 = self.L; self.L = self.L2; self.L2 = tmp8
            return 4

        elif op == 0xF3:
            self.iff1 = False; self.iff2 = False; return 4
        elif op == 0xFB:
            self.ei_pending = True; return 4

        elif op == 0xDB:
            tmp8 = self.fetch8()
            self.A = self.bus.io_read(<uint16_t>((self.A << 8) | tmp8))
            return 11
        elif op == 0xD3:
            tmp8 = self.fetch8()
            self.bus.io_write(<uint16_t>((self.A << 8) | tmp8), self.A)
            return 11

        else:
            raise NotImplementedError(f"opcode {op:02X}")

    cpdef int step(self):
        cdef uint8_t op
        cdef int cycles

        if self.halted:
            return 4

        op = self.fetch8()
        cycles = self.exec_main(op)

        if self.ei_pending:
            self.iff1 = True
            self.iff2 = True
            self.ei_pending = False

        return cycles

    cpdef int run_cycles(self, int cycles):
        cdef int used = 0
        while used < cycles and not self.halted:
            used += self.step()
        return used

    cpdef bint is_halted(self):
        return self.halted

    cpdef dict snapshot(self):
        return {
            "A": self.A, "F": self.F,
            "B": self.B, "C": self.C,
            "D": self.D, "E": self.E,
            "H": self.H, "L": self.L,

            "A2": self.A2, "F2": self.F2,
            "B2": self.B2, "C2": self.C2,
            "D2": self.D2, "E2": self.E2,
            "H2": self.H2, "L2": self.L2,

            "BC": self.get_BC(),
            "DE": self.get_DE(),
            "HL": self.get_HL(),

            "IX": self.IX,
            "IY": self.IY,
            "I": self.I,
            "R": self.R,

            "PC": self.PC,
            "SP": self.SP,

            "IFF1": bool(self.iff1),
            "IFF2": bool(self.iff2),
            "IM": self.im,
            "halted": bool(self.halted),
        }
