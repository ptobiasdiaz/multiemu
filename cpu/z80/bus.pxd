from .types cimport uint8_t, uint16_t, uint32_t
from .memory cimport MemoryBlock
from .io cimport PortHandler

cdef class MemoryDevice:
    cpdef uint8_t read(self, uint16_t addr)
    cpdef void write(self, uint16_t addr, uint8_t value)


cdef class Z80Bus:
    cdef list page_blocks
    cdef list page_devices
    cdef list port_handlers

    cdef uint8_t* page_ptrs[16]
    cdef uint16_t page_offsets[16]
    cdef uint8_t page_writable[16]

    cpdef map_block(self, int start, MemoryBlock block)
    cpdef map_device(self, int start, int size, MemoryDevice device)
    cpdef unmap(self, int start, int size)

    cpdef set_port_handler(self, int port, PortHandler handler)

    cdef uint8_t mem_read(self, uint16_t addr) noexcept
    cdef void mem_write(self, uint16_t addr, uint8_t value) noexcept

    cdef uint8_t io_read(self, uint16_t port)
    cdef void io_write(self, uint16_t port, uint8_t value)
