# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from libc.stdlib cimport malloc, free
from multiemu.state_codec import read_state_fields, write_state_fields


cdef class MemoryBlock:
    cdef public int size
    cdef public bint writable
    cdef unsigned char* data

    def __cinit__(self, int size):
        cdef int i
        if size <= 0 or size > 65536:
            raise ValueError("size fuera de rango")
        self.size = size
        self.writable = True
        self.data = <unsigned char*>malloc(size)
        if self.data == NULL:
            raise MemoryError()
        for i in range(size):
            self.data[i] = 0

    def __dealloc__(self):
        if self.data != NULL:
            free(self.data)
            self.data = NULL

    cpdef int read(self, int addr):
        if 0 <= addr < self.size:
            return self.data[addr]
        return 0xFF

    cpdef void write(self, int addr, int value):
        if self.writable and 0 <= addr < self.size:
            self.data[addr] = value & 0xFF

    cpdef load(self, int addr, bytes data):
        cdef Py_ssize_t i
        cdef Py_ssize_t n = len(data)
        cdef int end = addr + n
        if addr < 0 or end > self.size:
            raise ValueError("rango fuera de RAM")
        for i in range(n):
            self.data[addr + i] = data[i]

    cpdef int peek(self, int addr):
        return self.read(addr)

    def read_state(self) -> dict:
        cdef int i
        state = read_state_fields(
            self,
            scalar_fields=("size", "writable"),
            meta={"type": type(self).__name__},
        )
        state["data"] = [self.data[i] for i in range(self.size)]
        return state

    def write_state(self, state: dict) -> None:
        cdef int i
        cdef list data
        write_state_fields(self, state, scalar_fields=("writable",))
        if "data" in state:
            data = state["data"]
            if len(data) != self.size:
                raise ValueError("longitud de data incompatible con bloque de memoria")
            for i in range(self.size):
                self.data[i] = data[i] & 0xFF


cdef class RAMBlock(MemoryBlock):
    pass


cdef class ROMBlock(MemoryBlock):

    def __cinit__(self, int size):
        cdef int i
        self.writable = False
        for i in range(size):
            self.data[i] = 0xFF

    cpdef void write(self, int addr, int value):
        return

    cpdef load_bytes(self, bytes data, int offset=0):
        cdef Py_ssize_t i
        cdef Py_ssize_t n = len(data)
        cdef int end = offset + n
        if offset < 0 or end > self.size:
            raise ValueError("rango fuera de ROM")
        for i in range(n):
            self.data[offset + i] = data[i]

    cpdef int peek(self, int addr):
        return self.read(addr)
