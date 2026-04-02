# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""OAM DMA helper for the Game Boy."""

from multiemu.state_codec import read_state_fields, write_state_fields


cdef class GameBoyDMAController:
    """Tracks and executes OAM DMA transfers."""

    DMA_CYCLES_PER_BYTE = 4
    DMA_TOTAL_BYTES = 0xA0

    cdef public object bus
    cdef public object ppu
    cdef public bint active
    cdef public int source_base
    cdef public int index
    cdef public int cycle_accum
    cdef public int hdma_source, hdma_dest, hdma_blocks_remaining
    cdef public bint hdma_active
    cdef public int hdma_last_line

    def __init__(self, bus):
        self.bus = bus
        self.ppu = None
        self.reset()

    cpdef void reset(self):
        self.active = False
        self.source_base = 0
        self.index = 0
        self.cycle_accum = 0
        self.hdma_source = 0
        self.hdma_dest = 0
        self.hdma_blocks_remaining = 0
        self.hdma_active = False
        self.hdma_last_line = -1
        self.bus.set_dma_oam_blocked(False)

    cpdef void set_ppu(self, object ppu):
        self.ppu = ppu

    cpdef void start(self, int value):
        self.active = True
        self.source_base = (value & 0xFF) << 8
        self.index = 0
        self.cycle_accum = 0
        self.bus.set_dma_oam_blocked(True)

    cpdef int read_hdma1(self):
        return (self.hdma_source >> 8) & 0xFF

    cpdef void write_hdma1(self, int value):
        self.hdma_source = ((value & 0xFF) << 8) | (self.hdma_source & 0x00F0)

    cpdef int read_hdma2(self):
        return self.hdma_source & 0xF0

    cpdef void write_hdma2(self, int value):
        self.hdma_source = (self.hdma_source & 0xFF00) | (value & 0xF0)

    cpdef int read_hdma3(self):
        return 0x80 | ((self.hdma_dest >> 8) & 0x1F)

    cpdef void write_hdma3(self, int value):
        self.hdma_dest = ((value & 0x1F) << 8) | (self.hdma_dest & 0x00F0)

    cpdef int read_hdma4(self):
        return self.hdma_dest & 0xF0

    cpdef void write_hdma4(self, int value):
        self.hdma_dest = (self.hdma_dest & 0x1F00) | (value & 0xF0)

    cpdef int read_hdma5(self):
        if self.hdma_active:
            return (self.hdma_blocks_remaining - 1) & 0x7F
        return 0xFF

    cpdef void write_hdma5(self, int value):
        cdef int blocks = (value & 0x7F) + 1
        if self.hdma_active and (value & 0x80) == 0:
            self.hdma_active = False
            self.hdma_last_line = -1
            return
        self.hdma_blocks_remaining = blocks
        if value & 0x80:
            self.hdma_active = True
            self.hdma_last_line = -1
            return
        self.hdma_active = False
        while self.hdma_blocks_remaining > 0:
            self._transfer_hdma_block()

    cpdef void run_cycles(self, int cycles):
        cdef object bus
        cdef bytearray oam
        cdef int source_base
        cdef int index
        cdef int cycle_accum

        if self.active and cycles > 0:
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

        self._run_hdma()

    cdef void _run_hdma(self):
        cdef int mode
        cdef int ly
        if not self.hdma_active or self.hdma_blocks_remaining <= 0 or self.ppu is None:
            return
        mode = self.ppu.read_stat() & 0x03
        ly = self.ppu.read_ly()
        if mode == 0 and ly < 144 and ly != self.hdma_last_line:
            self._transfer_hdma_block()
            self.hdma_last_line = ly

    cdef void _transfer_hdma_block(self):
        cdef int i
        cdef int source
        cdef int dest
        cdef int dest_base
        cdef bytearray vram
        if self.hdma_blocks_remaining <= 0:
            self.hdma_active = False
            return
        source = self.hdma_source & 0xFFF0
        dest = self.hdma_dest & 0x1FF0
        dest_base = dest
        if self.bus.cgb_mode:
            dest_base += (self.bus.vram_bank_select & 0x01) * 0x2000
        vram = self.bus.vram
        for i in range(0x10):
            vram[(dest_base + i) & 0x3FFF] = self.bus.read8((source + i) & 0xFFFF)
        self.hdma_source = (source + 0x10) & 0xFFF0
        self.hdma_dest = (dest + 0x10) & 0x1FF0
        self.hdma_blocks_remaining -= 1
        if self.hdma_blocks_remaining <= 0:
            self.hdma_active = False
            self.hdma_last_line = -1

    def read_state(self) -> dict:
        return read_state_fields(
            self,
            scalar_fields=(
                "active",
                "source_base",
                "index",
                "cycle_accum",
                "hdma_source",
                "hdma_dest",
                "hdma_blocks_remaining",
                "hdma_active",
                "hdma_last_line",
            ),
            meta={"type": "GameBoyDMAController"},
        )

    def write_state(self, state: dict) -> None:
        write_state_fields(
            self,
            state,
            scalar_fields=(
                "active",
                "source_base",
                "index",
                "cycle_accum",
                "hdma_source",
                "hdma_dest",
                "hdma_blocks_remaining",
                "hdma_active",
                "hdma_last_line",
            ),
        )
