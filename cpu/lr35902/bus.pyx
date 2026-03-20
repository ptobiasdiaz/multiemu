# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""Bus scaffolding for the LR35902 CPU used by the original Game Boy."""

from __future__ import annotations


cdef class LR35902Bus:
    """Very small Game Boy address-space implementation."""

    WRAM_BASE = 0xC000
    WRAM_SIZE = 0x2000
    VRAM_BASE = 0x8000
    VRAM_SIZE = 0x2000
    ERAM_BASE = 0xA000
    ERAM_SIZE = 0x2000
    OAM_BASE = 0xFE00
    OAM_SIZE = 0x00A0
    HRAM_BASE = 0xFF80
    HRAM_SIZE = 0x007F

    cdef public object cartridge
    cdef public bytearray vram, eram, wram, oam, hram
    cdef public object io_readers, io_writers
    cdef public object interrupts, dma_controller
    cdef public int interrupt_enable
    cdef public bint vram_accessible, oam_accessible
    cdef bint _ppu_oam_accessible, _dma_oam_accessible

    def __init__(self, cartridge=None):
        self.cartridge = cartridge
        self.vram = bytearray(self.VRAM_SIZE)
        self.eram = bytearray(self.ERAM_SIZE)
        self.wram = bytearray(self.WRAM_SIZE)
        self.oam = bytearray(self.OAM_SIZE)
        self.hram = bytearray(self.HRAM_SIZE)
        self.io_readers = {}
        self.io_writers = {}
        self.interrupts = None
        self.dma_controller = None
        self.interrupt_enable = 0x00
        self.vram_accessible = True
        self.oam_accessible = True
        self._ppu_oam_accessible = True
        self._dma_oam_accessible = True

    def reset(self) -> None:
        self.vram[:] = b"\x00" * self.VRAM_SIZE
        self.eram[:] = b"\x00" * self.ERAM_SIZE
        self.wram[:] = b"\x00" * self.WRAM_SIZE
        self.oam[:] = b"\x00" * self.OAM_SIZE
        self.hram[:] = b"\x00" * self.HRAM_SIZE
        self.interrupt_enable = 0x00
        if self.interrupts is not None:
            self.interrupts.interrupt_flags = 0x00
        self.vram_accessible = True
        self._ppu_oam_accessible = True
        self._dma_oam_accessible = True
        self.oam_accessible = True
        if self.cartridge is not None and getattr(self.cartridge, "mapper", None) is not None:
            self.cartridge.mapper.reset()

    def set_ppu_access(self, *, vram_accessible: bool, oam_accessible: bool) -> None:
        self.vram_accessible = bool(vram_accessible)
        self._ppu_oam_accessible = bool(oam_accessible)
        self.oam_accessible = self._ppu_oam_accessible and self._dma_oam_accessible

    def set_dma_oam_blocked(self, blocked: bool) -> None:
        self._dma_oam_accessible = not bool(blocked)
        self.oam_accessible = self._ppu_oam_accessible and self._dma_oam_accessible

    def set_io_handler(self, addr: int, *, reader=None, writer=None) -> None:
        addr &= 0xFFFF
        if reader is not None:
            self.io_readers[addr] = reader
        if writer is not None:
            self.io_writers[addr] = writer

    def set_interrupt_controller(self, interrupts) -> None:
        self.interrupts = interrupts

    def set_dma_controller(self, dma_controller) -> None:
        self.dma_controller = dma_controller

    cpdef int read8(self, int addr):
        cdef object reader
        addr &= 0xFFFF

        if self.cartridge is not None and addr < 0x8000:
            return self.cartridge.read(addr)

        if self.VRAM_BASE <= addr < self.VRAM_BASE + self.VRAM_SIZE:
            if not self.vram_accessible:
                return 0xFF
            return self.vram[addr - self.VRAM_BASE]

        if self.ERAM_BASE <= addr < self.ERAM_BASE + self.ERAM_SIZE:
            if self.cartridge is not None:
                return self.cartridge.read(addr)
            return self.eram[addr - self.ERAM_BASE]

        if self.WRAM_BASE <= addr < self.WRAM_BASE + self.WRAM_SIZE:
            return self.wram[addr - self.WRAM_BASE]

        if 0xE000 <= addr < 0xFE00:
            return self.wram[addr - 0xE000]

        if self.OAM_BASE <= addr < self.OAM_BASE + self.OAM_SIZE:
            if not self.oam_accessible:
                return 0xFF
            return self.oam[addr - self.OAM_BASE]

        if addr == 0xFF0F:
            if self.interrupts is not None:
                return self.interrupts.interrupt_flags | 0xE0
            return 0xFF

        if 0xFF00 <= addr <= 0xFF7F:
            reader = self.io_readers.get(addr)
            if reader is not None:
                return reader() & 0xFF
            return 0xFF

        if self.HRAM_BASE <= addr < self.HRAM_BASE + self.HRAM_SIZE:
            return self.hram[addr - self.HRAM_BASE]

        if addr == 0xFFFF:
            return self.interrupt_enable

        return 0xFF

    cpdef void write8(self, int addr, int value):
        cdef object writer
        addr &= 0xFFFF
        value &= 0xFF

        if self.cartridge is not None and addr < 0x8000:
            self.cartridge.write(addr, value)
            return

        if self.VRAM_BASE <= addr < self.VRAM_BASE + self.VRAM_SIZE:
            if not self.vram_accessible:
                return
            self.vram[addr - self.VRAM_BASE] = value
            return

        if self.ERAM_BASE <= addr < self.ERAM_BASE + self.ERAM_SIZE:
            if self.cartridge is not None:
                self.cartridge.write(addr, value)
                return
            self.eram[addr - self.ERAM_BASE] = value
            return

        if self.WRAM_BASE <= addr < self.WRAM_BASE + self.WRAM_SIZE:
            self.wram[addr - self.WRAM_BASE] = value
            return

        if 0xE000 <= addr < 0xFE00:
            self.wram[addr - 0xE000] = value
            return

        if self.OAM_BASE <= addr < self.OAM_BASE + self.OAM_SIZE:
            if not self.oam_accessible:
                return
            self.oam[addr - self.OAM_BASE] = value
            return

        if addr == 0xFF46:
            if self.dma_controller is not None:
                self.dma_controller.start(value)
            return

        if addr == 0xFF0F:
            if self.interrupts is not None:
                self.interrupts.interrupt_flags = value & 0x1F
            return

        if 0xFF00 <= addr <= 0xFF7F:
            writer = self.io_writers.get(addr)
            if writer is not None:
                writer(value)
            return

        if self.HRAM_BASE <= addr < self.HRAM_BASE + self.HRAM_SIZE:
            self.hram[addr - self.HRAM_BASE] = value
            return

        if addr == 0xFFFF:
            self.interrupt_enable = value
            return

    def peek(self, addr: int) -> int:
        return self.read8(addr)

    def poke(self, addr: int, value: int) -> None:
        self.write8(addr, value)

    def read16(self, addr: int) -> int:
        cdef int lo = self.read8(addr)
        cdef int hi = self.read8((addr + 1) & 0xFFFF)
        return lo | (hi << 8)

    def write16(self, addr: int, value: int) -> None:
        self.write8(addr, value & 0xFF)
        self.write8((addr + 1) & 0xFFFF, (value >> 8) & 0xFF)
