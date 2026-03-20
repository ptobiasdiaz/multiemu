"""OAM DMA helper for the Game Boy."""

from __future__ import annotations


class GameBoyDMAController:
    """Tracks and executes OAM DMA transfers."""

    DMA_CYCLES_PER_BYTE = 4
    DMA_TOTAL_BYTES = 0xA0

    def __init__(self, bus):
        self.bus = bus
        self.reset()

    def reset(self):
        self.active = False
        self.source_base = 0
        self.index = 0
        self.cycle_accum = 0
        self.bus.set_dma_oam_blocked(False)

    def start(self, value: int):
        self.active = True
        self.source_base = (value & 0xFF) << 8
        self.index = 0
        self.cycle_accum = 0
        self.bus.set_dma_oam_blocked(True)

    def run_cycles(self, cycles: int):
        if not self.active or cycles <= 0:
            return

        self.cycle_accum += cycles
        while self.cycle_accum >= self.DMA_CYCLES_PER_BYTE and self.index < self.DMA_TOTAL_BYTES:
            self.cycle_accum -= self.DMA_CYCLES_PER_BYTE
            self.bus.oam[self.index] = self.bus.read8((self.source_base + self.index) & 0xFFFF)
            self.index += 1

        if self.index >= self.DMA_TOTAL_BYTES:
            self.active = False
            self.cycle_accum = 0
            self.bus.set_dma_oam_blocked(False)
