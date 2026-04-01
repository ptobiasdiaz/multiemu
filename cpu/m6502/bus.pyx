# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from __future__ import annotations

cdef int PAGE_SHIFT = 8
cdef int PAGE_SIZE = 0x100
cdef int PAGE_MASK = 0xFF
cdef int PAGE_COUNT = 0x100


cdef class MemoryDevice:

    cpdef int read(self, int addr):
        return 0xFF

    cpdef void write(self, int addr, int value):
        return


cdef class M6502Bus:
    cdef list _mapped
    cdef list _page_entries
    cdef public bint irq_pending
    cdef public bint nmi_pending

    def __cinit__(self):
        self._mapped = []
        self._page_entries = [None] * PAGE_COUNT
        self.irq_pending = False
        self.nmi_pending = False

    cpdef map_block(self, int start, object device, object size=None):
        cdef int end
        cdef int page_start
        cdef int page_end
        cdef int page
        cdef tuple entry
        cdef object bucket
        if size is None:
            size = getattr(device, "size", None)
        if size is None:
            raise ValueError("hay que indicar size o usar un device con atributo size")
        start &= 0xFFFF
        end = (start + int(size) - 1) & 0xFFFF
        if end < start:
            raise ValueError("no se soportan rangos que crucen 0xFFFF")
        entry = (start, end, device)
        self._mapped.append(entry)
        page_start = start >> PAGE_SHIFT
        page_end = end >> PAGE_SHIFT
        for page in range(page_start, page_end + 1):
            bucket = self._page_entries[page]
            if bucket is None:
                bucket = []
                self._page_entries[page] = bucket
            bucket.append(entry)

    cdef inline object _find_device(self, int addr):
        cdef Py_ssize_t i
        cdef tuple entry
        cdef object bucket
        cdef int start
        cdef int end
        addr &= 0xFFFF
        bucket = self._page_entries[addr >> PAGE_SHIFT]
        if bucket is None:
            return None
        for i in range(len(bucket) - 1, -1, -1):
            entry = bucket[i]
            start = <int>entry[0]
            end = <int>entry[1]
            if start <= addr <= end:
                return entry
        return None

    cpdef int read8(self, int addr):
        cdef object resolved = self._find_device(addr)
        cdef int start
        cdef object device
        if resolved is None:
            return 0xFF
        start = <int>resolved[0]
        device = resolved[2]
        return device.read((addr - start) & 0xFFFF) & 0xFF

    cpdef void write8(self, int addr, int value):
        cdef object resolved = self._find_device(addr)
        cdef int start
        cdef object device
        if resolved is None:
            return
        start = <int>resolved[0]
        device = resolved[2]
        device.write((addr - start) & 0xFFFF, value & 0xFF)

    cpdef int read16(self, int addr):
        cdef int lo = self.read8(addr)
        cdef int hi = self.read8((addr + 1) & 0xFFFF)
        return lo | (hi << 8)

    cpdef void request_irq(self):
        self.irq_pending = True

    cpdef void clear_irq(self):
        self.irq_pending = False

    cpdef void request_nmi(self):
        self.nmi_pending = True

    cpdef bint pull_nmi(self):
        cdef bint pending = self.nmi_pending
        self.nmi_pending = False
        return pending
