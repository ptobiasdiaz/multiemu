from .types cimport uint8_t, uint16_t
from .bus cimport Z80Bus

cdef class Z80Core:
    cdef Z80Bus bus

    cdef uint8_t A, F
    cdef uint8_t B, C
    cdef uint8_t D, E
    cdef uint8_t H, L

    cdef uint8_t A2, F2
    cdef uint8_t B2, C2
    cdef uint8_t D2, E2
    cdef uint8_t H2, L2

    cdef uint16_t IX, IY
    cdef uint8_t I, R

    cdef uint16_t PC, SP

    cdef bint halted
    cdef bint iff1
    cdef bint iff2
    cdef uint8_t im
    cdef bint ei_pending

    cdef uint8_t fetch8(self)
    cdef uint16_t fetch16(self)

    cdef uint16_t get_BC(self)
    cdef uint16_t get_DE(self)
    cdef uint16_t get_HL(self)

    cdef void set_BC(self, uint16_t v)
    cdef void set_DE(self, uint16_t v)
    cdef void set_HL(self, uint16_t v)

    cdef uint8_t get_IXH(self)
    cdef uint8_t get_IXL(self)
    cdef uint8_t get_IYH(self)
    cdef uint8_t get_IYL(self)

    cdef void set_IXH(self, uint8_t v)
    cdef void set_IXL(self, uint8_t v)
    cdef void set_IYH(self, uint8_t v)
    cdef void set_IYL(self, uint8_t v)

    cdef uint8_t parity_even(self, uint8_t v)

    cdef uint8_t add8(self, uint8_t a, uint8_t b)
    cdef uint8_t adc8(self, uint8_t a, uint8_t b)
    cdef uint8_t sub8(self, uint8_t a, uint8_t b)
    cdef uint8_t sbc8(self, uint8_t a, uint8_t b)
    cdef uint16_t adc16(self, uint16_t a, uint16_t b)
    cdef uint16_t sbc16(self, uint16_t a, uint16_t b)
    cdef uint16_t add16(self, uint16_t a, uint16_t b)

    cdef uint8_t and8(self, uint8_t a, uint8_t b)
    cdef uint8_t or8(self, uint8_t a, uint8_t b)
    cdef uint8_t xor8(self, uint8_t a, uint8_t b)
    cdef void cp8(self, uint8_t a, uint8_t b)
    cdef uint8_t inc8(self, uint8_t v)
    cdef uint8_t dec8(self, uint8_t v)
    cdef void daa(self)

    cdef uint8_t rlc8(self, uint8_t v)
    cdef uint8_t rrc8(self, uint8_t v)
    cdef uint8_t rl8(self, uint8_t v)
    cdef uint8_t rr8(self, uint8_t v)
    cdef uint8_t sla8(self, uint8_t v)
    cdef uint8_t sra8(self, uint8_t v)
    cdef uint8_t srl8(self, uint8_t v)
    cdef void bit8(self, uint8_t bit, uint8_t v)

    cdef void push16(self, uint16_t v)
    cdef uint16_t pop16(self)

    cdef bint cond_nz(self)
    cdef bint cond_z(self)
    cdef bint cond_nc(self)
    cdef bint cond_c(self)
    cdef bint cond_po(self)
    cdef bint cond_pe(self)
    cdef bint cond_p(self)
    cdef bint cond_m(self)

    cdef int exec_main(self, uint8_t op)
    cdef int exec_cb(self)
    cdef int exec_ed(self)
    cdef int exec_dd(self)
    cdef int exec_fd(self)
    cdef int exec_index(self, uint8_t op, bint use_iy)
    cdef int exec_index_cb(self, bint use_iy)

    cpdef reset(self)
    cpdef int step(self)
    cpdef int run_cycles(self, int cycles)
    cpdef dict snapshot(self)
    cpdef bint is_halted(self)
    cpdef interrupt(self)
