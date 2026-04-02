# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from __future__ import annotations

# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from __future__ import annotations

from array import array

from multiemu.state_codec import read_state_fields, write_state_fields


class VIC6560:
    """Canonical VIC-I implementation for VIC-20 NTSC."""

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

    AREA_IDLE = 0
    AREA_PENDING = 1
    AREA_DISPLAY = 2
    AREA_DONE = 3
    FETCH_IDLE = 0
    FETCH_START = 1
    FETCH_MATRIX = 2
    FETCH_CHARGEN = 3
    FETCH_DONE = 4
    _AREA_STATE_NAMES = ("idle", "pending", "display", "done")
    _FETCH_STATE_NAMES = ("idle", "start", "matrix", "chargen", "done")
    _MAX_OUTPUT_LEVEL = 29 * 15
    _NTSC_FIRST_DISPLAYED_LINE = 28
    _NTSC_LEFT_BORDER_WIDTH = 4
    _PAL_FIRST_DISPLAYED_LINE = 28
    _PAL_LEFT_BORDER_WIDTH = 12

    def __init__(self, *, sample_rate: int = 44100, cycles_per_second: int = 1_105_920):
        self.registers = bytearray(self.DEFAULT_REGISTERS)
        self.sample_rate = max(1, int(sample_rate))
        self.cycles_per_second = max(1, int(cycles_per_second))
        self._raster_line = 0
        self._raster_cycle = 0
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
        self._visible_raster_start = 0
        self._visible_raster_lines = 0
        self._area_state = self.AREA_IDLE
        self._fetch_state = self.FETCH_IDLE
        self._buf_offset = 0
        self._pending_text_cols = self.screen_columns()
        self._text_cols = self.screen_columns()
        self._text_lines = self.screen_rows()
        self._row_increase_line = self.char_height()
        self._ycounter = 0
        self._row_counter = 0
        self._memptr = 0
        self._memptr_inc = 0
        self._pending_memptr_update = 0
        self._blank_this_line = 1
        self._line_was_blank = 1
        self._vbuf = 0
        self._frame_fetch_cells = []
        self._frame_fetch_contexts = []
        self._completed_frame_fetch_cells = []
        self._completed_frame_fetch_contexts = []
        self._latched_reg0 = self.registers[0x00]
        self._latched_reg1 = self.registers[0x01]
        self._latched_screen_columns = self.screen_columns()
        self._latched_screen_rows = self.screen_rows()
        self._latched_char_height = self.char_height()
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
        self._cycles_per_sample = self.cycles_per_second / float(self.sample_rate)
        self._frame_samples = array("h")
        self._fetch_char_rom = None
        self._fetch_bus = None
        self._fetch_open_bus_data = 0xFF
        self._fetch_open_bus_high = 0x0F
        dt = 1.0 / float(self.sample_rate)
        self._lowpassbuf = 0.0
        self._highpassbuf = 0.0
        self._lowpassbeta = dt / (dt + 1e-4)
        self._highpassbeta = dt / (dt + 1e-3)

    def reset(self) -> None:
        self.registers[:] = self.DEFAULT_REGISTERS
        self._raster_line = 0
        self._raster_cycle = 0
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
        self._visible_raster_start = 0
        self._visible_raster_lines = 0
        self._area_state = self.AREA_IDLE
        self._fetch_state = self.FETCH_IDLE
        self._buf_offset = 0
        self._pending_text_cols = self.screen_columns()
        self._text_cols = self.screen_columns()
        self._text_lines = self.screen_rows()
        self._row_increase_line = self.char_height()
        self._ycounter = 0
        self._row_counter = 0
        self._memptr = 0
        self._memptr_inc = 0
        self._pending_memptr_update = 0
        self._blank_this_line = 1
        self._line_was_blank = 1
        self._vbuf = 0
        self._frame_fetch_cells = []
        self._frame_fetch_contexts = []
        self._completed_frame_fetch_cells = []
        self._completed_frame_fetch_contexts = []
        self._latched_reg0 = self.registers[0x00]
        self._latched_reg1 = self.registers[0x01]
        self._latched_screen_columns = self.screen_columns()
        self._latched_screen_rows = self.screen_rows()
        self._latched_char_height = self.char_height()
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
        self._fetch_open_bus_data = 0xFF
        self._fetch_open_bus_high = 0x0F
        self._lowpassbuf = 0.0
        self._highpassbuf = 0.0

    def configure_fetch_sources(self, *, char_rom, bus) -> None:
        self._fetch_char_rom = char_rom
        self._fetch_bus = bus

    def _serialize_nested_rows(self, rows) -> list:
        serialized = []
        for row in rows:
            if row is None:
                serialized.append(None)
                continue
            serialized.append([None if item is None else list(item) for item in row])
        return serialized

    def _restore_nested_rows(self, rows) -> list:
        restored = []
        for row in rows:
            if row is None:
                restored.append(None)
                continue
            restored.append([None if item is None else tuple(item) for item in row])
        return restored

    def read_state(self) -> dict:
        state = read_state_fields(
            self,
            scalar_fields=(
                "sample_rate",
                "cycles_per_second",
                "_raster_line",
                "_raster_cycle",
                "_cycles_into_frame",
                "_frame_raster_lines",
                "_frame_width",
                "_cycles_per_frame",
                "_display_xstart",
                "_display_xstop",
                "_fetch_xstart",
                "_fetch_xstop",
                "_display_ystart",
                "_display_ystop",
                "_visible_raster_start",
                "_visible_raster_lines",
                "_area_state",
                "_fetch_state",
                "_buf_offset",
                "_pending_text_cols",
                "_text_cols",
                "_text_lines",
                "_row_increase_line",
                "_ycounter",
                "_row_counter",
                "_memptr",
                "_memptr_inc",
                "_pending_memptr_update",
                "_blank_this_line",
                "_line_was_blank",
                "_vbuf",
                "_latched_reg0",
                "_latched_reg1",
                "_latched_screen_columns",
                "_latched_screen_rows",
                "_latched_char_height",
                "_sound_counters",
                "_sound_shift",
                "_sound_output",
                "_noise_lfsr",
                "_noise_lfsr0_old",
                "_sound_accum",
                "_sound_accum_cycles",
                "_sound_sample_clock",
                "_fetch_open_bus_data",
                "_fetch_open_bus_high",
                "_lowpassbuf",
                "_highpassbuf",
                "_lowpassbeta",
                "_highpassbeta",
            ),
            byte_fields=["registers"],
            array_fields=["_frame_samples"],
            meta={"type": "VIC6560"},
        )
        state["aux_events"] = [list(event) for event in self._aux_events]
        state["bg_events"] = [list(event) for event in self._bg_events]
        state["reverse_events"] = [list(event) for event in self._reverse_events]
        state["foreground_events"] = [
            [int(key), [list(event) for event in value]]
            for key, value in sorted(self._foreground_events.items())
        ]
        state["frame_fetch_cells"] = self._serialize_nested_rows(self._frame_fetch_cells)
        state["frame_fetch_contexts"] = self._serialize_nested_rows(self._frame_fetch_contexts)
        state["completed_frame_fetch_cells"] = self._serialize_nested_rows(self._completed_frame_fetch_cells)
        state["completed_frame_fetch_contexts"] = self._serialize_nested_rows(self._completed_frame_fetch_contexts)
        return state

    def write_state(self, state: dict) -> None:
        write_state_fields(
            self,
            state,
            scalar_fields=(
                "sample_rate",
                "cycles_per_second",
                "_raster_line",
                "_raster_cycle",
                "_cycles_into_frame",
                "_frame_raster_lines",
                "_frame_width",
                "_cycles_per_frame",
                "_display_xstart",
                "_display_xstop",
                "_fetch_xstart",
                "_fetch_xstop",
                "_display_ystart",
                "_display_ystop",
                "_visible_raster_start",
                "_visible_raster_lines",
                "_area_state",
                "_fetch_state",
                "_buf_offset",
                "_pending_text_cols",
                "_text_cols",
                "_text_lines",
                "_row_increase_line",
                "_ycounter",
                "_row_counter",
                "_memptr",
                "_memptr_inc",
                "_pending_memptr_update",
                "_blank_this_line",
                "_line_was_blank",
                "_vbuf",
                "_latched_reg0",
                "_latched_reg1",
                "_latched_screen_columns",
                "_latched_screen_rows",
                "_latched_char_height",
                "_sound_counters",
                "_sound_shift",
                "_sound_output",
                "_noise_lfsr",
                "_noise_lfsr0_old",
                "_sound_accum",
                "_sound_accum_cycles",
                "_sound_sample_clock",
                "_fetch_open_bus_data",
                "_fetch_open_bus_high",
                "_lowpassbuf",
                "_highpassbuf",
                "_lowpassbeta",
                "_highpassbeta",
            ),
            byte_fields=["registers"],
            array_fields=["_frame_samples"],
        )
        self._aux_events = [tuple(event) for event in state.get("aux_events", [])]
        self._bg_events = [tuple(event) for event in state.get("bg_events", [])]
        self._reverse_events = [tuple(event) for event in state.get("reverse_events", [])]
        self._foreground_events = {
            int(key): [tuple(event) for event in events]
            for key, events in state.get("foreground_events", [])
        }
        self._frame_fetch_cells = self._restore_nested_rows(state.get("frame_fetch_cells", []))
        self._frame_fetch_contexts = self._restore_nested_rows(state.get("frame_fetch_contexts", []))
        self._completed_frame_fetch_cells = self._restore_nested_rows(state.get("completed_frame_fetch_cells", []))
        self._completed_frame_fetch_contexts = self._restore_nested_rows(state.get("completed_frame_fetch_contexts", []))

    def read(self, addr: int) -> int:
        reg = addr & 0x0F
        if reg == 0x03:
            return (self.registers[0x03] & 0x7F) | (((self._raster_line & 0x01) << 7) & 0x80)
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

    def begin_frame(
        self,
        raster_lines: int,
        frame_width: int,
        cycles_per_frame: int,
        *,
        visible_line_start: int = 0,
        visible_line_count: int | None = None,
    ) -> None:
        self._cycles_into_frame = 0
        self._raster_line = 0
        self._raster_cycle = 0
        self._frame_raster_lines = max(1, raster_lines)
        self._frame_width = max(1, frame_width)
        self._cycles_per_frame = max(1, cycles_per_frame)
        self._display_xstart = -1
        self._display_xstop = -1
        self._fetch_xstart = -1
        self._fetch_xstop = -1
        self._display_ystart = -1
        self._display_ystop = -1
        self._visible_raster_start = max(0, int(visible_line_start))
        if visible_line_count is None:
            self._visible_raster_lines = self._frame_raster_lines
        else:
            self._visible_raster_lines = max(1, int(visible_line_count))
        self._area_state = self.AREA_IDLE
        self._fetch_state = self.FETCH_IDLE
        self._buf_offset = 0
        self._pending_text_cols = self._latched_screen_columns
        self._text_cols = self._latched_screen_columns
        self._text_lines = self._latched_screen_rows
        self._row_increase_line = self._latched_char_height
        self._ycounter = 0
        self._row_counter = 0
        self._memptr = 0
        self._memptr_inc = 0
        self._pending_memptr_update = 0
        self._blank_this_line = 1
        self._line_was_blank = 1
        self._vbuf = 0
        self._frame_fetch_cells = [None] * self._visible_raster_lines
        self._frame_fetch_contexts = [None] * self._visible_raster_lines
        self._completed_frame_fetch_cells = []
        self._completed_frame_fetch_contexts = []
        self._latched_reg0 = self.registers[0x00]
        self._latched_reg1 = self.registers[0x01]
        self._latched_screen_columns = self.screen_columns()
        self._latched_screen_rows = self.screen_rows()
        self._latched_char_height = self.char_height()
        reg_e = self.registers[0x0E]
        reg_f = self.registers[0x0F]
        self._aux_events = [(0, (reg_e >> 4) & 0x0F)]
        self._bg_events = [(0, (reg_f >> 4) & 0x0F, reg_f & 0x07)]
        self._reverse_events = [(0, 1 if (reg_f & 0x08) == 0 else 0)]
        self._foreground_events = {}
        self._frame_samples = array("h")

    def run_cycles(
        self,
        cycles: int,
        *,
        cycles_per_frame: int,
        raster_lines: int,
        fetch_read=None,
        color_read=None,
    ) -> None:
        if cycles <= 0 or cycles_per_frame <= 0 or raster_lines <= 0:
            return
        self._frame_raster_lines = raster_lines
        self._cycles_per_frame = cycles_per_frame
        for _ in range(cycles):
            self._advance_cycle(fetch_read, color_read)
        self._run_sound_cycles(cycles)

    def _fetch_color_direct(self, addr: int) -> int:
        if self._fetch_bus is None:
            return self._fetch_open_bus_high & 0x0F
        color = self._fetch_bus.read8(addr) & 0x0F
        self._fetch_open_bus_high = color
        return color

    def _fetch_byte_direct(self, addr: int) -> int:
        cdef int value
        if 0x8000 <= addr < 0x9000 and self._fetch_char_rom is not None:
            value = self._fetch_char_rom.read((addr - 0x8000) & 0x0FFF)
        elif (0x0000 <= addr < 0x0400) or (0x1000 <= addr < 0x2000):
            if self._fetch_bus is None:
                value = 0xFF
            else:
                value = self._fetch_bus.read8(addr & 0x1FFF)
        elif 0x9400 <= addr < 0x9800:
            if self._fetch_bus is None:
                value = self._fetch_open_bus_high & 0x0F
            else:
                value = self._fetch_bus.read8(addr)
        else:
            value = self._fetch_open_bus_data & (0xF0 | self._fetch_open_bus_high)
        self._fetch_open_bus_data = value & 0xFF
        return value & 0xFF

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
        return self._horizontal_offset(frame_width, screen_columns, self.registers[0x00])

    def _horizontal_offset(self, frame_width: int, screen_columns: int, reg0: int) -> int:
        visible_width = screen_columns * 8
        margin = max(0, frame_width - visible_width)
        requested = ((reg0 & 0x7F) * 4) - (self._left_border_width() * 4)
        return max(0, min(margin, requested))

    def vertical_offset(self, frame_height: int, screen_rows: int) -> int:
        return self._vertical_offset(frame_height, screen_rows, self.registers[0x01])

    def _vertical_offset(self, frame_height: int, screen_rows: int, reg1: int) -> int:
        visible_height = screen_rows * self._display_char_height()
        margin = max(0, frame_height - visible_height)
        requested = ((reg1 & 0xFF) * 2) - self._first_displayed_line()
        return max(0, min(margin, requested))

    def _first_displayed_line(self) -> int:
        if self._frame_raster_lines >= 300:
            return self._PAL_FIRST_DISPLAYED_LINE
        return self._NTSC_FIRST_DISPLAYED_LINE

    def _left_border_width(self) -> int:
        if self._frame_raster_lines >= 300:
            return self._PAL_LEFT_BORDER_WIDTH
        return self._NTSC_LEFT_BORDER_WIDTH

    def visible_width(self, screen_columns: int) -> int:
        return max(0, screen_columns * 8)

    def visible_height(self, screen_rows: int) -> int:
        return max(0, screen_rows * self.char_height())

    def _display_char_height(self) -> int:
        if self._cycles_per_frame <= 0 or self._frame_width <= 0:
            return self.char_height()
        return 16 if int(self._latched_char_height) > 8 else 8

    def visible_bounds(self, frame_width: int, frame_height: int, screen_columns: int, screen_rows: int) -> tuple[int, int, int, int]:
        return self._visible_bounds(frame_width, frame_height, screen_columns, screen_rows, self.registers[0x00], self.registers[0x01])

    def _visible_bounds(
        self,
        frame_width: int,
        frame_height: int,
        screen_columns: int,
        screen_rows: int,
        reg0: int,
        reg1: int,
    ) -> tuple[int, int, int, int]:
        x0 = self._horizontal_offset(frame_width, screen_columns, reg0)
        y0 = self._vertical_offset(frame_height, screen_rows, reg1)
        return (
            x0,
            y0,
            x0 + self.visible_width(screen_columns),
            y0 + max(0, screen_rows * self._display_char_height()),
        )

    def cell_origin(self, row: int, col: int, frame_width: int, frame_height: int) -> tuple[int, int]:
        screen_columns = self._display_screen_columns()
        screen_rows = self._display_screen_rows()
        x0, y0, _, _ = self._visible_bounds(
            frame_width,
            frame_height,
            screen_columns,
            screen_rows,
            self._display_reg0(),
            self._display_reg1(),
        )
        return x0 + (max(0, col) * 8), y0 + (max(0, row) * self._display_char_height())

    def display_cell_at_position(
        self,
        x: int,
        y: int,
        frame_width: int,
        frame_height: int,
    ) -> tuple[int, int, int, int] | None:
        screen_columns = self._display_screen_columns()
        screen_rows = self._display_screen_rows()
        x0, y0, x1, y1 = self._visible_bounds(
            frame_width,
            frame_height,
            screen_columns,
            screen_rows,
            self._display_reg0(),
            self._display_reg1(),
        )
        if self._fetch_xstart >= 0:
            x0 = self._fetch_xstart
        if self._fetch_xstop >= 0:
            x1 = self._fetch_xstop + 1
        if not (x0 <= x < x1 and y0 <= y < y1):
            return None
        rel_x = x - x0
        rel_y = y - y0
        col = rel_x // 8
        row = rel_y // self._display_char_height()
        if not (0 <= col < screen_columns and 0 <= row < screen_rows):
            return None
        return row, col, rel_x % 8, rel_y % self._display_char_height()

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
        screen_columns = self._display_screen_columns()
        screen_rows = self._display_screen_rows()
        if not (0 <= text_row < screen_rows):
            return []
        cells = []
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
        screen_columns = self._display_screen_columns()
        screen_rows = self._display_screen_rows()
        display_line_origin = max(0, (self._display_reg1() & 0xFF) - 22)
        _, visible_y0, _, _ = self._visible_bounds(
            frame_width,
            frame_height,
            screen_columns,
            screen_rows,
            self._display_reg0(),
            self._display_reg1(),
        )
        visible_index = (y - visible_y0) + display_line_origin
        source_cells = self._completed_frame_fetch_cells if self._completed_frame_fetch_cells else self._frame_fetch_cells
        if 0 <= visible_index < len(source_cells):
            buffered = source_cells[visible_index]
            if buffered is not None:
                if len(buffered) >= screen_columns and all(cell is not None for cell in buffered[:screen_columns]):
                    return list(buffered[:screen_columns])
            if self._completed_frame_fetch_cells:
                return []
        x0, _, x1, _ = self._visible_bounds(
            frame_width,
            frame_height,
            screen_columns,
            screen_rows,
            self._display_reg0(),
            self._display_reg1(),
        )
        fetch_x = self._fetch_xstart
        if fetch_x < 0:
            fetch_x = min(x1 - 1, x0 + 16)
        cell = self.display_cell_at_position(fetch_x, y, frame_width, frame_height)
        if cell is None:
            return []
        row, _, _, pixel_y = cell
        cells = []
        for col in range(screen_columns):
            cell_x, _ = self.cell_origin(row, col, frame_width, frame_height)
            screen_addr = self.screen_address_for_cell(row, col, screen_columns)
            color_addr = self.color_address_for_cell(row, col, screen_columns)
            cells.append((row, col, cell_x, pixel_y, screen_addr, color_addr))
        return cells

    def has_completed_fetch_buffers(self) -> bool:
        return bool(self._completed_frame_fetch_contexts)

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
        contexts = []
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

    def display_latched_contexts_for_scanline(
        self,
        y: int,
        frame_width: int,
        frame_height: int,
    ) -> list[tuple[int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int]]:
        cdef int screen_columns
        cdef int screen_rows
        cdef int visible_index
        cdef object buffered
        cdef list contexts
        cdef object cell
        cdef int row
        cdef int col
        cdef int cell_x
        cdef int pixel_y
        cdef int screen_addr
        cdef int color_addr
        cdef int screen_code
        cdef int color_nibble
        cdef int glyph_addr
        cdef int glyph_row_bits
        cdef int reg_e
        cdef int reg_f
        cdef int half_flag
        cdef int phase0_e
        cdef int phase0_f
        cdef int phase1_e
        cdef int phase1_f
        cdef int phase2_e
        cdef int phase2_f
        cdef int display_line_origin
        cdef bint effective_reverse
        cdef bint multicolor_mode

        screen_columns = self._display_screen_columns()
        screen_rows = self._display_screen_rows()
        display_line_origin = max(0, (self._display_reg1() & 0xFF) - 22)
        _, visible_y0, _, _ = self._visible_bounds(
            frame_width,
            frame_height,
            screen_columns,
            screen_rows,
            self._display_reg0(),
            self._display_reg1(),
        )
        visible_index = (y - visible_y0) + display_line_origin
        if visible_index < 0 or visible_index >= len(self._frame_fetch_contexts):
            return []
        source_contexts = (
            self._completed_frame_fetch_contexts
            if self._completed_frame_fetch_contexts
            else self._frame_fetch_contexts
        )
        buffered = source_contexts[visible_index]
        if buffered is None:
            return []

        contexts = []
        for cell in buffered:
            if cell is None:
                continue
            row = cell[0]
            col = cell[1]
            cell_x = cell[2]
            pixel_y = cell[3]
            screen_addr = cell[4]
            color_addr = cell[5]
            screen_code = cell[6]
            color_nibble = cell[7]
            glyph_addr = cell[8]
            glyph_row_bits = cell[9]
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
                return color_nibble & 0x07
            return (reg_e >> 4) & 0x0F

        row_bits = glyph_bits ^ 0xFF if effective_reverse else glyph_bits
        pixel_on = (row_bits & (0x80 >> (pixel_x & 0x07))) != 0
        return (color_nibble & 0x07) if pixel_on else bg

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
        return self._AREA_STATE_NAMES[self._area_state]

    def fetch_state(self) -> str:
        return self._FETCH_STATE_NAMES[self._fetch_state]

    def border_color_index_for_line(self, line: int) -> int:
        _, reg_f = self._color_regs_for_position(line, 0)
        return reg_f & 0x07

    def screen_color_index_for_line(self, line: int) -> int:
        _, reg_f = self._color_regs_for_position(line, self._line_sample_x(line))
        return (reg_f >> 4) & 0x0F

    def bg_border_spans_for_line(self, line: int, width: int) -> list[tuple[int, int, int, int]]:
        cdef int clamped_width = max(0, int(width))
        cdef int current_bg
        cdef int current_border
        cdef int event_index
        cdef int event_bg
        cdef int event_border
        cdef int event_line
        cdef int event_x
        cdef int start_x
        cdef list spans = []

        if clamped_width <= 0:
            return spans

        if self._bg_events:
            current_bg = self._bg_events[0][1]
            current_border = self._bg_events[0][2]
        else:
            current_bg = (self.registers[0x0F] >> 4) & 0x0F
            current_border = self.registers[0x0F] & 0x07

        start_x = 0
        for event_index, event_bg, event_border in self._bg_events:
            event_line = event_index // self._frame_width
            if event_line < line:
                current_bg = event_bg
                current_border = event_border
                continue
            if event_line > line:
                break
            event_x = event_index % self._frame_width
            event_x = max(0, min(clamped_width, event_x))
            if event_x > start_x:
                spans.append((start_x, event_x, current_bg, current_border))
            current_bg = event_bg
            current_border = event_border
            start_x = event_x
        if start_x < clamped_width:
            spans.append((start_x, clamped_width, current_bg, current_border))
        return spans

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

    def _display_reg0(self) -> int:
        if self._cycles_per_frame <= 0 or self._frame_width <= 0:
            return self.registers[0x00] & 0xFF
        return self._latched_reg0 & 0xFF

    def _display_reg1(self) -> int:
        if self._cycles_per_frame <= 0 or self._frame_width <= 0:
            return self.registers[0x01] & 0xFF
        return self._latched_reg1 & 0xFF

    def _display_screen_columns(self) -> int:
        if self._cycles_per_frame <= 0 or self._frame_width <= 0:
            return self.screen_columns()
        return max(1, int(self._latched_screen_columns))

    def _display_screen_rows(self) -> int:
        if self._cycles_per_frame <= 0 or self._frame_width <= 0:
            return self.screen_rows()
        return max(1, int(self._latched_screen_rows))

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

        event_col, half_flag, old_aux, new_aux, old_border, new_border, old_reverse, new_reverse = event
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
        if col > event_col:
            return 0, phase2_e, phase2_f, phase2_e, phase2_f, phase2_e, phase2_f
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
        for event_index, event_bg, event_border in self._bg_events:
            if event_index > pixel_index:
                break
            bg_color = event_bg
            border_color = event_border
        if self.is_display_position(clamped_line, clamped_x):
            for event_index, event_aux in self._aux_events:
                if event_index > pixel_index:
                    break
                aux_color = event_aux
            for event_index, event_reverse in self._reverse_events:
                if event_index > pixel_index:
                    break
                reverse_enabled = bool(event_reverse)
        return aux_color, bg_color, border_color, reverse_enabled

    def _stamp_aux_change(self) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        pixel_index = self._color_event_pixel_index(0)
        event = (pixel_index, (self.registers[0x0E] >> 4) & 0x0F)
        if self._aux_events and self._aux_events[len(self._aux_events) - 1][0] == pixel_index:
            self._aux_events[len(self._aux_events) - 1] = event
            return
        self._aux_events.append(event)

    def _stamp_bg_border_change(self) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        pixel_index = self._background_event_pixel_index(0)
        reg_f = self.registers[0x0F]
        event = (pixel_index, (reg_f >> 4) & 0x0F, reg_f & 0x07)
        if self._bg_events and self._bg_events[len(self._bg_events) - 1][0] == pixel_index:
            self._bg_events[len(self._bg_events) - 1] = event
            return
        self._bg_events.append(event)

    def _stamp_reverse_change(self) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        pixel_index = self._color_event_pixel_index(2)
        event = (pixel_index, 1 if (self.registers[0x0F] & 0x08) == 0 else 0)
        if self._reverse_events and self._reverse_events[len(self._reverse_events) - 1][0] == pixel_index:
            self._reverse_events[len(self._reverse_events) - 1] = event
            return
        self._reverse_events.append(event)

    def _stamp_foreground_change(self, old_reg_e: int, old_reg_f: int) -> None:
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return
        if self._fetch_xstart < 0 or self._display_ystart < 0:
            return

        line = self._raster_line - self._visible_raster_start
        cdef int cycles_per_line = self.cycles_per_line()
        cdef int event_cycle = (self._cycles_into_frame % cycles_per_line) + 1
        if event_cycle >= cycles_per_line:
            event_cycle -= cycles_per_line
            line += 1
        if line < 0 or line >= self._visible_raster_lines:
            return
        if not (self._display_ystart <= line <= self._display_ystop):
            return

        char_index = self._raster_char_int(event_cycle)
        half_flag = self._raster_char_frac(event_cycle)
        if char_index < 0 or char_index >= self._text_cols:
            return
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
        if events and events[len(events) - 1][0] == char_index:
            events[len(events) - 1] = event
            return
        events.append(event)

    def _current_pixel_index(self, x_bias: int) -> int:
        cycles_per_line = self.cycles_per_line()
        total_pixels = self._frame_width * self._frame_raster_lines
        visible_line = self._raster_line - self._visible_raster_start
        if visible_line < 0:
            line = 0
        elif visible_line >= self._visible_raster_lines:
            return total_pixels
        else:
            line = max(0, min(self._frame_raster_lines - 1, visible_line))
        cycles_into_line = self._cycles_into_frame % cycles_per_line
        x = self.cycle_pixel_x(cycles_into_line) + x_bias
        x = max(0, min(self._frame_width - 1, x))
        return max(0, min(total_pixels - 1, (line * self._frame_width) + x))

    def _color_event_pixel_index(self, x_bias: int) -> int:
        cdef int cycles_per_line = self.cycles_per_line()
        cdef int total_pixels = self._frame_width * self._frame_raster_lines
        cdef int visible_line = self._raster_line - self._visible_raster_start
        cdef int cycles_into_line
        cdef int event_cycle
        cdef int raw_x
        cdef int next_line
        cdef int line_start

        if visible_line < 0:
            return 0
        if visible_line >= self._visible_raster_lines:
            return total_pixels

        cycles_into_line = self._cycles_into_frame % cycles_per_line
        event_cycle = cycles_into_line + 1
        if event_cycle >= cycles_per_line:
            event_cycle -= cycles_per_line
            visible_line += 1
            if visible_line >= self._visible_raster_lines:
                return total_pixels
        raw_x = ((4 * event_cycle) - 27) + x_bias
        line_start = visible_line * self._frame_width

        if visible_line < self._display_ystart or visible_line > self._display_ystop:
            if raw_x <= 0:
                return max(0, min(total_pixels - 1, line_start))
            if raw_x >= self._frame_width:
                next_line = visible_line + 1
                if next_line >= self._visible_raster_lines:
                    return total_pixels
                return max(0, min(total_pixels - 1, next_line * self._frame_width))
            return max(0, min(total_pixels - 1, line_start + raw_x))

        if raw_x < self._display_xstart:
            return max(0, min(total_pixels - 1, (visible_line * self._frame_width) + self._display_xstart))

        if raw_x > self._display_xstop:
            next_line = visible_line + 1
            if next_line > self._display_ystop:
                return total_pixels
            return max(0, min(total_pixels - 1, (next_line * self._frame_width) + self._display_xstart))

        return self._current_pixel_index(x_bias)

    def _background_event_pixel_index(self, x_bias: int) -> int:
        cdef int cycles_per_line = self.cycles_per_line()
        cdef int total_pixels = self._frame_width * self._frame_raster_lines
        cdef int visible_line = self._raster_line - self._visible_raster_start
        cdef int cycles_into_line
        cdef int event_cycle
        cdef int raw_x
        cdef int next_line

        if visible_line < 0:
            return 0
        if visible_line >= self._visible_raster_lines:
            return total_pixels

        cycles_into_line = self._cycles_into_frame % cycles_per_line
        event_cycle = cycles_into_line + 1
        if event_cycle >= cycles_per_line:
            event_cycle -= cycles_per_line
            visible_line += 1
            if visible_line >= self._visible_raster_lines:
                return total_pixels

        if self._area_state == self.AREA_DISPLAY and self._fetch_state in (self.FETCH_DONE, self.FETCH_IDLE):
            visible_line += 1
            if visible_line >= self._visible_raster_lines:
                return total_pixels
            return visible_line * self._frame_width

        raw_x = ((4 * event_cycle) - 27) + x_bias + 1
        if raw_x < 0:
            raw_x = 0
        if raw_x >= self._frame_width:
            next_line = visible_line + 1
            if next_line >= self._visible_raster_lines:
                return total_pixels
            return next_line * self._frame_width

        return (visible_line * self._frame_width) + raw_x

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

    def _raster_char_int(self, cycle: int) -> int:
        cdef int base = int(self._display_xstart / 4)
        cdef int numer = int(cycle) - base - 7
        if numer >= 0:
            return numer // 2
        return -((-numer) // 2)

    def _raster_char_frac(self, cycle: int) -> int:
        cdef int base = int(self._display_xstart / 4)
        cdef int numer = int(cycle) - base - 7
        cdef int frac = numer % 2
        if frac < 0:
            frac += 2
        return frac

    def _update_display_state(self) -> None:
        return

    def _visible_line(self) -> int:
        return self._raster_line - self._visible_raster_start

    def _visible_line_raster(self) -> int:
        if self._visible_raster_lines <= 0:
            return 0
        visible_line = self._visible_line()
        if visible_line < 0:
            return 0
        if visible_line >= self._visible_raster_lines:
            return self._visible_raster_lines - 1
        return visible_line

    def _nominal_visible_bounds(self) -> tuple[int, int, int, int]:
        return self._visible_bounds(
            self._frame_width,
            self._visible_raster_lines,
            self._display_screen_columns(),
            self._display_screen_rows(),
            self._display_reg0(),
            self._display_reg1(),
        )

    def _open_v(self) -> None:
        visible_line = self._visible_line_raster()
        x0, y0, x1, y1 = self._nominal_visible_bounds()
        self._area_state = self.AREA_PENDING
        self._display_xstart = x0
        self._display_xstop = max(x0, x1 - 1)
        self._fetch_xstart = min(self._display_xstop + 1, self._display_xstart + 16)
        self._fetch_xstop = self._display_xstop
        self._display_ystart = visible_line
        self._row_counter = 0
        self._ycounter = 0
        if self._text_lines <= 0:
            self._close_v()
        else:
            self._display_ystop = max(visible_line, y1 - 1)

    def _close_v(self) -> None:
        visible_line = self._visible_line_raster()
        self._area_state = self.AREA_DONE
        self._display_ystop = visible_line
        if self._fetch_state != self.FETCH_IDLE:
            self._display_ystop += 1

    def _open_h(self) -> None:
        self._fetch_state = self.FETCH_START
        self._buf_offset = 4
        if self._area_state == self.AREA_PENDING:
            self._area_state = self.AREA_DISPLAY
        self._memptr_inc = 0
        self._text_cols = self._pending_text_cols

    def _close_h(self) -> None:
        self._fetch_state = self.FETCH_DONE

    def _start_fetch(self) -> None:
        self._fetch_xstart = min(self._display_xstop + 1, self._display_xstart + 16)
        self._fetch_xstop = self._display_xstop
        if self._text_cols > 0:
            self._blank_this_line = 0
            self._fetch_state = self.FETCH_MATRIX
        else:
            self._close_h()

    def _handle_memptr(self) -> None:
        if self._row_increase_line == self._ycounter or 2 * self._row_increase_line == self._ycounter:
            self._ycounter = 0
            self._memptr_inc = 0 if self._line_was_blank else self._text_cols
            self._row_counter += 1
            if self._row_counter == self._text_lines:
                self._close_v()
        self._memptr += self._memptr_inc
        self._memptr_inc = 0

    def _end_of_line(self) -> None:
        self._line_was_blank = self._blank_this_line
        if self._area_state == self.AREA_DISPLAY:
            self._ycounter += 1
            self._pending_memptr_update = 1
        self._fetch_state = self.FETCH_IDLE
        self._blank_this_line = 1
        self._raster_cycle = 0
        self._raster_line += 1
        if self._area_state in (self.AREA_PENDING, self.AREA_DISPLAY):
            if self._display_ystop >= 0 and self._visible_line() > self._display_ystop:
                self._close_v()
        if self._raster_line >= self._frame_raster_lines:
            self._end_of_frame()

    def _end_of_frame(self) -> None:
        if self._area_state != self.AREA_DONE:
            self._close_v()
            self._display_ystop = self._visible_line() - 1
        self._completed_frame_fetch_cells = self._frame_fetch_cells
        self._completed_frame_fetch_contexts = self._frame_fetch_contexts
        self._raster_line = 0
        self._area_state = self.AREA_IDLE
        self._fetch_state = self.FETCH_IDLE
        self._display_xstart = -1
        self._display_xstop = -1
        self._fetch_xstart = -1
        self._fetch_xstop = -1
        self._display_ystart = -1
        self._display_ystop = -1
        self._ycounter = 0
        self._row_counter = 0
        self._memptr = 0
        self._memptr_inc = 0
        self._pending_memptr_update = 0
        self._blank_this_line = 1
        self._line_was_blank = 1
        self._vbuf = 0

    def _fix_addr(self, addr: int) -> int:
        msb = (~((addr & 0x2000) << 2)) & 0x8000
        return (addr & 0x1FFF) | msb

    def _record_matrix_fetch(self) -> None:
        cdef int visible_line
        cdef int addr
        cdef int screen_addr
        cdef int color_addr
        cdef int row
        cdef int col
        cdef int cell_x
        cdef int pixel_y
        cdef object buffered
        cdef object buffered_contexts

        visible_line = self._visible_line()
        if visible_line < 0 or visible_line >= len(self._frame_fetch_cells):
            return
        if self._buf_offset < 0 or self._buf_offset >= self._text_cols:
            return

        addr = (((self.registers[0x05] & 0xF0) << 6) | ((self.registers[0x02] & 0x80) << 2)) + (self._memptr + self._buf_offset)
        screen_addr = self._fix_addr(addr)
        color_addr = 0x9400 + (addr & 0x03FF)
        row = self._row_counter
        col = self._buf_offset
        cell_x = max(0, self._display_xstart) + (col * 8)
        pixel_y = self._ycounter & (((self._row_increase_line >> 1) | 7))

        buffered = self._frame_fetch_cells[visible_line]
        if buffered is None or len(buffered) < self._text_cols:
            buffered = [None] * self._text_cols
            self._frame_fetch_cells[visible_line] = buffered
        if buffered[col] is None:
            buffered[col] = [row, col, cell_x, pixel_y, screen_addr, color_addr]
        else:
            buffered[col][0] = row
            buffered[col][1] = col
            buffered[col][2] = cell_x
            buffered[col][3] = pixel_y
            buffered[col][4] = screen_addr
            buffered[col][5] = color_addr
        buffered_contexts = self._frame_fetch_contexts[visible_line]
        if buffered_contexts is None or len(buffered_contexts) < self._text_cols:
            buffered_contexts = [None] * self._text_cols
            self._frame_fetch_contexts[visible_line] = buffered_contexts
        if buffered_contexts[col] is None:
            buffered_contexts[col] = [
                row,
                col,
                cell_x,
                pixel_y,
                screen_addr,
                color_addr,
                0,
                0,
                0,
                0,
            ]
        else:
            buffered_contexts[col][0] = row
            buffered_contexts[col][1] = col
            buffered_contexts[col][2] = cell_x
            buffered_contexts[col][3] = pixel_y
            buffered_contexts[col][4] = screen_addr
            buffered_contexts[col][5] = color_addr
            buffered_contexts[col][6] = 0
            buffered_contexts[col][7] = 0
            buffered_contexts[col][8] = 0
            buffered_contexts[col][9] = 0

    def _do_matrix_fetch(self, fetch_read, color_read) -> None:
        cdef int visible_line
        cdef int addr
        cdef int fixed_addr
        cdef int color_addr
        cdef int row
        cdef int col
        cdef int cell_x
        cdef int pixel_y
        cdef int screen_code
        cdef int color_nibble
        cdef object buffered

        self._record_matrix_fetch()
        if fetch_read is None:
            fetch_read = self._fetch_byte_direct
        if color_read is None:
            color_read = self._fetch_color_direct

        visible_line = self._visible_line()
        if visible_line < 0 or visible_line >= len(self._frame_fetch_contexts):
            return
        if self._buf_offset < 0 or self._buf_offset >= self._text_cols:
            return

        addr = (((self.registers[0x05] & 0xF0) << 6) | ((self.registers[0x02] & 0x80) << 2)) + (self._memptr + self._buf_offset)
        fixed_addr = self._fix_addr(addr)
        color_addr = 0x9400 + (addr & 0x03FF)
        screen_code = int(fetch_read(fixed_addr)) & 0xFF
        color_nibble = int(color_read(color_addr)) & 0x0F
        self._vbuf = screen_code

        buffered = self._frame_fetch_contexts[visible_line]
        if buffered is None:
            return
        row = self._row_counter
        col = self._buf_offset
        cell_x = max(0, self._display_xstart) + (col * 8)
        pixel_y = self._ycounter & (((self._row_increase_line >> 1) | 7))
        if buffered[col] is None:
            buffered[col] = [
                row,
                col,
                cell_x,
                pixel_y,
                fixed_addr,
                color_addr,
                screen_code,
                color_nibble,
                0,
                0,
            ]
        else:
            buffered[col][0] = row
            buffered[col][1] = col
            buffered[col][2] = cell_x
            buffered[col][3] = pixel_y
            buffered[col][4] = fixed_addr
            buffered[col][5] = color_addr
            buffered[col][6] = screen_code
            buffered[col][7] = color_nibble
            buffered[col][8] = 0
            buffered[col][9] = 0

    def _do_chargen_fetch(self, fetch_read, color_read) -> None:
        cdef int visible_line
        cdef int col
        cdef int char_addr
        cdef int fixed_char_addr
        cdef int color_addr
        cdef int glyph_byte
        cdef object buffered
        cdef object cell

        if fetch_read is None:
            fetch_read = self._fetch_byte_direct
        if color_read is None:
            color_read = self._fetch_color_direct
        visible_line = self._visible_line()
        if visible_line < 0 or visible_line >= len(self._frame_fetch_contexts):
            return
        col = self._buf_offset
        if col < 0 or col >= self._text_cols:
            return
        buffered = self._frame_fetch_contexts[visible_line]
        if buffered is None or buffered[col] is None:
            return
        cell = buffered[col]
        char_addr = ((self.registers[0x05] & 0x0F) << 10) + (
            (self._vbuf * self._row_increase_line)
            + (self._ycounter & (((self._row_increase_line >> 1) | 7)))
        )
        fixed_char_addr = self._fix_addr(char_addr)
        color_addr = 0x9400 + (fixed_char_addr & 0x03FF)
        glyph_byte = int(fetch_read(fixed_char_addr)) & 0xFF
        color_read(color_addr)
        buffered[col][8] = fixed_char_addr
        buffered[col][9] = glyph_byte

    def _advance_cycle(self, fetch_read=None, color_read=None) -> None:
        cdef int cycles_per_line
        cdef int area_state
        cdef int fetch_state
        cdef int reg0
        cdef int reg1
        cdef int reg2
        cdef int reg3
        cdef int visible_line
        if self._frame_width <= 0 or self._frame_raster_lines <= 0 or self._cycles_per_frame <= 0:
            return

        cycles_per_line = self._cycles_per_frame // self._frame_raster_lines
        if cycles_per_line <= 0:
            cycles_per_line = 1
        area_state = self._area_state
        fetch_state = self._fetch_state
        reg0 = self.registers[0x00]
        reg1 = self.registers[0x01]
        reg2 = self.registers[0x02]
        reg3 = self.registers[0x03]

        if self._pending_memptr_update and self._raster_cycle == 0 and area_state == self.AREA_DISPLAY:
            self._handle_memptr()
            self._pending_memptr_update = 0

        if area_state == self.AREA_IDLE:
            visible_line = self._raster_line - self._visible_raster_start
            if visible_line == max(0, reg1 - 22):
                self._open_v()
                area_state = self._area_state

        self._cycles_into_frame = (self._cycles_into_frame + 1) % self._cycles_per_frame
        self._raster_cycle += 1

        if self._raster_cycle == 1:
            self._pending_text_cols = min(reg2 & 0x7F, 32)
        if self._raster_line == 0 and self._raster_cycle == 2:
            self._text_lines = (reg3 & 0x7E) >> 1
            self._row_increase_line = 16 if (reg3 & 0x01) else 8

        if self._raster_cycle >= cycles_per_line:
            self._end_of_line()
            return

        if area_state == self.AREA_DISPLAY or area_state == self.AREA_PENDING:
            if fetch_state == self.FETCH_IDLE and (reg0 & 0x7F) == self._raster_cycle:
                self._open_h()
                fetch_state = self._fetch_state
                area_state = self._area_state

        if fetch_state == self.FETCH_START:
            self._buf_offset -= 1
            if self._buf_offset == 0:
                self._start_fetch()
                fetch_state = self._fetch_state
        elif fetch_state == self.FETCH_MATRIX:
            self._do_matrix_fetch(fetch_read, color_read)
            self._fetch_state = self.FETCH_CHARGEN
        elif fetch_state == self.FETCH_CHARGEN:
            self._do_chargen_fetch(fetch_read, color_read)
            self._buf_offset += 1
            if self._ycounter == (self._row_increase_line - 1):
                self._memptr_inc = self._buf_offset
            if self._buf_offset >= self._text_cols:
                self._close_h()
            else:
                self._fetch_state = self.FETCH_MATRIX

    def _run_sound_cycles(self, cycles: int) -> None:
        cdef int cycle_index
        cdef int channel
        cdef int mix
        cdef int reg
        cdef int enabled
        cdef int counter
        cdef int period
        cdef int reload_shift
        cdef int shift
        cdef int edge_trigger
        cdef int bit3
        cdef int bit12
        cdef int bit14
        cdef int bit15
        cdef int gate1
        cdef int gate2
        cdef int gate3
        cdef int gate4
        cdef double sample_clock
        cdef double cycles_per_sample
        cdef int volume
        cdef int tone_mask

        sample_clock = self._sound_sample_clock
        cycles_per_sample = self._cycles_per_sample
        volume = self.registers[0x0E] & 0x0F
        tone_mask = (
            self.registers[0x0A]
            | self.registers[0x0B]
            | self.registers[0x0C]
            | self.registers[0x0D]
        ) & 0x80

        if volume == 0 and tone_mask == 0:
            self._sound_accum_cycles += cycles
            sample_clock += cycles
            while sample_clock >= cycles_per_sample:
                sample_clock -= cycles_per_sample
                self._emit_sound_sample()
            self._sound_sample_clock = sample_clock
            return

        for cycle_index in range(cycles):
            mix = 0
            for channel in range(4):
                reg = self.registers[0x0A + channel]
                enabled = 1 if (reg & 0x80) else 0
                counter = self._sound_counters[channel] - 1
                self._sound_counters[channel] = counter
                if counter <= 0:
                    period = (~reg) & 0x7F
                    if period == 0:
                        period = 0x80
                    reload_shift = 4 - channel
                    counter += period << reload_shift
                    self._sound_counters[channel] = counter
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

                mix += enabled & self._sound_output[channel]

            self._sound_accum += mix
            self._sound_accum_cycles += 1
            sample_clock += 1.0
            if sample_clock >= cycles_per_sample:
                sample_clock -= cycles_per_sample
                self._emit_sound_sample()

        self._sound_sample_clock = sample_clock

    def _emit_sound_sample(self) -> None:
        cdef int sample
        cdef int volume
        cdef double level
        cdef double target

        if self._sound_accum_cycles <= 0:
            self._frame_samples.append(0)
            return
        volume = self.registers[0x0E] & 0x0F
        if volume:
            level = ((self._sound_accum * 7.0) / self._sound_accum_cycles) + 1.0
            target = (level * volume / self._MAX_OUTPUT_LEVEL) * 28000.0
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
