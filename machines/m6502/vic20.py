from __future__ import annotations

from array import array

from chipsets.via6522 import VIA6522
from chipsets.vic6560 import VIC6560

try:
    from chipsets.vic6560_render import draw_char_cell_scanline_rgb24 as _draw_char_cell_scanline_rgb24_render
    from chipsets.vic6560_render import draw_scanline_cells_rgb24 as _draw_scanline_cells_rgb24_render
    from chipsets.vic6560_render import draw_scanline_contexts_rgb24 as _draw_scanline_contexts_rgb24_render
    from chipsets.vic6560_render import build_scanline_contexts as _build_scanline_contexts_render
except ImportError:  # pragma: no cover - fallback when extension is unavailable
    _draw_char_cell_scanline_rgb24_render = None
    _draw_scanline_cells_rgb24_render = None
    _draw_scanline_contexts_rgb24_render = None
    _build_scanline_contexts_render = None

from cpu.m6502 import RAMBlock, ROMBlock
from frontend.input_events import (
    InputEvent,
    JOYSTICK_DOWN,
    JOYSTICK_FIRE,
    JOYSTICK_FIRE_2,
    JOYSTICK_LEFT,
    JOYSTICK_RIGHT,
    JOYSTICK_UP,
)
from machines.frame_runner import ScanlineFrameRunner
from machines.m6502.base import M6502MachineBase
from machines.m6502.vic20_io import ColorRAM as _ColorRAM
from machines.m6502.vic20_io import IoRam as _IoRam
from machines.m6502.vic20_io import OpenBus as _OpenBus


class VIC20(M6502MachineBase):
    """Early VIC-20 scaffold with basic memory map and ROM slots.

    This keeps the machine visible in the CLI and establishes the reusable
    6502-era home-computer wiring: RAM blocks, character ROM, BASIC/KERNAL ROMs
    and optional expansion blocks. Video, VIA and cassette stay for later
    passes.
    """

    LOW_RAM_SIZE = 0x0400
    MAIN_RAM_SIZE = 0x1000
    COLOR_RAM_SIZE = 0x0400
    CHAR_ROM_SIZE = 0x1000
    BASIC_ROM_SIZE = 0x2000
    KERNAL_ROM_SIZE = 0x2000
    EXPANSION_ROM_SIZE = 0x2000
    SCREEN_COLUMNS = 22
    SCREEN_ROWS = 23
    SCREEN_RAM_BASE = 0x1E00
    FRAME_BORDER_X = 16
    FRAME_BORDER_Y = 16
    DISPLAY_WIDTH = 200
    DISPLAY_HEIGHT = 234

    TSTATES_PER_FRAME = 18_432
    FRAMES_PER_SECOND = 60
    SCANLINES_PER_FRAME = 261
    VISIBLE_RASTER_START = 28
    PALETTE = (
        (0, 0, 0),
        (255, 255, 255),
        (240, 0, 0),
        (0, 240, 240),
        (96, 0, 96),
        (0, 160, 0),
        (0, 0, 240),
        (208, 208, 0),
        (192, 160, 0),
        (255, 160, 0),
        (240, 128, 128),
        (0, 255, 255),
        (255, 0, 255),
        (0, 255, 0),
        (0, 160, 255),
        (255, 255, 0),
    )
    PALETTE_BYTES = tuple(bytes(rgb) for rgb in PALETTE)

    def __init__(
        self,
        basic_rom_data: bytes,
        kernal_rom_data: bytes,
        char_rom_data: bytes,
        *,
        blk1_rom_data: bytes | None = None,
        blk2_rom_data: bytes | None = None,
        blk3_rom_data: bytes | None = None,
        blk5_rom_data: bytes | None = None,
        io2_ram_enabled: bool = False,
        io3_ram_enabled: bool = False,
        audio_sample_rate: int = 44100,
    ):
        super().__init__(audio_sample_rate=audio_sample_rate)

        self.machine_id = "vic20ntsc"
        self.display_name = "Commodore VIC-20 NTSC (early scaffold)"
        self.input_keymap_name = "vic20"
        self.input_gamepad_map_name = "vic20"
        self.input_joystick_count = 1
        self.input_tap_hold_frames = 2
        self.input_quick_tap_max_frames = 1

        self.low_ram = RAMBlock(self.LOW_RAM_SIZE)
        self.main_ram = RAMBlock(self.MAIN_RAM_SIZE)
        self.color_ram = _ColorRAM()
        self.io2_ram = _IoRam() if io2_ram_enabled else None
        self.io3_ram = _IoRam() if io3_ram_enabled else None
        self.vic = VIC6560(
            sample_rate=audio_sample_rate,
            cycles_per_second=self.TSTATES_PER_FRAME * self.FRAMES_PER_SECOND,
        )
        self.io_space = _OpenBus()
        self.via1 = VIA6522()
        self.via2 = VIA6522()
        self.via1.connect_irq(self.bus.request_nmi, self._clear_nmi)
        self.via2.connect_irq(self.bus.request_irq, self.bus.clear_irq)
        self.key_matrix = [0x00] * 8
        self.joystick_state = 0
        self.via1.set_port_a_input_callback(self._read_via1_port_a)
        self.via2.set_port_a_input_callback(self._read_keyboard_rows)
        self.via2.set_port_b_input_callback(self._read_via2_port_b)

        self.char_rom = self._make_rom(self.CHAR_ROM_SIZE, char_rom_data, slot_id="char")
        self.basic_rom = self._make_rom(self.BASIC_ROM_SIZE, basic_rom_data, slot_id="basic")
        self.kernal_rom = self._make_rom(self.KERNAL_ROM_SIZE, kernal_rom_data, slot_id="kernal")
        self.blk1_rom = self._make_optional_rom(blk1_rom_data, slot_id="blk1")
        self.blk2_rom = self._make_optional_rom(blk2_rom_data, slot_id="blk2")
        self.blk3_rom = self._make_optional_rom(blk3_rom_data, slot_id="blk3")
        self.blk5_rom = self._make_optional_rom(blk5_rom_data, slot_id="blk5")

        self.bus.map_block(0x0000, self.low_ram, size=self.low_ram.size)
        self.bus.map_block(0x1000, self.main_ram, size=self.main_ram.size)
        self.bus.map_block(0x8000, self.char_rom, size=self.char_rom.size)
        self.bus.map_block(0x9000, self.io_space, size=self.io_space.size)
        self.bus.map_block(0x9000, self.vic, size=self.vic.size)
        self.bus.map_block(0x9110, self.via1, size=self.via1.size)
        self.bus.map_block(0x9120, self.via2, size=self.via2.size)
        self.bus.map_block(0x9400, self.color_ram, size=self.color_ram.size)
        self.bus.map_block(0x9600, self.color_ram, size=self.color_ram.size)
        if self.io2_ram is not None:
            self.bus.map_block(0x9800, self.io2_ram, size=self.io2_ram.size)
        if self.io3_ram is not None:
            self.bus.map_block(0x9C00, self.io3_ram, size=self.io3_ram.size)
        self.bus.map_block(0xC000, self.basic_rom, size=self.basic_rom.size)
        self.bus.map_block(0xE000, self.kernal_rom, size=self.kernal_rom.size)
        self.vic.configure_fetch_sources(char_rom=self.char_rom, bus=self.bus)

        if self.blk1_rom is not None:
            self.bus.map_block(0x2000, self.blk1_rom, size=self.blk1_rom.size)
        if self.blk2_rom is not None:
            self.bus.map_block(0x4000, self.blk2_rom, size=self.blk2_rom.size)
        if self.blk3_rom is not None:
            self.bus.map_block(0x6000, self.blk3_rom, size=self.blk3_rom.size)
        if self.blk5_rom is not None:
            self.bus.map_block(0xA000, self.blk5_rom, size=self.blk5_rom.size)

        self.frame_width = self.DISPLAY_WIDTH
        self.frame_height = self.DISPLAY_HEIGHT
        self.framebuffer_rgb24 = self._render_screen_frame()
        self.audio_samples = array("h")
        base_tstates = self.TSTATES_PER_FRAME // self.SCANLINES_PER_FRAME
        extra_tstates = self.TSTATES_PER_FRAME % self.SCANLINES_PER_FRAME
        self._scanline_tstates = [
            base_tstates + (1 if scanline < extra_tstates else 0)
            for scanline in range(self.SCANLINES_PER_FRAME)
        ]
        self._frame_runner = ScanlineFrameRunner(self.SCANLINES_PER_FRAME, self._scanline_tstates)
        self._device_clock = 0
        self.current_scanline = 0
        self._vic_bus_last_data = 0xFF
        self._vic_bus_last_high = 0x0F

        self.reset()

    def _make_rom(self, size: int, data: bytes, *, slot_id: str) -> ROMBlock:
        if len(data) != size:
            raise ValueError(f"la ROM {slot_id} de VIC-20 debe medir {size} bytes")
        rom = ROMBlock(size)
        rom.load_bytes(data)
        return rom

    def _make_optional_rom(self, data: bytes | None, *, slot_id: str) -> ROMBlock | None:
        if data is None:
            return None
        if not 0 < len(data) <= self.EXPANSION_ROM_SIZE:
            raise ValueError(
                f"la ROM {slot_id} de VIC-20 debe medir entre 1 y {self.EXPANSION_ROM_SIZE} bytes"
            )
        rom = ROMBlock(len(data))
        rom.load_bytes(data)
        return rom

    def reset(self):
        super().reset()
        self.low_ram.load(0, bytes(self.low_ram.size))
        self.main_ram.load(0, bytes(self.main_ram.size))
        self.color_ram.clear()
        if self.io2_ram is not None:
            self.io2_ram.clear()
        if self.io3_ram is not None:
            self.io3_ram.clear()
        self.vic.reset()
        self.via1.reset()
        self.via2.reset()
        self.via1.set_port_a_input_callback(self._read_via1_port_a)
        self.via2.set_port_a_input_callback(self._read_keyboard_rows)
        self.via2.set_port_b_input_callback(self._read_via2_port_b)
        self.bus.clear_irq()
        self.bus.nmi_pending = False
        self.key_matrix = [0x00] * 8
        self.joystick_state = 0
        self._device_clock = 0
        self.current_scanline = 0
        self._vic_bus_last_data = 0xFF
        self._vic_bus_last_high = 0x0F
        self.framebuffer_rgb24 = self._render_screen_frame()
        self.audio_samples = array("h")

    def _begin_frame(self) -> None:
        self.frame_tstates = 0
        self._device_clock = 0
        self.current_scanline = 0
        self.vic.begin_frame(
            self.SCANLINES_PER_FRAME,
            self.frame_width,
            self.TSTATES_PER_FRAME,
            visible_line_start=self.VISIBLE_RASTER_START,
            visible_line_count=self.frame_height,
        )

    def _begin_scanline(self, scanline: int) -> None:
        self.current_scanline = scanline

    def _after_scanline_cpu(self, frame_tstates: int, scanline: int) -> None:
        self.current_scanline = scanline
        self._run_devices_until(frame_tstates)

    def _finish_frame(self) -> None:
        self.framebuffer_rgb24 = self._render_screen_frame()
        self.audio_samples = self.vic.get_frame_samples()
        self.audio_ring.write(self.audio_samples)
        self.frame_counter += 1

    def run_frame(self) -> int:
        return self._frame_runner.run(
            self,
            self.cpu.run_cycles,
            before_frame=self._begin_frame,
            before_scanline=self._begin_scanline,
            after_cpu=self._after_scanline_cpu,
            after_frame=self._finish_frame,
        )

    def render_frame(self):
        self.framebuffer_rgb24 = self._render_screen_frame()
        return self.framebuffer_rgb24

    def _run_devices_until(self, tstates: int):
        delta = tstates - self._device_clock
        if delta <= 0:
            return
        self.vic.run_cycles(
            delta,
            cycles_per_frame=self.TSTATES_PER_FRAME,
            raster_lines=self.SCANLINES_PER_FRAME,
        )
        self.via1.run_cycles(delta)
        self.via2.run_cycles(delta)
        self._device_clock = tstates

    def snapshot(self) -> dict:
        snap = self.cpu.snapshot()
        snap["tstates"] = self.tstates
        snap["frame_counter"] = self.frame_counter
        snap["frame_tstates"] = self.frame_tstates
        snap["vic_screen_base"] = self.vic.screen_base()
        snap["vic_char_base"] = self.vic.char_base()
        snap["vic_char_height"] = self.vic.char_height()
        snap["vic_raster_line"] = self.vic.raster_line()
        snap["vic_raster_cycle"] = self.vic.raster_cycle()
        snap["vic_aux_color"] = self.vic.auxiliary_color_index()
        snap["vic_volume"] = self.vic.volume()
        snap["vic_reverse_mode"] = self.vic.reverse_mode_enabled()
        snap["vic_area_state"] = self.vic.area_state()
        snap["vic_display_xstart"] = self.vic.display_xstart()
        snap["vic_display_xstop"] = self.vic.display_xstop()
        snap["vic_display_ystart"] = self.vic.display_ystart()
        snap["vic_display_ystop"] = self.vic.display_ystop()
        snap["via1_ifr"] = self.via1._read_ifr()
        snap["via2_ifr"] = self.via2._read_ifr()
        snap["has_blk1"] = self.blk1_rom is not None
        snap["has_blk2"] = self.blk2_rom is not None
        snap["has_blk3"] = self.blk3_rom is not None
        snap["has_blk5"] = self.blk5_rom is not None
        return snap

    def debug_devices(self) -> list[dict]:
        devices = super().debug_devices() + [
            self._debug_device("low_ram", self.low_ram, "memory", label="Low RAM"),
            self._debug_device("main_ram", self.main_ram, "memory", label="Main RAM"),
            self._debug_device("color_ram", self.color_ram, "memory", label="Color RAM"),
            self._debug_device("char_rom", self.char_rom, "memory", label="Character ROM"),
            self._debug_device("basic_rom", self.basic_rom, "memory", label="BASIC ROM"),
            self._debug_device("kernal_rom", self.kernal_rom, "memory", label="KERNAL ROM"),
            self._debug_device("vic", self.vic, "chip", label="VIC-I"),
            self._debug_device("via1", self.via1, "chip", label="VIA #1"),
            self._debug_device("via2", self.via2, "chip", label="VIA #2"),
        ]
        if self.io2_ram is not None:
            devices.append(self._debug_device("io2_ram", self.io2_ram, "memory", label="IO2 RAM"))
        if self.io3_ram is not None:
            devices.append(self._debug_device("io3_ram", self.io3_ram, "memory", label="IO3 RAM"))
        if self.blk1_rom is not None:
            devices.append(self._debug_device("blk1_rom", self.blk1_rom, "memory", label="BLK1 ROM"))
        if self.blk2_rom is not None:
            devices.append(self._debug_device("blk2_rom", self.blk2_rom, "memory", label="BLK2 ROM"))
        if self.blk3_rom is not None:
            devices.append(self._debug_device("blk3_rom", self.blk3_rom, "memory", label="BLK3 ROM"))
        if self.blk5_rom is not None:
            devices.append(self._debug_device("blk5_rom", self.blk5_rom, "memory", label="BLK5 ROM"))
        return devices

    def _clear_nmi(self) -> None:
        self.bus.nmi_pending = False

    def clear_input_state(self):
        self.key_matrix = [0x00] * 8
        self.joystick_state = 0

    def handle_input_event(self, event):
        if not isinstance(event, InputEvent):
            raise TypeError(f"evento de input inválido: {type(event)!r}")
        if event.kind == "key_matrix":
            row = max(0, min(7, event.control_a))
            col = max(0, min(7, event.control_b))
            mask = 1 << col
            if event.active:
                self.key_matrix[row] |= mask
            else:
                self.key_matrix[row] &= ~mask
            return

        if event.kind == "joystick":
            joystick_index = int(event.control_a)
            if joystick_index != 0:
                raise ValueError(f"joystick fuera de rango: {joystick_index}")
            mask = int(event.control_b) & 0x3F
            if event.active:
                self.joystick_state |= mask
            else:
                self.joystick_state &= ~mask
            self.joystick_state &= 0x3F
            return

        raise ValueError(f"tipo de input no soportado: {event.kind}")

    def _read_keyboard_rows(self) -> int:
        selected_columns = (~self.via2.orb) & self.via2.ddrb & 0xFF
        rows = 0xFF
        for row in range(8):
            if self.key_matrix[row] & selected_columns:
                rows &= ~(1 << row)
        return rows

    def _read_via1_port_a(self) -> int:
        value = 0xFF
        if self.joystick_state & JOYSTICK_UP:
            value &= ~(1 << 2)
        if self.joystick_state & JOYSTICK_DOWN:
            value &= ~(1 << 3)
        if self.joystick_state & JOYSTICK_LEFT:
            value &= ~(1 << 4)
        if self.joystick_state & (JOYSTICK_FIRE | JOYSTICK_FIRE_2):
            value &= ~(1 << 5)
        return value

    def _read_via2_port_b(self) -> int:
        value = 0xFF
        if self.joystick_state & JOYSTICK_RIGHT:
            value &= ~(1 << 7)
        return value

    def _read_vic_visible(self, addr: int) -> int:
        """Read memory as seen by the VIC-I, not as seen by the CPU.

        The VIC only sees:
        - character ROM at 0x8000-0x8FFF
        - the lowest 8 KB of RAM at 0x0000-0x1FFF
        I/O and the rest of the CPU address space are not part of its normal
        fetch window.
        """
        if addr >= 0x8000:
            return self.char_rom.read((addr - 0x8000) & 0x0FFF)
        if addr >= 0x0000:
            return self.bus.read8(addr & 0x1FFF)
        return 0xFF

    def _vic_fetch_color(self, addr: int) -> int:
        color = self.bus.read8(addr) & 0x0F
        self._vic_bus_last_high = color
        return color

    def _vic_fetch_byte(self, addr: int) -> int:
        if 0x8000 <= addr < 0x9000:
            value = self.char_rom.read((addr - 0x8000) & 0x0FFF)
        elif 0x0000 <= addr < 0x0400 or 0x1000 <= addr < 0x2000:
            value = self.bus.read8(addr & 0x1FFF)
        elif 0x9400 <= addr < 0x9800:
            value = self.bus.read8(addr)
        else:
            value = self._vic_bus_last_data & (0xF0 | self._vic_bus_last_high)
        self._vic_bus_last_data = value & 0xFF
        return value & 0xFF

    def _render_screen_frame(self) -> bytes:
        width = self.frame_width
        height = self.frame_height
        screen_columns = min(self.SCREEN_COLUMNS, self.vic.screen_columns())
        screen_rows = min(self.SCREEN_ROWS, self.vic.screen_rows())
        screen_base = self.vic.screen_base()
        accent = (31, 63, 38)
        visible_x0, visible_y0, visible_x1, visible_y1 = self.vic.visible_bounds(
            width,
            height,
            screen_columns,
            screen_rows,
        )

        out = bytearray(width * height * 3)
        for y in range(height):
            row_start = y * width * 3
            for span_x0, span_x1, span_bg, span_border in self.vic.bg_border_spans_for_line(y, width):
                span_rgb = self.PALETTE_BYTES[span_border & 0x07]
                start = row_start + (span_x0 * 3)
                if span_x1 > span_x0:
                    out[start:row_start + (span_x1 * 3)] = span_rgb * (span_x1 - span_x0)
            if visible_y0 <= y < visible_y1:
                for span_x0, span_x1, span_bg, _ in self.vic.bg_border_spans_for_line(y, width):
                    display_x0 = max(visible_x0, span_x0)
                    display_x1 = min(visible_x1, span_x1)
                    if display_x1 <= display_x0:
                        continue
                    bg_rgb = self.PALETTE_BYTES[span_bg & 0x0F]
                    display_start = row_start + (display_x0 * 3)
                    out[display_start:row_start + (display_x1 * 3)] = bg_rgb * (display_x1 - display_x0)

        for y in range(visible_y0, visible_y1):
            fetch_contexts = self.vic.display_latched_contexts_for_scanline(y, width, height)
            if not fetch_contexts:
                if self.vic.has_completed_fetch_buffers():
                    continue
                fetch_cells = self.vic.display_fetch_cells_for_scanline(y, width, height)
                screen_codes = [self._read_vic_visible(screen_addr) for _, _, _, _, screen_addr, _ in fetch_cells]
                color_nibbles = [self.bus.read8(color_addr) & 0x0F for _, _, _, _, _, color_addr in fetch_cells]
                glyph_row_bits = [
                    self._read_vic_visible(self.vic.glyph_row_address_for_cell(screen_code, pixel_y))
                    for (_, _, _, pixel_y, _, _), screen_code in zip(fetch_cells, screen_codes, strict=False)
                ]
                if _build_scanline_contexts_render is not None:
                    fetch_contexts = _build_scanline_contexts_render(
                        self.vic,
                        y,
                        width,
                        height,
                        screen_codes,
                        color_nibbles,
                        glyph_row_bits,
                    )
                else:
                    fetch_contexts = self.vic.display_fetch_contexts_for_scanline(
                        y,
                        width,
                        height,
                        screen_codes,
                        color_nibbles,
                        glyph_row_bits,
                    )
            if _draw_scanline_contexts_rgb24_render is not None and fetch_contexts:
                _draw_scanline_contexts_rgb24_render(
                    out,
                    width,
                    height,
                    y,
                    self.vic.char_height(),
                    fetch_contexts,
                )
            else:
                self._draw_scanline_contexts(out, width, height, y, fetch_contexts)
        return bytes(out)

    def _palette_color(self, color_index: int) -> tuple[int, int, int]:
        return self.PALETTE[color_index & 0x0F]

    def _cell_color_nibble(self, row: int, col: int, screen_columns: int, screen_base: int) -> int:
        color_addr = self.vic.color_address_for_cell(row, col, screen_columns)
        return self.bus.read8(color_addr) & 0x0F

    def _color_for_cell(
        self,
        row: int,
        col: int,
        screen_columns: int,
        screen_base: int,
        default: tuple[int, int, int],
        *,
        color_override: int | None = None,
    ) -> tuple[int, int, int]:
        if color_override is None:
            color_index = self._cell_color_nibble(row, col, screen_columns, screen_base)
        else:
            color_index = color_override & 0x0F
        return self.PALETTE[color_index & 0x0F]

    def _draw_char_cell_scanline(
        self,
        out: bytearray,
        width: int,
        height: int,
        x: int,
        y: int,
        screen_code: int,
        color_nibble: int,
        glyph_bits: int,
        reg_e: int,
        reg_f: int,
        half_flag: int,
        phase0_e: int,
        phase0_f: int,
        phase1_e: int,
        phase1_f: int,
        phase2_e: int,
        phase2_f: int,
    ) -> None:
        if not (0 <= y < height):
            return
        char_height = self.vic.char_height()
        for col in range(8):
            dst_x = x + col
            if not (0 <= dst_x < width):
                continue
            phase = self.vic.foreground_phase_for_pixel(col, half_flag)
            if phase == 0:
                pixel_reg_e, pixel_reg_f = phase0_e, phase0_f
            elif phase == 1:
                pixel_reg_e, pixel_reg_f = phase1_e, phase1_f
            else:
                pixel_reg_e, pixel_reg_f = phase2_e, phase2_f
            color_index = self.vic.effective_pixel_color_index(
                screen_code=screen_code,
                color_nibble=color_nibble,
                glyph_bits=glyph_bits,
                reg_e=pixel_reg_e,
                reg_f=pixel_reg_f,
                pixel_x=col,
                char_height=char_height,
            )
            color = self._palette_color(color_index)
            idx = (y * width + dst_x) * 3
            out[idx:idx + 3] = bytes(color)

    def _draw_scanline_contexts(
        self,
        out: bytearray,
        width: int,
        height: int,
        y: int,
        fetch_contexts,
    ) -> None:
        for (
            _,
            _,
            cell_x,
            _,
            _,
            _,
            screen_code,
            color_nibble,
            _,
            glyph_bits,
            reg_e,
            reg_f,
            _,
            half_flag,
            phase0_e,
            phase0_f,
            phase1_e,
            phase1_f,
            phase2_e,
            phase2_f,
        ) in fetch_contexts:
            self._draw_char_cell_scanline(
                out,
                width,
                height,
                cell_x,
                y,
                screen_code,
                color_nibble,
                glyph_bits,
                reg_e,
                reg_f,
                half_flag,
                phase0_e,
                phase0_f,
                phase1_e,
                phase1_f,
                phase2_e,
                phase2_f,
            )


VIC20NTSC = VIC20


class VIC20PAL(VIC20):
    DISPLAY_WIDTH = 224
    DISPLAY_HEIGHT = 284
    TSTATES_PER_FRAME = 22_152
    FRAMES_PER_SECOND = 50
    SCANLINES_PER_FRAME = 312
    VISIBLE_RASTER_START = 28

    def __init__(
        self,
        basic_rom_data: bytes,
        kernal_rom_data: bytes,
        char_rom_data: bytes,
        *,
        blk1_rom_data: bytes | None = None,
        blk2_rom_data: bytes | None = None,
        blk3_rom_data: bytes | None = None,
        blk5_rom_data: bytes | None = None,
        io2_ram_enabled: bool = False,
        io3_ram_enabled: bool = False,
        audio_sample_rate: int = 44100,
    ):
        super().__init__(
            basic_rom_data,
            kernal_rom_data,
            char_rom_data,
            blk1_rom_data=blk1_rom_data,
            blk2_rom_data=blk2_rom_data,
            blk3_rom_data=blk3_rom_data,
            blk5_rom_data=blk5_rom_data,
            io2_ram_enabled=io2_ram_enabled,
            io3_ram_enabled=io3_ram_enabled,
            audio_sample_rate=audio_sample_rate,
        )
        self.machine_id = "vic20pal"
        self.display_name = "Commodore VIC-20 PAL (early scaffold)"
