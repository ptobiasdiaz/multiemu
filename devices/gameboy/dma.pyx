# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""OAM DMA helper for the Game Boy."""


cdef class GameBoyDMAController:
    """Tracks and executes OAM DMA transfers."""

    DMA_CYCLES_PER_BYTE = 4
    DMA_TOTAL_BYTES = 0xA0

    cdef public object bus
    cdef public bint active
    cdef public int source_base
    cdef public int index
    cdef public int cycle_accum

    def __init__(self, bus):
        self.bus = bus
        self.reset()

    cpdef void reset(self):
        self.active = False
        self.source_base = 0
        self.index = 0
        self.cycle_accum = 0
        self.bus.set_dma_oam_blocked(False)

    cpdef void start(self, int value):
        self.active = True
        self.source_base = (value & 0xFF) << 8
        self.index = 0
        self.cycle_accum = 0
        self.bus.set_dma_oam_blocked(True)

    cpdef void run_cycles(self, int cycles):
        cdef object bus
        cdef bytearray oam
        cdef int source_base
        cdef int index
        cdef int cycle_accum

        if not self.active or cycles <= 0:
            return

        bus = self.bus
        oam = bus.oam
        source_base = self.source_base
        index = self.index
        cycle_accum = self.cycle_accum + cycles

        while cycle_accum >= self.DMA_CYCLES_PER_BYTE and index < self.DMA_TOTAL_BYTES:
            cycle_accum -= self.DMA_CYCLES_PER_BYTE
            oam[index] = bus.read8((source_base + index) & 0xFFFF)
            index += 1

        self.index = index
        self.cycle_accum = cycle_accum

        if index >= self.DMA_TOTAL_BYTES:
            self.active = False
            self.cycle_accum = 0
            bus.set_dma_oam_blocked(False)
