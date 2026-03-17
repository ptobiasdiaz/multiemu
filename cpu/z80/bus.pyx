# cython: boundscheck=False
# cython: wraparound=False

from .types cimport uint8_t, uint16_t
from .bus cimport Z80Bus, MemoryDevice
from .memory cimport MemoryBlock
from .io cimport PortHandler

cdef int PAGE_SHIFT = 12
cdef int PAGE_SIZE = 0x1000
cdef int PAGE_MASK = 0x0FFF
cdef int PAGE_COUNT = 16


cdef class MemoryDevice:

    cpdef uint8_t read(self, uint16_t addr):
        return 0xFF

    cpdef void write(self, uint16_t addr, uint8_t value):
        pass


cdef class Z80Bus:

    def __cinit__(self):
        cdef int i

        self.page_blocks = [None] * PAGE_COUNT
        self.page_devices = [None] * PAGE_COUNT
        self.port_handlers = [None] * 256

        for i in range(PAGE_COUNT):
            self.page_ptrs[i] = NULL
            self.page_offsets[i] = 0
            self.page_writable[i] = 0

        for i in range(256):
            self.port_handlers[i] = PortHandler()

    cpdef map_block(self, int start, MemoryBlock block):
        cdef int page_start
        cdef int page_count
        cdef int i
        cdef int offset

        if start < 0 or start > 0xFFFF:
            raise ValueError("start fuera de rango")
        if (start & (PAGE_SIZE - 1)) != 0:
            raise ValueError("start debe estar alineado a 4 KB")
        if (block.size & (PAGE_SIZE - 1)) != 0:
            raise ValueError("el tamaño del bloque debe ser múltiplo de 4 KB")

        page_start = start >> PAGE_SHIFT
        page_count = block.size >> PAGE_SHIFT

        if page_start + page_count > PAGE_COUNT:
            raise ValueError("el bloque se sale del espacio de direcciones")

        for i in range(page_count):
            offset = i << PAGE_SHIFT
            self.page_blocks[page_start + i] = block
            self.page_devices[page_start + i] = None
            self.page_ptrs[page_start + i] = block.data + offset
            self.page_offsets[page_start + i] = <uint16_t>offset
            self.page_writable[page_start + i] = 1 if block.writable else 0

    cpdef map_device(self, int start, int size, MemoryDevice device):
        cdef int page_start
        cdef int page_count
        cdef int i

        if start < 0 or start > 0xFFFF:
            raise ValueError("start fuera de rango")
        if size <= 0:
            raise ValueError("size inválido")
        if (start & (PAGE_SIZE - 1)) != 0:
            raise ValueError("start debe estar alineado a 4 KB")
        if (size & (PAGE_SIZE - 1)) != 0:
            raise ValueError("size debe ser múltiplo de 4 KB")

        page_start = start >> PAGE_SHIFT
        page_count = size >> PAGE_SHIFT

        if page_start + page_count > PAGE_COUNT:
            raise ValueError("el dispositivo se sale del espacio de direcciones")

        for i in range(page_count):
            self.page_blocks[page_start + i] = None
            self.page_devices[page_start + i] = device
            self.page_ptrs[page_start + i] = NULL
            self.page_offsets[page_start + i] = 0
            self.page_writable[page_start + i] = 0

    cpdef unmap(self, int start, int size):
        cdef int page_start
        cdef int page_count
        cdef int i

        if start < 0 or start > 0xFFFF:
            raise ValueError("start fuera de rango")
        if size <= 0:
            raise ValueError("size inválido")
        if (start & (PAGE_SIZE - 1)) != 0:
            raise ValueError("start debe estar alineado a 4 KB")
        if (size & (PAGE_SIZE - 1)) != 0:
            raise ValueError("size debe ser múltiplo de 4 KB")

        page_start = start >> PAGE_SHIFT
        page_count = size >> PAGE_SHIFT

        if page_start + page_count > PAGE_COUNT:
            raise ValueError("unmap fuera de rango")

        for i in range(page_count):
            self.page_blocks[page_start + i] = None
            self.page_devices[page_start + i] = None
            self.page_ptrs[page_start + i] = NULL
            self.page_offsets[page_start + i] = 0
            self.page_writable[page_start + i] = 0

    cpdef set_port_handler(self, int port, PortHandler handler):
        if port < 0 or port > 0xFF:
            raise ValueError("port fuera de rango (0..255)")
        self.port_handlers[port] = handler

    cdef uint8_t mem_read(self, uint16_t addr) noexcept:
        cdef int page = addr >> PAGE_SHIFT
        cdef uint8_t* ptr = self.page_ptrs[page]
        cdef MemoryDevice dev

        if ptr != NULL:
            return ptr[addr & PAGE_MASK]

        dev = <MemoryDevice>self.page_devices[page]
        if dev is not None:
            return dev.read(addr)

        return 0xFF

    cdef void mem_write(self, uint16_t addr, uint8_t value) noexcept:
        cdef int page = addr >> PAGE_SHIFT
        cdef uint8_t* ptr = self.page_ptrs[page]
        cdef MemoryDevice dev

        if ptr != NULL:
            if self.page_writable[page]:
                ptr[addr & PAGE_MASK] = value
            return

        dev = <MemoryDevice>self.page_devices[page]
        if dev is not None:
            dev.write(addr, value)

    cdef uint8_t io_read(self, uint16_t port):
        cdef PortHandler handler = <PortHandler>self.port_handlers[port & 0xFF]
        return handler.read(port)

    cdef void io_write(self, uint16_t port, uint8_t value):
        cdef PortHandler handler = <PortHandler>self.port_handlers[port & 0xFF]
        handler.write(port, value)
