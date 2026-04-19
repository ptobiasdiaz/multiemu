"""Game Boy Color machine scaffold.

Current scope:
- visible machine id and registry entry for CGB software/users
- same hardware path as DMG for now until CGB-only subsystems land

Deferred:
- CGB palettes and colorized PPU path
- WRAM banking
- double-speed mode
- CGB-specific DMA/details
"""

from __future__ import annotations

from .base import GameBoyMachineBase


class CGB(GameBoyMachineBase):
    """Nintendo Game Boy Color scaffold on top of the current DMG path."""

    def __init__(self, rom_data: bytes):
        super().__init__(rom_data)
        self.bus.cgb_mode = True
        self.ppu.cgb_mode = True
        self.vbk = 0x00
        self.svbk = 0x01
        self.bus.key1_state = 0x00
        self.bus.vram_bank_select = self.vbk
        self.bus.wram_bank_select = self.svbk
        self.bus.set_io_handler(0xFF4D, reader=self.read_key1, writer=self.write_key1)
        self.bus.set_io_handler(0xFF4F, reader=self.read_vbk, writer=self.write_vbk)
        self.bus.set_io_handler(0xFF51, reader=self.dma.read_hdma1, writer=self.dma.write_hdma1)
        self.bus.set_io_handler(0xFF52, reader=self.dma.read_hdma2, writer=self.dma.write_hdma2)
        self.bus.set_io_handler(0xFF53, reader=self.dma.read_hdma3, writer=self.dma.write_hdma3)
        self.bus.set_io_handler(0xFF54, reader=self.dma.read_hdma4, writer=self.dma.write_hdma4)
        self.bus.set_io_handler(0xFF55, reader=self.dma.read_hdma5, writer=self.dma.write_hdma5)
        self.bus.set_io_handler(0xFF68, reader=self.ppu.read_bgpi, writer=self.ppu.write_bgpi)
        self.bus.set_io_handler(0xFF69, reader=self.ppu.read_bgpd, writer=self.ppu.write_bgpd)
        self.bus.set_io_handler(0xFF6A, reader=self.ppu.read_obpi, writer=self.ppu.write_obpi)
        self.bus.set_io_handler(0xFF6B, reader=self.ppu.read_obpd, writer=self.ppu.write_obpd)
        self.bus.set_io_handler(0xFF70, reader=self.read_svbk, writer=self.write_svbk)
        self._device_real_clock = 0

    def reset(self):
        super().reset()
        # Expose a CGB-like post-BIOS CPU state instead of the DMG defaults
        # used by the shared LR35902 reset path.
        self.cpu.A = 0x11
        self.cpu.F = 0x80
        self.cpu.B = 0x00
        self.cpu.C = 0x00
        self.cpu.D = 0xFF
        self.cpu.E = 0x56
        self.cpu.H = 0x00
        self.cpu.L = 0x0D
        self.cpu.SP = 0xFFFE
        self.cpu.PC = 0x0100
        self.vbk = 0x00
        self.svbk = 0x01
        self.bus.cgb_mode = True
        self.ppu.cgb_mode = True
        self.bus.key1_state = 0x00
        self.bus.vram_bank_select = self.vbk
        self.bus.wram_bank_select = self.svbk
        self._device_real_clock = 0

    def _cpu_speed_multiplier(self) -> int:
        return 2 if (self.bus.key1_state & 0x80) else 1

    def _begin_frame(self) -> None:
        super()._begin_frame()
        self._device_real_clock = 0

    def run_frame(self) -> int:
        speed = self._cpu_speed_multiplier()
        self._frame_runner.run_scaled(
            self,
            self.cpu.step,
            self.TSTATES_PER_FRAME * speed,
            speed,
            self._begin_frame,
            self._finish_frame,
            (self.timer.run_cycles,),
            (self.apu.run_cycles, self.dma.run_cycles),
            (self.ppu.run_until,),
            "_device_clock",
            "_device_real_clock",
        )
        return self.tstates

    def read_key1(self) -> int:
        return 0x7E | (self.bus.key1_state & 0x81)

    def write_key1(self, value: int) -> None:
        self.bus.key1_state = (self.bus.key1_state & 0x80) | (value & 0x01)

    def read_vbk(self) -> int:
        return 0xFE | (self.vbk & 0x01)

    def write_vbk(self, value: int) -> None:
        self.vbk = value & 0x01
        self.bus.vram_bank_select = self.vbk

    def read_svbk(self) -> int:
        return 0xF8 | (self.svbk & 0x07)

    def write_svbk(self, value: int) -> None:
        bank = value & 0x07
        self.svbk = bank if bank != 0 else 1
        self.bus.wram_bank_select = self.svbk

    def read_state(self) -> dict:
        state = super().read_state()
        state |= {
            "vbk": self.vbk,
            "svbk": self.svbk,
            "device_real_clock": self._device_real_clock,
        }
        return state

    def write_state(self, state: dict) -> None:
        super().write_state(state)
        if "vbk" in state:
            self.vbk = int(state["vbk"]) & 0x01
        if "svbk" in state:
            bank = int(state["svbk"]) & 0x07
            self.svbk = bank if bank != 0 else 1
        if "device_real_clock" in state:
            self._device_real_clock = int(state["device_real_clock"])
        self.bus.cgb_mode = True
        self.ppu.cgb_mode = True
        self.bus.vram_bank_select = self.vbk
        self.bus.wram_bank_select = self.svbk
