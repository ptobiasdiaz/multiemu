# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from multiemu.state_codec import read_state_fields, write_state_fields


cdef class OpenBus:
    cdef public int size

    def __cinit__(self):
        self.size = 0x0400

    cpdef int read(self, int addr):
        return 0xFF

    cpdef void write(self, int addr, int value):
        return

    def read_state(self) -> dict:
        return read_state_fields(self, scalar_fields=("size",), meta={"type": "OpenBus"})

    def write_state(self, state: dict) -> None:
        write_state_fields(self, state, scalar_fields=("size",))


cdef class ColorRAM:
    cdef public int size
    cdef bytearray data

    def __cinit__(self):
        self.size = 0x0400
        self.data = bytearray(self.size)

    cpdef int read(self, int addr):
        if 0 <= addr < self.size:
            return self.data[addr] & 0x0F
        return 0x0F

    cpdef void write(self, int addr, int value):
        if 0 <= addr < self.size:
            self.data[addr] = value & 0x0F

    cpdef int peek(self, int addr):
        return self.read(addr)

    cpdef void clear(self):
        self.data[:] = bytes(self.size)

    def read_state(self) -> dict:
        return read_state_fields(
            self,
            scalar_fields=("size",),
            byte_fields=("data",),
            meta={"type": "ColorRAM"},
        )

    def write_state(self, state: dict) -> None:
        write_state_fields(self, state, scalar_fields=("size",), byte_fields=("data",))


cdef class IoRam:
    cdef public int size
    cdef bytearray data

    def __cinit__(self):
        self.size = 0x0400
        self.data = bytearray(self.size)

    cpdef int read(self, int addr):
        if 0 <= addr < self.size:
            return self.data[addr]
        return 0xFF

    cpdef void write(self, int addr, int value):
        if 0 <= addr < self.size:
            self.data[addr] = value & 0xFF

    cpdef void clear(self):
        self.data[:] = bytes(self.size)

    def read_state(self) -> dict:
        return read_state_fields(
            self,
            scalar_fields=("size",),
            byte_fields=("data",),
            meta={"type": "IoRam"},
        )

    def write_state(self, state: dict) -> None:
        write_state_fields(self, state, scalar_fields=("size",), byte_fields=("data",))
