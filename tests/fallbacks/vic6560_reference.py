from __future__ import annotations

from array import array


class VIC6560:
    """Python reference VIC-I model.

    Keep this fallback aligned with the canonical Cython implementation in
    ``chipsets/vic6560.pyx``.
    """

    size = 0x10

    DEFAULT_REGISTERS = bytes(
        [
            0x05,
            0x19,
            0x16,
            0x2E,
            0x00,
            0xC0,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x1B,
        ]
    )

    _CHAR_BASE_LOOKUP = {
        0x0: 0x8000,
        0x1: 0x8400,
        0x2: 0x8800,
        0x3: 0x8C00,
        0x8: 0x0000,
        0xC: 0x1000,
        0xD: 0x1400,
        0xE: 0x1800,
        0xF: 0x1C00,
    }

    AREA_IDLE = "idle"
    AREA_PENDING = "pending"
    AREA_DISPLAY = "display"
    AREA_DONE = "done"
    _MAX_OUTPUT_LEVEL = 29 * 15

    def __init__(self, *, sample_rate: int = 44100, cycles_per_second: int = 1_105_920):
        self.registers = bytearray(self.DEFAULT_REGISTERS)
        self.sample_rate = max(1, int(sample_rate))
        self.cycles_per_second = max(1, int(cycles_per_second))
        self._raster_line = 0
        self._cycles_into_frame = 0
        self._frame_raster_lines = 0
        self._frame_width = 0
        self._cycles_per_frame = 0
        self._display_xstart = -1
        self._display_xstop = -1
        self._fetch_xstart = -1
        self._fetch_xstop = -1
        self._display_ystart = -1
        self._display_ystop = -1
        self._area_state = self.AREA_IDLE
        self._aux_events: list[tuple[int, int]] = []
        self._bg_events: list[tuple[int, int, int]] = []
        self._reverse_events: list[tuple[int, int]] = []
        self._foreground_events: dict[int, list[tuple[int, int, int, int, int, int, int, int]]] = {}
        self._sound_counters = [1, 1, 1, 1]
        self._sound_shift = [0, 0, 0, 0]
        self._sound_output = [0, 0, 0, 0]
        self._noise_lfsr = 0x0000
        self._noise_lfsr0_old = 0
        self._sound_accum = 0.0
        self._sound_accum_cycles = 0
        self._sound_sample_clock = 0.0
        self._cycles_per_sample = self.cycles_per_second / float(self.sample_rate)
        self._frame_samples = array("h")
        dt = 1.0 / float(self.sample_rate)
        self._lowpassbuf = 0.0
        self._highpassbuf = 0.0
        self._lowpassbeta = dt / (dt + 1e-4)
        self._highpassbeta = dt / (dt + 1e-3)

    def reset(self) -> None:
        self.registers[:] = self.DEFAULT_REGISTERS
        self._raster_line = 0
        self._cycles_into_frame = 0
        self._frame_raster_lines = 0
        self._frame_width = 0
        self._cycles_per_frame = 0
        self._display_xstart = -1
        self._display_xstop = -1
        self._fetch_xstart = -1
        self._fetch_xstop = -1
        self._display_ystart = -1
        self._display_ystop = -1
        self._area_state = self.AREA_IDLE
        self._aux_events = []
        self._bg_events = []
        self._reverse_events = []
        self._foreground_events = {}
        self._sound_counters = [1, 1, 1, 1]
        self._sound_shift = [0, 0, 0, 0]
        self._sound_output = [0, 0, 0, 0]
        self._noise_lfsr = 0x0000
        self._noise_lfsr0_old = 0
        self._sound_accum = 0.0
        self._sound_accum_cycles = 0
        self._sound_sample_clock = 0.0
        self._frame_samples = array("h")
        self._lowpassbuf = 0.0
        self._highpassbuf = 0.0

    def read(self, addr: int) -> int:
        reg = addr & 0x0F
        if reg == 0x03:
            return (self.registers[0x03] & 0x7F) | ((self._raster_line & 0x01) << 7)
        if reg == 0x04:
            return (self._raster_line >> 1) & 0xFF
        return self.registers[reg]

    def write(self, addr: int, value: int) -> None:
        reg = addr & 0x0F
        if reg == 0x04:
            return
        old_reg_e = self.registers[0x0E]
        old_reg_f = self.registers[0x0F]
        self.registers[reg] = value & 0xFF
        if reg == 0x0E:
            self._stamp_aux_change()
            self._stamp_foreground_change(old_reg_e, old_reg_f)
        if reg == 0x0F:
            self._stamp_bg_border_change()
            self._stamp_reverse_change()
            self._stamp_foreground_change(old_reg_e, old_reg_f)

    def begin_frame(self, raster_lines: int, frame_width: int, cycles_per_frame: int) -> None:
        self._cycles_into_frame = 0
        self._raster_line = 0
        self._frame_raster_lines = max(1, raster_lines)
        self._frame_width = max(1, frame_width)
        self._cycles_per_frame = max(1, cycles_per_frame)
        self._display_xstart = -1
        self._display_xstop = -1
        self._fetch_xstart = -1
        self._fetch_xstop = -1
        self._display_ystart = -1
        self._display_ystop = -1
        self._area_state = self.AREA_IDLE
        reg_e = self.registers[0x0E]
        reg_f = self.registers[0x0F]
        self._aux_events = [(0, (reg_e >> 4) & 0x0F)]
        self._bg_events = [(0, (reg_f >> 4) & 0x0F, reg_f & 0x07)]
        self._reverse_events = [(0, 1 if (reg_f & 0x08) == 0 else 0)]
        self._foreground_events = {}
        self._frame_samples = array("h")

    def run_cycles(self, cycles: int, *, cycles_per_frame: int, raster_lines: int) -> None:
        if cycles <= 0 or cycles_per_frame <= 0 or raster_lines <= 0:
            return
        self._frame_raster_lines = raster_lines
        self._cycles_per_frame = cycles_per_frame
        self._cycles_into_frame = (self._cycles_into_frame + cycles) % cycles_per_frame
        self._raster_line = (self._cycles_into_frame * raster_lines) // cycles_per_frame
        self._update_display_state()
        self._run_sound_cycles(cycles)

    def screen_columns(self) -> int:
        return max(1, min(32, self.registers[0x02] & 0x7F))

    def screen_rows(self) -> int:
        return max(1, min(32, (self.registers[0x03] & 0x7E) >> 1))

    def char_height(self) -> int:
        return 16 if (self.registers[0x03] & 0x01) else 8

    def glyph_count(self) -> int:
        return 0x100 if self.char_height() > 8 else 0x80

    def char_window_size(self) -> int:
        return 0x1000 if self.char_height() > 8 else 0x0400

    def glyph_index(self, screen_code: int) -> int:
        if self.char_height() > 8:
            return screen_code & 0xFF
        return screen_code & 0x7F

    def glyph_row_address(self, screen_code: int, row: int) -> int:
        glyph_height = self.char_height()
        glyph_row = max(0, min(glyph_height - 1, row))
        char_window_mask = self.char_window_size() - 1
        glyph_offset = (self.glyph_index(screen_code) * glyph_height) + glyph_row
        return self.char_base() + (glyph_offset & char_window_mask)

    def horizontal_offset(self, frame_width: int, screen_columns: int) -> int:
        visible_width = screen_columns * 8
        margin = max(0, frame_width - visible_width)
        requested = self.registers[0x00] + 4
        return max(0, min(margin, requested))

    def vertical_offset(self, frame_height: int, screen_rows: int) -> int:
        visible_height = screen_rows * self.char_height()
        margin = max(0, frame_height - visible_height)
        requested = max(0, self.registers[0x01] - 22)
        return max(0, min(margin, requested))

    def visible_width(self, screen_columns: int) -> int:
        return max(0, screen_columns * 8)

    def visible_height(self, screen_rows: int) -> int:
        return max(0, screen_rows * self.char_height())

    def visible_bounds(self, frame_width: int, frame_height: int, screen_columns: int, screen_rows: int) -> tuple[int, int, int, int]:
        x0 = self.horizontal_offset(frame_width, screen_columns)
        y0 = self.vertical_offset(frame_height, screen_rows)
        return (
            x0,
            y0,
            x0 + self.visible_width(screen_columns),
            y0 + self.visible_height(screen_rows),
        )

    def cell_origin(self, row: int, col: int, frame_width: int, frame_height: int) -> tuple[int, int]:
        screen_columns = self.screen_columns()
        screen_rows = self.screen_rows()
        x0, y0, _, _ = self.visible_bounds(frame_width, frame_height, screen_columns, screen_rows)
        return x0 + (max(0, col) * 8), y0 + (max(0, row) * self.char_height())

    def display_cell_at_position(
        self,
        x: int,
        y: int,
        frame_width: int,
        frame_height: int,
    ) -> tuple[int, int, int, int] | None:
        screen_columns = self.screen_columns()
        screen_rows = self.screen_rows()
        x0, y0, x1, y1 = self.visible_bounds(frame_width, frame_height, screen_columns, screen_rows)
        if self._fetch_xstart >= 0:
            x0 = self._fetch_xstart
        if self._fetch_xstop >= 0:
            x1 = self._fetch_xstop + 1
        if not (x0 <= x < x1 and y0 <= y < y1):
            return None
        rel_x = x - x0
        rel_y = y - y0
        col = rel_x // 8
        row = rel_y // self.char_height()
        if not (0 <= col < screen_columns and 0 <= row < screen_rows):
            return None
        return row, col, rel_x % 8, rel_y % self.char_height()

    def screen_address_for_cell(self, row: int, col: int, screen_columns: int | None = None) -> int:
        if screen_columns is None:
            screen_columns = self.screen_columns()
        return self.screen_base() + (max(0, row) * max(1, screen_columns)) + max(0, col)

    def color_address_for_cell(self, row: int, col: int, screen_columns: int | None = None) -> int:
        screen_addr = self.screen_address_for_cell(row, col, screen_columns)
        return 0x9400 | (screen_addr & 0x03FF)

    def glyph_row_address_for_cell(self, screen_code: int, pixel_y: int) -> int:
        return self.glyph_row_address(screen_code, pixel_y)

    def display_fetch_addresses_for_position(
        self,
        x: int,
        y: int,
        frame_width: int,
        frame_height: int,
        screen_code: int,
    ) -> tuple[int, int, int, int, int, int, int] | None:
        cell = self.display_cell_at_position(x, y, frame_width, frame_height)
        if cell is None:
            return None
        row, col, pixel_x, pixel_y = cell
        screen_columns = self.screen_columns()
        screen_addr = self.screen_address_for_cell(row, col, screen_columns)
        color_addr = self.color_address_for_cell(row, col, screen_columns)
        glyph_addr = self.glyph_row_address_for_cell(screen_code, pixel_y)
        return row, col, pixel_x, pixel_y, screen_addr, color_addr, glyph_addr

    def display_fetch_slot_for_position(
        self,
        x: int,
        y: int,
        frame_width: int,
        frame_height: int,
    ) -> tuple[int, int, int, int, int] | None:
        cell = self.display_cell_at_position(x, y, frame_width, frame_height)
        if cell is None:
            return None
        row, col, pixel_x, pixel_y = cell
        half_flag = 1 if pixel_x >= 4 else 0
        return row, col, pixel_x, pixel_y, half_flag

    def display_fetch_cells_for_text_row(
        self,
        text_row: int,
        frame_width: int,
        frame_height: int,
    ) -> list[tuple[int, int, int, int, int]]:
        screen_columns = self.screen_columns()
        screen_rows = self.screen_rows()
        if not (0 <= text_row < screen_rows):
            return []
        cells: list[tuple[int, int, int, int, int]] = []
        for col in range(screen_columns):
            cell_x, cell_y = self.cell_origin(text_row, col, frame_width, frame_height)
            screen_addr = self.screen_address_for_cell(text_row, col, screen_columns)
            color_addr = self.color_address_for_cell(text_row, col, screen_columns)
            cells.append((col, cell_x, cell_y, screen_addr, color_addr))
        return cells

    def display_fetch_cells_for_scanline(
        self,
        y: int,
        frame_width: int,
        frame_height: int,
    ) -> list[tuple[int, int, int, int, int, int]]:
        screen_columns = self.screen_columns()
        screen_rows = self.screen_rows()
        x0, _, x1, _ = self.visible_bounds(frame_width, frame_height, screen_columns, screen_rows)
        fetch_x = self._fetch_xstart
        if fetch_x < 0:
            fetch_x = min(x1 - 1, x0 + 16)
        cell = self.display_cell_at_position(fetch_x, y, frame_width, frame_height)
        if cell is None:
            return []
        row, _, _, pixel_y = cell
        cells: list[tuple[int, int, int, int, int, int]] = []
        for col in range(screen_columns):
            cell_x, _ = self.cell_origin(row, col, frame_width, frame_height)
            screen_addr = self.screen_address_for_cell(row, col, screen_columns)
            color_addr = self.color_address_for_cell(row, col, screen_columns)
            cells.append((row, col, cell_x, pixel_y, screen_addr, color_addr))
        return cells

    def display_fetch_addresses_for_scanline_cell(
        self,
        y: int,
        frame_width: int,
        frame_height: int,
        col: int,
        screen_code: int,
    ) -> tuple[int, int, int, int, int, int, int] | None:
        scanline_cells = self.display_fetch_cells_for_scanline(y, frame_width, frame_height)
        if not scanline_cells:
            return None
        screen_columns = self.screen_columns()
        if not (0 <= col < screen_columns):
            return None
        row, _, cell_x, pixel_y, screen_addr, color_addr = scanline_cells[col]
        glyph_addr = self.glyph_row_address_for_cell(screen_code, pixel_y)
        return row, col, cell_x, pixel_y, screen_addr, color_addr, glyph_addr

    def display_fetch_contexts_for_scanline(
        self,
        y: int,
        frame_width: int,
        frame_height: int,
        screen_codes: list[int],
        color_nibbles: list[int],
        glyph_bits: list[int],
    ) -> list[tuple[int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int]]:
        cells = self.display_fetch_cells_for_scanline(y, frame_width, frame_height)
        contexts: list[
            tuple[int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int]
        ] = []
        for index, cell in enumerate(cells):
            if index >= len(screen_codes) or index >= len(color_nibbles) or index >= len(glyph_bits):
                break
            row, col, cell_x, pixel_y, screen_addr, color_addr = cell
            screen_code = screen_codes[index] & 0xFF
            color_nibble = color_nibbles[index] & 0x0F
            glyph_addr = self.glyph_row_address_for_cell(screen_code, pixel_y)
            glyph_row_bits = glyph_bits[index] & 0xFF
            reg_e, reg_f = self.color_regs_for_position(y, cell_x)
            (
                half_flag,
                phase0_e,
                phase0_f,
                phase1_e,
                phase1_f,
                phase2_e,
                phase2_f,
            ) = self.foreground_reg_phase_values_for_cell(y, col, reg_e, reg_f)
            effective_reverse, multicolor_mode = self.effective_cell_mode(
                screen_code=screen_code,
                color_nibble=color_nibble,
                reg_f=reg_f,
                char_height=self.char_height(),
            )
            contexts.append(
                (
                    row,
                    col,
                    cell_x,
                    pixel_y,
                    screen_addr,
                    color_addr,
                    screen_code,
                    color_nibble,
                    glyph_addr,
                    glyph_row_bits,
                    reg_e,
                    reg_f,
                    (1 if effective_reverse else 0) | ((1 if multicolor_mode else 0) << 1),
                    half_flag,
                    phase0_e,
                    phase0_f,
                    phase1_e,
                    phase1_f,
                    phase2_e,
                    phase2_f,
                )
            )
        return contexts

    def effective_cell_mode(
        self,
        *,
        screen_code: int,
        color_nibble: int,
        reg_f: int,
        char_height: int,
    ) -> tuple[bool, bool]:
        reverse_code = (screen_code & 0x80) != 0 and char_height <= 8
        effective_reverse = ((reg_f & 0x08) == 0) ^ reverse_code
        multicolor_mode = (color_nibble & 0x08) != 0
        return effective_reverse, multicolor_mode

    def effective_pixel_color_index(
        self,
        *,
        screen_code: int,
        color_nibble: int,
        glyph_bits: int,
        reg_e: int,
        reg_f: int,
        pixel_x: int,
        char_height: int,
    ) -> int:
        effective_reverse, multicolor_mode = self.effective_cell_mode(
            screen_code=screen_code,
            color_nibble=color_nibble,
            reg_f=reg_f,
            char_height=char_height,
        )
        bg = (reg_f >> 4) & 0x0F
        if multicolor_mode:
            pair_bits = (glyph_bits >> (6 - (((pixel_x & 0x07) // 2) * 2))) & 0x03
            if pair_bits == 0x00:
                return bg
            if pair_bits == 0x01:
                return reg_f & 0x07
            if pair_bits == 0x02:
                return (reg_e >> 4) & 0x0F
            return color_nibble & 0x07

        row_bits = glyph_bits ^ 0xFF if effective_reverse else glyph_bits
        pixel_on = (row_bits & (0x80 >> (pixel_x & 0x07))) != 0
        return (color_nibble & 0x0F) if pixel_on else bg

    def display_pixel_color_index_for_position(
        self,
        *,
        x: int,
        y: int,
        frame_width: int,
        frame_height: int,
        screen_code: int,
        color_nibble: int,
        glyph_bits: int,
        reg_e: int,
        reg_f: int,
        char_height: int,
    ) -> int | None:
        fetch = self.display_fetch_addresses_for_position(
            x,
            y,
            frame_width,
            frame_height,
            screen_code,
        )
        if fetch is None:
            return None
        _, display_col, pixel_x, _, _, _, _ = fetch
        reg_e, reg_f = self.foreground_regs_for_cell_pixel(
            y,
            display_col,
            pixel_x,
            reg_e,
            reg_f,
        )
        return self.effective_pixel_color_index(
            screen_code=screen_code,
            color_nibble=color_nibble,
            glyph_bits=glyph_bits,
            reg_e=reg_e,
            reg_f=reg_f,
            pixel_x=pixel_x,
            char_height=char_height,
        )

    def screen_base(self) -> int:
        hibase = ((self.registers[0x05] >> 3) & 0x1C) | (0x02 if (self.registers[0x02] & 0x80) else 0x00)
        return (hibase & 0xFF) << 8

    def char_base(self) -> int:
        char_bits = self.registers[0x05] & 0x0F
        return self._CHAR_BASE_LOOKUP.get(char_bits, 0x8000 + (char_bits << 10))

    def border_color_index(self) -> int:
        return self.registers[0x0F] & 0x07

    def screen_color_index(self) -> int:
        return (self.registers[0x0F] >> 4) & 0x0F

    def reverse_mode_enabled(self) -> bool:
        return (self.registers[0x0F] & 0x08) == 0

    def auxiliary_color_index(self) -> int:
        return (self.registers[0x0E] >> 4) & 0x0F

    def volume(self) -> int:
        return self.registers[0x0E] & 0x0F

    def raster_line(self) -> int:
        return self._raster_line

    def raster_cycle(self) -> int:
        return self._cycles_into_frame % self.cycles_per_line()

    def display_xstart(self) -> int:
        return self._display_xstart

    def display_xstop(self) -> int:
        return self._display_xstop

    def display_ystart(self) -> int:
        return self._display_ystart

    def display_ystop(self) -> int:
        return self._display_ystop

    def fetch_xstart(self) -> int:
        return self._fetch_xstart

    def fetch_xstop(self) -> int:
        return self._fetch_xstop

    def area_state(self) -> str:
        return self._area_state

    def border_color_index_for_line(self, line: int) -> int:
        _, reg_f = self._color_regs_for_position(line, 0)
        return reg_f & 0x07

    def screen_color_index_for_line(self, line: int) -> int:
        _, reg_f = self._color_regs_for_position(line, self._line_sample_x(line))
        return (reg_f >> 4) & 0x0F

    def reverse_mode_enabled_for_line(self, line: int) -> bool:
        _, reg_f = self._color_regs_for_position(line, self._line_sample_x(line))
        return (reg_f & 0x08) == 0

    def auxiliary_color_index_for_line(self, line: int) -> int:
        reg_e, _ = self._color_regs_for_position(line, self._line_sample_x(line))
        return (reg_e >> 4) & 0x0F

    def color_regs_for_position(self, line: int, x: int) -> tuple[int, int]:
        aux_color, bg_color, border_color, reverse_enabled = self._state_for_position(line, x)
        reg_e = (aux_color & 0x0F) << 4
        reg_f = ((bg_color & 0x0F) << 4) | (border_color & 0x07)
        if not reverse_enabled:
            reg_f |= 0x08
        return reg_e, reg_f

    def get_frame_samples(self) -> array:
        return array("h", self._frame_samples)

    def foreground_regs_for_cell_pixel(
        self,
        line: int,
        col: int,
        pixel: int,
        reg_e: int,
        reg_f: int,
    ) -> tuple[int, int]:
        half_flag, phase0_e, phase0_f, phase1_e, phase1_f, phase2_e, phase2_f = (
            self.foreground_reg_phase_values_for_cell(line, col, reg_e, reg_f)
        )
        phase = self._foreground_phase(pixel, half_flag)
        if phase == 0:
            return phase0_e, phase0_f
        if phase == 1:
            return phase1_e, phase1_f
        return phase2_e, phase2_f

    def foreground_phase_for_pixel(self, pixel: int, half_flag: int) -> int:
        return self._foreground_phase(pixel, half_flag)

    def foreground_reg_phase_values_for_cell(
        self,
        line: int,
        col: int,
        reg_e: int,
        reg_f: int,
    ) -> tuple[int, int, int, int, int, int, int]:
        event = self._foreground_event_for_cell(line, col)
        if event is None:
            return 0, reg_e, reg_f, reg_e, reg_f, reg_e, reg_f

        _, half_flag, old_aux, new_aux, old_border, new_border, old_reverse, new_reverse = event
        bg = (reg_f >> 4) & 0x0F

        def _phase_regs(aux: int, border: int, reverse_enabled: bool) -> tuple[int, int]:
            out_reg_e = (aux & 0x0F) << 4
            out_reg_f = ((bg & 0x0F) << 4) | (border & 0x07)
            if not reverse_enabled:
                out_reg_f |= 0x08
            return out_reg_e, out_reg_f

        phase0_e, phase0_f = _phase_regs(old_aux, old_border, bool(old_reverse))
        phase1_e, phase1_f = _phase_regs(new_aux, new_border, bool(old_reverse))
        phase2_e, phase2_f = _phase_regs(new_aux, new_border, bool(new_reverse))
        return half_flag, phase0_e, phase0_f, phase1_e, phase1_f, phase2_e, phase2_f

    def is_display_position(self, line: int, x: int) -> bool:
        if self._fetch_xstart < 0 or self._display_ystart < 0:
            return False
        return (
            self._display_ystart <= line <= self._display_ystop
            and self._fetch_xstart <= x <= self._fetch_xstop
        )

    def cycles_per_line(self) -> int:
        if self._frame_raster_lines <= 0:
            return 1
        return max(1, self._cycles_per_frame // self._frame_raster_lines)

    def cycle_pixel_x(self, cycle_in_line: int) -> int:
        x = (4 * (int(cycle_in_line) - 7)) + 1
        return max(0, min(self._frame_width - 1, x))

    def _color_regs_for_position(self, line: int, x: int) -> tuple[int, int]:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0:
            return self.registers[0x0E], self.registers[0x0F]
        aux_color, bg_color, border_color, reverse_enabled = self._state_for_position(line, x)
        reg_e = (aux_color & 0x0F) << 4
        reg_f = ((bg_color & 0x0F) << 4) | (border_color & 0x07)
        if not reverse_enabled:
            reg_f |= 0x08
        return reg_e, reg_f

    def _state_for_position(self, line: int, x: int) -> tuple[int, int, int, bool]:
        clamped_line = max(0, min(self._frame_raster_lines - 1, line))
        clamped_x = max(0, min(self._frame_width - 1, x))
        pixel_index = (clamped_line * self._frame_width) + clamped_x
        aux_color = self._aux_events[0][1] if self._aux_events else ((self.registers[0x0E] >> 4) & 0x0F)
        if self._bg_events:
            bg_color = self._bg_events[0][1]
            border_color = self._bg_events[0][2]
        else:
            bg_color = (self.registers[0x0F] >> 4) & 0x0F
            border_color = self.registers[0x0F] & 0x07
        reverse_enabled = bool(self._reverse_events[0][1]) if self._reverse_events else ((self.registers[0x0F] & 0x08) == 0)
        if self.is_display_position(clamped_line, clamped_x):
            for event_index, event_aux in self._aux_events:
                if event_index > pixel_index:
                    break
                aux_color = event_aux
            for event_index, event_bg, event_border in self._bg_events:
                if event_index > pixel_index:
                    break
                bg_color = event_bg
                border_color = event_border
            for event_index, event_reverse in self._reverse_events:
                if event_index > pixel_index:
                    break
                reverse_enabled = bool(event_reverse)
        return aux_color, bg_color, border_color, reverse_enabled

    def _stamp_aux_change(self) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        pixel_index = self._current_pixel_index(0)
        event = (pixel_index, (self.registers[0x0E] >> 4) & 0x0F)
        if self._aux_events and self._aux_events[-1][0] == pixel_index:
            self._aux_events[-1] = event
            return
        self._aux_events.append(event)

    def _stamp_bg_border_change(self) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        pixel_index = self._current_pixel_index(0)
        reg_f = self.registers[0x0F]
        event = (pixel_index, (reg_f >> 4) & 0x0F, reg_f & 0x07)
        if self._bg_events and self._bg_events[-1][0] == pixel_index:
            self._bg_events[-1] = event
            return
        self._bg_events.append(event)

    def _stamp_reverse_change(self) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        pixel_index = self._current_pixel_index(2)
        event = (pixel_index, 1 if (self.registers[0x0F] & 0x08) == 0 else 0)
        if self._reverse_events and self._reverse_events[-1][0] == pixel_index:
            self._reverse_events[-1] = event
            return
        self._reverse_events.append(event)

    def _stamp_foreground_change(self, old_reg_e: int, old_reg_f: int) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        if self._fetch_xstart < 0 or self._display_ystart < 0:
            return

        line = max(0, min(self._frame_raster_lines - 1, self._raster_line))
        if not (self._display_ystart <= line <= self._display_ystop):
            return

        current_x = self.cycle_pixel_x(self.raster_cycle())
        fetch_slot = self.display_fetch_slot_for_position(
            current_x,
            line,
            self._frame_width,
            self._frame_raster_lines,
        )
        if fetch_slot is None:
            return
        _, char_index, _, _, half_flag = fetch_slot
        new_reg_e = self.registers[0x0E]
        new_reg_f = self.registers[0x0F]
        event = (
            char_index,
            half_flag,
            (old_reg_e >> 4) & 0x0F,
            (new_reg_e >> 4) & 0x0F,
            old_reg_f & 0x07,
            new_reg_f & 0x07,
            1 if (old_reg_f & 0x08) == 0 else 0,
            1 if (new_reg_f & 0x08) == 0 else 0,
        )
        events = self._foreground_events.setdefault(line, [])
        if events and events[-1][0] == char_index:
            events[-1] = event
            return
        events.append(event)

    def _current_pixel_index(self, x_bias: int) -> int:
        cycles_per_line = self.cycles_per_line()
        total_pixels = self._frame_width * self._frame_raster_lines
        line = max(0, min(self._frame_raster_lines - 1, self._raster_line))
        cycles_into_line = self._cycles_into_frame % cycles_per_line
        x = self.cycle_pixel_x(cycles_into_line) + x_bias
        x = max(0, min(self._frame_width - 1, x))
        return max(0, min(total_pixels - 1, (line * self._frame_width) + x))

    def _line_sample_x(self, line: int) -> int:
        if self._display_ystart <= line <= self._display_ystop and self._fetch_xstart >= 0:
            return self._fetch_xstart
        return 0

    def _foreground_event_for_cell(self, line: int, col: int) -> tuple[int, int, int, int, int, int, int, int] | None:
        events = self._foreground_events.get(line)
        if not events:
            return None
        selected = None
        for event in events:
            if event[0] > col:
                break
            if event[0] == col:
                selected = event
        return selected

    def _foreground_phase(self, pixel: int, half_flag: int) -> int:
        if half_flag:
            if pixel < 5:
                return 0
            if pixel < 7:
                return 1
            return 2
        if pixel < 1:
            return 0
        if pixel < 3:
            return 1
        return 2

    def _update_display_state(self) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0:
            self._display_xstart = -1
            self._display_xstop = -1
            self._fetch_xstart = -1
            self._fetch_xstop = -1
            self._display_ystart = -1
            self._display_ystop = -1
            self._area_state = self.AREA_IDLE
            return

        x0, y0, x1, y1 = self.visible_bounds(
            self._frame_width,
            self._frame_raster_lines,
            self.screen_columns(),
            self.screen_rows(),
        )
        self._display_xstart = x0
        self._display_xstop = max(x0, x1 - 1)
        self._fetch_xstart = min(self._display_xstop + 1, self._display_xstart + 16)
        self._fetch_xstop = self._display_xstop
        self._display_ystart = y0
        self._display_ystop = max(y0, y1 - 1)

        if self._raster_line < y0:
            self._area_state = self.AREA_IDLE
            return
        if self._raster_line > self._display_ystop:
            self._area_state = self.AREA_DONE
            return

        current_x = self.cycle_pixel_x(self.raster_cycle())
        if current_x < self._fetch_xstart:
            self._area_state = self.AREA_PENDING
        elif current_x <= self._fetch_xstop:
            self._area_state = self.AREA_DISPLAY
        else:
            self._area_state = self.AREA_DONE

    def _run_sound_cycles(self, cycles: int) -> None:
        for _ in range(cycles):
            mix = 0
            for channel in range(4):
                reg = self.registers[0x0A + channel]
                enabled = 1 if (reg & 0x80) else 0
                self._sound_counters[channel] -= 1
                if self._sound_counters[channel] <= 0:
                    period = (~reg) & 0x7F
                    if period == 0:
                        period = 0x80
                    reload_shift = (4, 3, 2, 1)[channel]
                    self._sound_counters[channel] += period << reload_shift
                    if channel != 3:
                        shift = self._sound_shift[channel] & 0xFF
                        shift = ((shift << 1) | ((((shift >> 7) ^ 0x01) & enabled))) & 0xFF
                        self._sound_shift[channel] = shift
                        self._sound_output[channel] = shift & 0x01
                    else:
                        edge_trigger = (self._noise_lfsr & 0x01) and (not self._noise_lfsr0_old)
                        if edge_trigger:
                            shift = self._sound_shift[channel] & 0xFF
                            shift = ((shift << 1) | ((((shift >> 7) ^ 0x01) & enabled))) & 0xFF
                            self._sound_shift[channel] = shift
                        bit3 = (self._noise_lfsr >> 3) & 0x01
                        bit12 = (self._noise_lfsr >> 12) & 0x01
                        bit14 = (self._noise_lfsr >> 14) & 0x01
                        bit15 = (self._noise_lfsr >> 15) & 0x01
                        gate1 = bit3 ^ bit12
                        gate2 = bit14 ^ bit15
                        gate3 = (gate1 ^ gate2) ^ 0x01
                        gate4 = (gate3 & enabled) ^ 0x01
                        self._noise_lfsr0_old = self._noise_lfsr & 0x01
                        self._noise_lfsr = ((self._noise_lfsr << 1) | gate4) & 0xFFFF
                        self._sound_output[channel] = self._sound_shift[channel] & enabled

                mix += 1 if (enabled and self._sound_output[channel]) else 0

            self._sound_accum += float(mix)
            self._sound_accum_cycles += 1
            self._sound_sample_clock += 1.0
            if self._sound_sample_clock >= self._cycles_per_sample:
                self._sound_sample_clock -= self._cycles_per_sample
                self._emit_sound_sample()

    def _emit_sound_sample(self) -> None:
        if self._sound_accum_cycles <= 0:
            self._frame_samples.append(0)
            return
        volume = self.registers[0x0E] & 0x0F
        if volume:
            level = ((self._sound_accum * 7.0) / float(self._sound_accum_cycles)) + 1.0
            target = (level * volume / float(self._MAX_OUTPUT_LEVEL)) * 28000.0
            self._highpassbuf += self._highpassbeta * (self._lowpassbuf - self._highpassbuf)
            self._lowpassbuf += self._lowpassbeta * (target - self._lowpassbuf)
            sample = int(self._lowpassbuf - self._highpassbuf)
        else:
            self._highpassbuf += self._highpassbeta * (self._lowpassbuf - self._highpassbuf)
            self._lowpassbuf += self._lowpassbeta * (0.0 - self._lowpassbuf)
            sample = int(self._lowpassbuf - self._highpassbuf)
        if sample < -32768:
            sample = -32768
        elif sample > 32767:
            sample = 32767
        self._frame_samples.append(sample)
        self._sound_accum = 0.0
        self._sound_accum_cycles = 0
