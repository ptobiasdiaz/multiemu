from __future__ import annotations


cdef class LR35902Bus:
    cdef public object cartridge
    cdef public bytearray vram, eram, wram, oam, hram
    cdef public object io_readers, io_writers
    cdef public object interrupts, dma_controller
    cdef public int interrupt_enable
    cdef public int vram_bank_select, wram_bank_select, key1_state
    cdef public bint cgb_mode
    cdef public bint vram_accessible, oam_accessible
    cdef bint _ppu_oam_accessible, _dma_oam_accessible

    cpdef void apply_ppu_access(self, bint vram_accessible, bint oam_accessible)
    cpdef int read8(self, int addr)
    cpdef void write8(self, int addr, int value)
