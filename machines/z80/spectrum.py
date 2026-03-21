from __future__ import annotations

from cpu.z80 import RAMBlock, ROMBlock, PythonPortHandler
from devices import SpectrumCassetteTape
from devices.ula import Spectrum48KULA
from frontend.input_events import InputEvent
from machines.frame_runner import SteppedFrameRunner
from machines.z80.base import Z80MachineBase
from video import get_display_profile


class SpectrumBase(Z80MachineBase):
    """Common ZX Spectrum machine behavior shared across memory variants."""

    ROM_SIZE = 0x4000
    RAM_SIZE = 0x4000
    RAM_BASE = 0x4000
    TSTATES_PER_FRAME = 69888

    def __init__(
        self,
        rom_data: bytes | None = None,
        *,
        tape_data: bytes | None = None,
        display_profile: str = "default",
    ):
        super().__init__()
        self.display_profile_name = display_profile
        self.display_profile = get_display_profile(display_profile)

        self.rom = ROMBlock(self.ROM_SIZE)
        self.ram = RAMBlock(self.RAM_SIZE)

        if rom_data is not None:
            self.rom.load_bytes(rom_data)

        self.bus.map_block(0x0000, self.rom)
        # Each model maps only the RAM it physically has. Unmapped pages fall
        # back to the bus default behavior (0xFF on reads, ignored writes).
        self.bus.map_block(self.RAM_BASE, self.ram)

        self.border_color = 0
        self.last_out_fe = 0

        self.ula = Spectrum48KULA(self)
        self.cassette = SpectrumCassetteTape.from_tzx_bytes(tape_data) if tape_data is not None else None
        self._tape_tstates = 0
        self.frame_width = self.ula.frame_width
        self.frame_height = self.ula.frame_height
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()
        self.audio_ring = self.audio_ring.__class__(self.ula.beeper.sample_rate // 2)

        self.keyboard_rows = [0x1F] * 8

        self.bus.set_port_handler(
            0xFE,
            PythonPortHandler(self._port_read_fe, self._port_write_fe),
        )
        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)

    @property
    def framebuffer_rgb24(self):
        if hasattr(self, "ula"):
            return self.ula.framebuffer_rgb24
        return getattr(self, "_framebuffer_rgb24", None)

    @framebuffer_rgb24.setter
    def framebuffer_rgb24(self, value):
        if hasattr(self, "ula"):
            self.ula.framebuffer_rgb24 = value
            return
        self._framebuffer_rgb24 = value

    @property
    def ram_top(self) -> int:
        return self.RAM_BASE + self.RAM_SIZE

    def _port_read_fe(self, port: int) -> int:
        result = 0xFF
        high = (port >> 8) & 0xFF

        for row in range(8):
            if (high & (1 << row)) == 0:
                result &= self.keyboard_rows[row]

        if self.cassette is not None:
            # EAR input is observed on bit 6. Toggling this bit is enough for
            # the ROM loader to see tape edges.
            if self.cassette.level:
                result &= ~0x40
            else:
                result |= 0x40

        return result & 0xFF

    def _port_write_fe(self, port: int, value: int) -> None:
        value &= 0xFF
        self.last_out_fe = value
        self.border_color = value & 0x07
        self.ula.beeper.set_level_from_port_value(value, self.frame_tstates)

    def reset(self):
        super().reset()
        self.border_color = 0
        self.last_out_fe = 0
        self.keyboard_rows = [0x1F] * 8

        self.ula.reset()
        if self.cassette is not None:
            self.cassette.reset()
        self._tape_tstates = 0
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self._tape_tstates = 0
        self.ula.beeper.begin_frame()

    def _finish_frame(self) -> None:
        self.ula.end_frame()
        self.framebuffer_rgb24 = self.ula.framebuffer_rgb24
        self.audio_samples = self.ula.get_frame_samples()
        self.audio_ring.write(self.audio_samples)
        self.frame_counter += 1

    def run_frame(self) -> int:
        self._frame_runner.run(
            self,
            self.cpu.step,
            self._run_devices_until,
            self._begin_frame,
            self._finish_frame,
        )
        return self.tstates

    def _run_devices_until(self, tstates: int):
        self.ula.run_until(tstates)
        if self.cassette is not None:
            self.cassette.run_cycles(max(0, tstates - self._tape_tstates))
            self._tape_tstates = tstates

    def toggle_tape_play_pause(self) -> bool:
        if self.cassette is None:
            return False
        return self.cassette.toggle_play_pause()

    def load_rom(self, data: bytes):
        self.rom.load_bytes(data)

    def _is_ram_address(self, addr: int) -> bool:
        return self.RAM_BASE <= addr < self.ram_top

    def poke(self, addr: int, value: int):
        if self._is_ram_address(addr):
            self.ram.load(addr - self.RAM_BASE, bytes([value & 0xFF]))
            return
        raise ValueError(
            f"solo se puede escribir en RAM 0x{self.RAM_BASE:04X}-0x{self.ram_top - 1:04X}"
        )

    def peek(self, addr: int) -> int:
        if 0x0000 <= addr < self.ROM_SIZE:
            return self.rom.peek(addr)
        if self._is_ram_address(addr):
            return self.ram.peek(addr - self.RAM_BASE)
        if 0 <= addr <= 0xFFFF:
            # Smaller models expose holes above installed RAM. Returning 0xFF
            # keeps the high-level helpers aligned with the underlying bus.
            return 0xFF
        raise ValueError("dirección fuera de rango")

    def load_ram(self, addr: int, data: bytes):
        if not self._is_ram_address(addr) or addr + len(data) > self.ram_top:
            raise ValueError(
                f"el rango debe caer dentro de la RAM del Spectrum "
                f"0x{self.RAM_BASE:04X}-0x{self.ram_top - 1:04X}"
            )
        self.ram.load(addr - self.RAM_BASE, data)

    def clear_input_state(self):
        self.keyboard_rows = [0x1F] * 8

    def _press_key(self, row: int, bit: int):
        self.keyboard_rows[row] &= ~(1 << bit)
        self.keyboard_rows[row] &= 0x1F

    def _release_key(self, row: int, bit: int):
        self.keyboard_rows[row] |= (1 << bit)
        self.keyboard_rows[row] &= 0x1F

    def handle_input_event(self, event):
        if not isinstance(event, InputEvent):
            raise TypeError(f"evento de input inválido: {type(event)!r}")

        if event.kind != "key_matrix":
            raise ValueError(f"tipo de input no soportado: {event.kind}")

        if event.active:
            self._press_key(event.control_a, event.control_b)
        else:
            self._release_key(event.control_a, event.control_b)

    def render_frame(self):
        self.framebuffer_rgb24 = self.ula.render_frame()
        return self.framebuffer_rgb24

    def get_audio_samples(self):
        return self.audio_samples

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["border_color"] = self.border_color
        snap["last_out_fe"] = self.last_out_fe
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        snap["ram_base"] = self.RAM_BASE
        snap["ram_size"] = self.RAM_SIZE
        return snap


class Spectrum16K(SpectrumBase):
    """ZX Spectrum 16K with RAM only in 0x4000-0x7FFF."""

    RAM_SIZE = 0x4000


class Spectrum48K(SpectrumBase):
    """ZX Spectrum 48K with the full 0x4000-0xFFFF RAM space mapped."""

    RAM_SIZE = 0xC000
