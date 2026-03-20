"""Base classes for Nintendo Game Boy machines."""

from __future__ import annotations

from frontend.input_events import InputEvent
from machines.base import BaseMachine
from machines.frame_runner import SteppedFrameRunner

from cpu.lr35902 import LR35902Bus, LR35902Core
from devices.gameboy import (
    GameBoyAPU,
    GameBoyCartridge,
    GameBoyDMAController,
    GameBoyInterruptController,
    GameBoyJoypad,
    GameBoyPPU,
    GameBoyTimer,
)


class GameBoyMachineBase(BaseMachine):
    """Shared DMG machine wiring.

    The machine remains in Python, while the future hot paths can move to
    dedicated accelerated devices later.
    """

    TSTATES_PER_FRAME = 70224
    def __init__(self, rom_data: bytes):
        self.cartridge = GameBoyCartridge(rom_data)
        self.bus = LR35902Bus(self.cartridge)
        self.cpu = LR35902Core(self.bus)
        super().__init__(bus=self.bus, cpu=self.cpu, audio_sample_rate=44100)

        self.interrupts = GameBoyInterruptController()
        self.joypad = GameBoyJoypad(self.interrupts)
        self.timer = GameBoyTimer(self.interrupts)
        self.ppu = GameBoyPPU(self.bus, self.interrupts)
        self.apu = GameBoyAPU(sample_rate=44100)
        self.dma = GameBoyDMAController(self.bus)
        self.bus.set_interrupt_controller(self.interrupts)
        self.bus.set_dma_controller(self.dma)

        self.frame_width = self.ppu.frame_width
        self.frame_height = self.ppu.frame_height
        self.framebuffer_rgb24 = self.ppu.framebuffer_rgb24
        self.audio_samples = self.apu.get_frame_samples()
        self.input_keymap_name = "gameboy"
        self.input_tap_hold_frames = 2
        self.input_quick_tap_max_frames = 1
        self._device_clock = 0
        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)
        self._install_io_handlers()

    def _write_dma(self, value: int) -> None:
        self.dma.start(value)

    def _run_dma(self, cycles: int) -> None:
        self.dma.run_cycles(cycles)

    def _install_io_handlers(self):
        self.bus.set_io_handler(0xFF00, reader=self.joypad.read_p1, writer=self.joypad.write_p1)
        self.bus.set_io_handler(0xFF04, reader=self.timer.read_div, writer=self.timer.write_div)
        self.bus.set_io_handler(0xFF05, reader=self.timer.read_tima, writer=self.timer.write_tima)
        self.bus.set_io_handler(0xFF06, reader=self.timer.read_tma, writer=self.timer.write_tma)
        self.bus.set_io_handler(0xFF07, reader=self.timer.read_tac, writer=self.timer.write_tac)
        self.bus.set_io_handler(0xFF40, reader=self.ppu.read_lcdc, writer=self.ppu.write_lcdc)
        self.bus.set_io_handler(0xFF41, reader=self.ppu.read_stat, writer=self.ppu.write_stat)
        self.bus.set_io_handler(0xFF42, reader=self.ppu.read_scy, writer=self.ppu.write_scy)
        self.bus.set_io_handler(0xFF43, reader=self.ppu.read_scx, writer=self.ppu.write_scx)
        self.bus.set_io_handler(0xFF44, reader=self.ppu.read_ly, writer=self.ppu.write_ly)
        self.bus.set_io_handler(0xFF45, reader=self.ppu.read_lyc, writer=self.ppu.write_lyc)
        self.bus.set_io_handler(0xFF47, reader=self.ppu.read_bgp, writer=self.ppu.write_bgp)
        self.bus.set_io_handler(0xFF48, reader=self.ppu.read_obp0, writer=self.ppu.write_obp0)
        self.bus.set_io_handler(0xFF49, reader=self.ppu.read_obp1, writer=self.ppu.write_obp1)
        self.bus.set_io_handler(0xFF4A, reader=self.ppu.read_wy, writer=self.ppu.write_wy)
        self.bus.set_io_handler(0xFF4B, reader=self.ppu.read_wx, writer=self.ppu.write_wx)
        self.bus.set_io_handler(0xFF10, reader=self.apu.read_nr10, writer=self.apu.write_nr10)
        self.bus.set_io_handler(0xFF11, reader=self.apu.read_nr11, writer=self.apu.write_nr11)
        self.bus.set_io_handler(0xFF12, reader=self.apu.read_nr12, writer=self.apu.write_nr12)
        self.bus.set_io_handler(0xFF13, reader=self.apu.read_nr13, writer=self.apu.write_nr13)
        self.bus.set_io_handler(0xFF14, reader=self.apu.read_nr14, writer=self.apu.write_nr14)
        self.bus.set_io_handler(0xFF16, reader=self.apu.read_nr21, writer=self.apu.write_nr21)
        self.bus.set_io_handler(0xFF17, reader=self.apu.read_nr22, writer=self.apu.write_nr22)
        self.bus.set_io_handler(0xFF18, reader=self.apu.read_nr23, writer=self.apu.write_nr23)
        self.bus.set_io_handler(0xFF19, reader=self.apu.read_nr24, writer=self.apu.write_nr24)
        self.bus.set_io_handler(0xFF1A, reader=self.apu.read_nr30, writer=self.apu.write_nr30)
        self.bus.set_io_handler(0xFF1B, reader=self.apu.read_nr31, writer=self.apu.write_nr31)
        self.bus.set_io_handler(0xFF1C, reader=self.apu.read_nr32, writer=self.apu.write_nr32)
        self.bus.set_io_handler(0xFF1D, reader=self.apu.read_nr33, writer=self.apu.write_nr33)
        self.bus.set_io_handler(0xFF1E, reader=self.apu.read_nr34, writer=self.apu.write_nr34)
        self.bus.set_io_handler(0xFF20, reader=self.apu.read_nr41, writer=self.apu.write_nr41)
        self.bus.set_io_handler(0xFF21, reader=self.apu.read_nr42, writer=self.apu.write_nr42)
        self.bus.set_io_handler(0xFF22, reader=self.apu.read_nr43, writer=self.apu.write_nr43)
        self.bus.set_io_handler(0xFF23, reader=self.apu.read_nr44, writer=self.apu.write_nr44)
        self.bus.set_io_handler(0xFF24, reader=self.apu.read_nr50, writer=self.apu.write_nr50)
        self.bus.set_io_handler(0xFF25, reader=self.apu.read_nr51, writer=self.apu.write_nr51)
        self.bus.set_io_handler(0xFF26, reader=self.apu.read_nr52, writer=self.apu.write_nr52)
        for wave_index in range(16):
            addr = 0xFF30 + wave_index
            self.bus.set_io_handler(
                addr,
                reader=lambda wave_index=wave_index: self.apu.read_wave_ram(wave_index),
                writer=lambda value, wave_index=wave_index: self.apu.write_wave_ram(wave_index, value),
            )
    def reset(self):
        super().reset()
        self.bus.reset()
        self.cpu.reset()
        self.interrupts.reset()
        self.joypad.reset()
        self.timer.reset()
        self.ppu.reset()
        self.apu.reset()
        self.dma.reset()
        self.framebuffer_rgb24 = self.ppu.framebuffer_rgb24
        self.audio_samples = self.apu.get_frame_samples()
        self._device_clock = 0
        self.bus.interrupt_enable = self.interrupts.interrupt_enable

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self._device_clock = 0
        self.ppu.begin_frame()
        self.apu.begin_frame()

    def _finish_frame(self) -> None:
        self.framebuffer_rgb24 = self.ppu.render_frame()
        self.audio_samples = self.apu.get_frame_samples()
        self.audio_ring.write(self.audio_samples)
        self.frame_counter += 1

    def run_frame(self) -> int:
        self._frame_runner.run(
            self,
            self.cpu.step,
            None,
            self._begin_frame,
            self._finish_frame,
            (self.timer.run_cycles, self.apu.run_cycles, self.dma.run_cycles),
            (self.ppu.run_until,),
            "_device_clock",
        )
        return self.tstates

    def render_frame(self):
        self.framebuffer_rgb24 = self.ppu.render_frame()
        return self.framebuffer_rgb24

    def _run_devices_until(self, tstates: int):
        delta = tstates - self._device_clock
        if delta <= 0:
            return

        self.timer.run_cycles(delta)
        self.ppu.run_until(tstates)
        self.apu.run_cycles(delta)
        self._run_dma(delta)
        self._device_clock = tstates

    def clear_input_state(self):
        self.joypad.clear_pressed_state()

    def handle_input_event(self, event):
        if not isinstance(event, InputEvent):
            raise TypeError(f"evento de input inválido: {type(event)!r}")
        if event.kind != "key_matrix":
            raise ValueError(f"tipo de input no soportado: {event.kind}")

        if event.active:
            self.joypad.press(event.control_a, event.control_b)
        else:
            self.joypad.release(event.control_a, event.control_b)

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        snap["cartridge_title"] = self.cartridge.title
        snap["cartridge_type"] = self.cartridge.cartridge_type_name
        snap["interrupt_enable"] = self.bus.interrupt_enable
        snap["interrupt_flags"] = self.interrupts.interrupt_flags
        return snap
