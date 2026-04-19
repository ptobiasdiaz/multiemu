from __future__ import annotations

from array import array

from chipsets.m6530 import M6530
from cpu.m6502 import RAMBlock, ROMBlock
from frontend.input_events import InputEvent
from machines.frame_runner import SteppedFrameRunner
from machines.m6502.base import M6502MachineBase


class KIM1(M6502MachineBase):
    """Very small KIM-1 scaffold to validate the new 6502 architecture."""

    RAM_SIZE = 0x0400
    DISPLAY_ADDR = 0x1740
    MONITOR_RAM_BASE = 0x17C0
    MONITOR_RAM_SIZE = 0x40
    NMIV_ADDR = 0x17FA
    RSTV_ADDR = 0x17FC
    IRQV_ADDR = 0x17FE
    STOP_VECTOR = 0x1C00
    RESET_HANDLER = 0x1C22
    # KIM-1 monitor ROM layout from the original dumps/assembly:
    # - 6530-003 lives at 0x1800-0x1BFF
    # - 6530-002 lives at 0x1C00-0x1FFF
    # The reset vectors visible at 0xFFFA-0xFFFF mirror the 6530-002 image.
    UPPER_ROM_BASE = 0x1800
    LOWER_ROM_BASE = 0x1C00
    UPPER_ROM_MIRROR_BASE = 0xF800
    LOWER_ROM_MIRROR_BASE = 0xFC00
    ROM_SIZE = 0x0400
    TSTATES_PER_FRAME = 20_000

    def __init__(
        self,
        lower_rom_data: bytes | None = None,
        upper_rom_data: bytes | None = None,
        *,
        monitor_rom_data: bytes | None = None,
    ):
        super().__init__(audio_sample_rate=44100)

        self.machine_id = "kim1"
        self.display_name = "MOS KIM-1 (early scaffold)"
        self.input_keymap_name = None

        self.ram = RAMBlock(self.RAM_SIZE)
        self.monitor_ram = RAMBlock(self.MONITOR_RAM_SIZE)
        self.riot = M6530()
        self.display = self.riot
        lower_rom_data, upper_rom_data = self._build_monitor_roms(
            lower_rom_data=lower_rom_data,
            upper_rom_data=upper_rom_data,
            monitor_rom_data=monitor_rom_data,
        )
        self.lower_rom = ROMBlock(self.ROM_SIZE)
        self.lower_rom.load_bytes(lower_rom_data)
        self.upper_rom = ROMBlock(self.ROM_SIZE)
        self.upper_rom.load_bytes(upper_rom_data)

        self.bus.map_block(0x0000, self.ram, size=self.RAM_SIZE)
        self.bus.map_block(self.MONITOR_RAM_BASE, self.monitor_ram, size=self.MONITOR_RAM_SIZE)
        self.bus.map_block(self.DISPLAY_ADDR, self.riot, size=self.riot.size)
        self.bus.map_block(self.LOWER_ROM_BASE, self.lower_rom, size=self.ROM_SIZE)
        self.bus.map_block(self.UPPER_ROM_BASE, self.upper_rom, size=self.ROM_SIZE)
        self.bus.map_block(self.LOWER_ROM_MIRROR_BASE, self.lower_rom, size=self.ROM_SIZE)
        self.bus.map_block(self.UPPER_ROM_MIRROR_BASE, self.upper_rom, size=self.ROM_SIZE)

        self.frame_width = 192
        self.frame_height = 64
        self.framebuffer_rgb24 = self._render_panel()
        self.audio_samples = array("h")
        self.input_keymap_name = "kim1"
        self._frame_runner = SteppedFrameRunner(self.TSTATES_PER_FRAME)
        self._riot_clock = 0

        self.reset()

    def _make_default_monitor_rom(self) -> bytes:
        rom = bytearray([0xEA] * (self.ROM_SIZE * 2))
        reset_vector = self.LOWER_ROM_BASE
        rom[self.ROM_SIZE + 0x0000] = 0x4C  # JMP 1C00
        rom[self.ROM_SIZE + 0x0001] = reset_vector & 0xFF
        rom[self.ROM_SIZE + 0x0002] = (reset_vector >> 8) & 0xFF
        rom[0x03FC] = reset_vector & 0xFF
        rom[0x03FD] = (reset_vector >> 8) & 0xFF
        return bytes(rom)

    def _build_monitor_roms(
        self,
        *,
        lower_rom_data: bytes | None,
        upper_rom_data: bytes | None,
        monitor_rom_data: bytes | None,
    ) -> tuple[bytes, bytes]:
        if monitor_rom_data is not None:
            if len(monitor_rom_data) != self.ROM_SIZE * 2:
                raise ValueError(f"la ROM combinada de KIM-1 debe medir {self.ROM_SIZE * 2} bytes")
            return monitor_rom_data[:self.ROM_SIZE], monitor_rom_data[self.ROM_SIZE:]

        if lower_rom_data is not None and upper_rom_data is None and len(lower_rom_data) == self.ROM_SIZE * 2:
            return lower_rom_data[:self.ROM_SIZE], lower_rom_data[self.ROM_SIZE:]

        if lower_rom_data is None and upper_rom_data is None:
            default = self._make_default_monitor_rom()
            return default[:self.ROM_SIZE], default[self.ROM_SIZE:]

        if lower_rom_data is None or upper_rom_data is None:
            raise ValueError("KIM-1 necesita las ROMs lower y upper juntas")

        if len(lower_rom_data) != self.ROM_SIZE:
            raise ValueError(f"la ROM lower de KIM-1 debe medir {self.ROM_SIZE} bytes")
        if len(upper_rom_data) != self.ROM_SIZE:
            raise ValueError(f"la ROM upper de KIM-1 debe medir {self.ROM_SIZE} bytes")

        return lower_rom_data, upper_rom_data

    def reset(self):
        self.ram = getattr(self, "ram", None) or RAMBlock(self.RAM_SIZE)
        self.monitor_ram = getattr(self, "monitor_ram", None) or RAMBlock(self.MONITOR_RAM_SIZE)
        super().reset()
        self.bus.clear_irq()
        self.bus.nmi_pending = False
        self.ram.load(0, bytes(self.RAM_SIZE))
        self.monitor_ram.load(0, bytes(self.MONITOR_RAM_SIZE))
        self._init_monitor_workspace()
        self.riot.reset()
        self.riot.set_keyboard_mode(True)
        self.riot.set_serial_input(True)
        self._riot_clock = 0
        self.framebuffer_rgb24 = self._render_panel()
        self.audio_samples = array("h")

    def _init_monitor_workspace(self) -> None:
        # The KIM-1 monitor expects RAM vectors in the 6530 RAM area.
        self.bus.write8(self.NMIV_ADDR, self.STOP_VECTOR & 0xFF)
        self.bus.write8(self.NMIV_ADDR + 1, (self.STOP_VECTOR >> 8) & 0xFF)
        self.bus.write8(self.RSTV_ADDR, self.RESET_HANDLER & 0xFF)
        self.bus.write8(self.RSTV_ADDR + 1, (self.RESET_HANDLER >> 8) & 0xFF)
        self.bus.write8(self.IRQV_ADDR, self.STOP_VECTOR & 0xFF)
        self.bus.write8(self.IRQV_ADDR + 1, (self.STOP_VECTOR >> 8) & 0xFF)

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self._riot_clock = 0

    def _finish_frame(self) -> None:
        self.framebuffer_rgb24 = self._render_panel()
        self.audio_samples = array("h")
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

    def render_frame(self):
        self.framebuffer_rgb24 = self._render_panel()
        return self.framebuffer_rgb24

    def _run_devices_until(self, tstates: int):
        delta = tstates - self._riot_clock
        if delta > 0:
            self.riot.run_cycles(delta)
            self._riot_clock = tstates

    def clear_input_state(self):
        self.riot.set_keypad_matrix([0xFF, 0xFF, 0xFF])

    def set_tty_mode(self, enabled: bool) -> None:
        self.riot.set_keyboard_mode(not enabled)

    def queue_tty_input(self, data: bytes, *, calibration: bool = False) -> None:
        self.riot.queue_tty_input(data, calibration=calibration)

    def drain_tty_output(self) -> bytes:
        return self.riot.drain_tty_output()

    def drain_tty_output_ascii(self) -> bytes:
        return self.riot.drain_tty_output_ascii()

    def read_state(self) -> dict:
        state = super().read_state()
        state |= {
            "riot_clock": self._riot_clock,
            "ram": self.ram.read_state(),
            "monitor_ram": self.monitor_ram.read_state(),
            "riot": self.riot.read_state(),
        }
        return state

    def write_state(self, state: dict) -> None:
        super().write_state(state)
        if "riot_clock" in state:
            self._riot_clock = int(state["riot_clock"])
        if "ram" in state:
            self.ram.write_state(state["ram"])
        if "monitor_ram" in state:
            self.monitor_ram.write_state(state["monitor_ram"])
        if "riot" in state:
            self.riot.write_state(state["riot"])
        self.framebuffer_rgb24 = self._render_panel()
        self.audio_samples = array("h")

    def handle_input_event(self, event):
        if not isinstance(event, InputEvent):
            raise TypeError(f"evento de input inválido: {type(event)!r}")
        if event.kind != "key_matrix":
            raise ValueError(f"tipo de input no soportado: {event.kind}")

        rows = list(self.riot.key_rows)
        row = max(0, min(2, event.control_a))
        bit = max(0, min(7, event.control_b))
        if event.active:
            rows[row] &= ~(1 << bit)
        else:
            rows[row] |= 1 << bit
        self.riot.set_keypad_matrix(rows)

    def _render_panel(self) -> bytes:
        width = self.frame_width
        height = self.frame_height
        out = bytearray(width * height * 3)
        bg = (18, 18, 16)
        on = (255, 70, 32)
        off = (60, 26, 18)

        for y in range(height):
            for x in range(width):
                idx = (y * width + x) * 3
                out[idx:idx + 3] = bytes(bg)

        digit_width = 24
        digit_height = 44
        x0 = 12
        y0 = 10
        for digit_index, pattern in enumerate(self.riot.display_digits):
            dx = x0 + digit_index * 30
            self._draw_digit(out, width, dx, y0, digit_width, digit_height, pattern, on, off)

        return bytes(out)

    def _draw_digit(
        self,
        out: bytearray,
        width: int,
        x: int,
        y: int,
        digit_width: int,
        digit_height: int,
        pattern: int,
        on: tuple[int, int, int],
        off: tuple[int, int, int],
    ) -> None:
        thickness = 4
        top = (x + thickness, y, digit_width - 2 * thickness, thickness)
        middle = (x + thickness, y + digit_height // 2 - thickness // 2, digit_width - 2 * thickness, thickness)
        bottom = (x + thickness, y + digit_height - thickness, digit_width - 2 * thickness, thickness)
        upper_left = (x, y + thickness, thickness, digit_height // 2 - thickness)
        upper_right = (x + digit_width - thickness, y + thickness, thickness, digit_height // 2 - thickness)
        lower_left = (x, y + digit_height // 2, thickness, digit_height // 2 - thickness)
        lower_right = (x + digit_width - thickness, y + digit_height // 2, thickness, digit_height // 2 - thickness)
        segments = (
            (0x01, top),
            (0x02, upper_right),
            (0x04, lower_right),
            (0x08, bottom),
            (0x10, lower_left),
            (0x20, upper_left),
            (0x40, middle),
        )
        for mask, rect in segments:
            self._fill_rect(out, width, rect, on if pattern & mask else off)

    def _fill_rect(
        self,
        out: bytearray,
        width: int,
        rect: tuple[int, int, int, int],
        color: tuple[int, int, int],
    ) -> None:
        x, y, w, h = rect
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                idx = (yy * width + xx) * 3
                out[idx:idx + 3] = bytes(color)

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        snap["display_digits"] = tuple(self.riot.display_digits)
        return snap

    def debug_devices(self) -> list[dict]:
        return super().debug_devices() + [
            self._debug_device("ram", self.ram, "memory", label="RAM"),
            self._debug_device("monitor_ram", self.monitor_ram, "memory", label="Monitor RAM"),
            self._debug_device("riot", self.riot, "chip", label="M6530 RIOT"),
            self._debug_device("display", self.display, "device", label="Display"),
            self._debug_device("lower_rom", self.lower_rom, "memory", label="Lower ROM"),
            self._debug_device("upper_rom", self.upper_rom, "memory", label="Upper ROM"),
        ]
