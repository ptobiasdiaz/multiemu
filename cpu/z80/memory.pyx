# cython: boundscheck=False
# cython: wraparound=False

from libc.stdlib cimport malloc, free
from .types cimport uint8_t, uint16_t, uint32_t
from .memory cimport MemoryBlock


cdef class MemoryBlock:

    def __cinit__(self, int size):
        if size <= 0 or size > 65536:
            raise ValueError("size fuera de rango")

        self.size = <uint32_t>size
        self.writable = True
        self.data = <uint8_t*>malloc(size)

        if self.data == NULL:
            raise MemoryError()

        cdef int i
        for i in range(size):
            self.data[i] = 0

    def __dealloc__(self):
        if self.data != NULL:
            free(self.data)
            self.data = NULL

    cdef uint8_t read(self, uint16_t addr) noexcept:
        return self.data[addr]

    cdef void write(self, uint16_t addr, uint8_t value) noexcept:
        if self.writable:
            self.data[addr] = value

    cpdef load(self, int offset, bytes data):
        cdef Py_ssize_t i
        cdef Py_ssize_t n = len(data)

        if offset < 0 or offset + n > self.size:
            raise ValueError("load fuera de rango")

        if not self.writable:
            raise ValueError("el bloque no es escribible")

        for i in range(n):
            self.data[offset + i] = <uint8_t>data[i]

    cpdef int peek(self, int addr):
        if addr < 0 or addr >= self.size:
            raise ValueError("peek fuera de rango")
        return self.data[addr]


cdef class RAMBlock(MemoryBlock):
    pass


cdef class ROMBlock(MemoryBlock):

    def __cinit__(self, int size):
        self.writable = False

    cpdef load_bytes(self, bytes data):
        cdef Py_ssize_t i
        cdef Py_ssize_t n = len(data)

        if n > self.size:
            raise ValueError("ROM demasiado grande")

        for i in range(n):
            self.data[i] = <uint8_t>data[i]
