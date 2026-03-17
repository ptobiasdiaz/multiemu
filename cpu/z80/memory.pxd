from .types cimport uint8_t, uint16_t, uint32_t

cdef class MemoryBlock:
    cdef uint32_t size
    cdef uint8_t* data
    cdef bint writable

    cdef uint8_t read(self, uint16_t addr) noexcept
    cdef void write(self, uint16_t addr, uint8_t value) noexcept
    cpdef load(self, int offset, bytes data)
    cpdef int peek(self, int addr)


cdef class RAMBlock(MemoryBlock):
    pass


cdef class ROMBlock(MemoryBlock):
    cpdef load_bytes(self, bytes data)
