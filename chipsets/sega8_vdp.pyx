from __future__ import annotations
# cython: cdivision=False

from .sega8_vdp_fallback import Sega8VDPFallback


cdef int FRAME_WIDTH = 256
cdef int FRAME_HEIGHT = 192


class Sega8VDP(Sega8VDPFallback):
    """Cython-backed Sega 8-bit VDP.

    Keep this logic aligned with ``tests/sega8_vdp.py``. The Python
    implementation stays as the easy-to-read production fallback, while this
    module is the drop-in path for native builds.
    """

    def reset(self) -> None:
        self.vram[:] = b"\x00" * self.VRAM_SIZE
        self.cram[:] = b"\x00" * self.CRAM_SIZE
        self.registers[:] = b"\x00" * 16
        self.status = 0x00
        self.address = 0x0000
        self.code = 0
        self.read_buffer = 0x00
        self.first_control = None
        self.data_latch = 0x00
        self.latched_h_counter = 0x00
        self.framebuffer_rgb24 = bytes(FRAME_WIDTH * FRAME_HEIGHT * 3)
        self.interrupt_fired = False
        self._line_interrupt_pending = False
        self._frame_interrupt_pending = False
        self.last_tstates = 0
        self._line_irq_counter = 0
        self._scanline_index = 0
        self._next_scanline_tstate = 0
        self._render_vram = None
        self._render_cram = None
        self._render_registers = None
        self._render_line_r0 = None
        self._render_line_scroll_x = None
        self._render_line_scroll_y = None
        self._line_r0[:] = b"\x00" * FRAME_HEIGHT
        self._line_scroll_x[:] = b"\x00" * FRAME_HEIGHT
        self._line_scroll_y[:] = b"\x00" * FRAME_HEIGHT
        self._refresh_timing_constants()

    def _refresh_timing_constants(self) -> None:
        self._scanline_tstates = max(1, self.machine.TSTATES_PER_FRAME // self.TOTAL_SCANLINES)
        self.VBLANK_TSTATE = self._scanline_tstates * FRAME_HEIGHT

    def begin_frame(self) -> None:
        self._refresh_timing_constants()
        self.interrupt_fired = False
        self.last_tstates = 0
        self._line_irq_counter = self.registers[10] & 0xFF
        self._scanline_index = 0
        self._next_scanline_tstate = self._scanline_tstates
        self._render_vram = None
        self._render_cram = None
        self._render_registers = None
        self._render_line_r0 = None
        self._render_line_scroll_x = None
        self._render_line_scroll_y = None
        self._line_r0[:] = bytes([self.registers[0] & 0xFF]) * FRAME_HEIGHT
        self._line_scroll_x[:] = bytes([self.registers[8] & 0xFF]) * FRAME_HEIGHT
        self._line_scroll_y[:] = bytes([self.registers[9] & 0xFF]) * FRAME_HEIGHT

    def run_until(self, int tstates) -> None:
        self.last_tstates = tstates
        while (
            self._scanline_index < self.TOTAL_SCANLINES
            and self._next_scanline_tstate > 0
            and tstates >= self._next_scanline_tstate
        ):
            if self._scanline_index < FRAME_HEIGHT:
                if self._line_irq_counter == 0:
                    self._line_interrupt_pending = True
                    self._service_interrupt()
                    self._line_irq_counter = self.registers[10] & 0xFF
                else:
                    self._line_irq_counter = (self._line_irq_counter - 1) & 0xFF
            else:
                self._line_irq_counter = (self._line_irq_counter - 1) & 0xFF
            self._scanline_index += 1
            if self._scanline_index < FRAME_HEIGHT:
                self._line_r0[self._scanline_index] = self.registers[0] & 0xFF
                self._line_scroll_x[self._scanline_index] = self.registers[8] & 0xFF
                self._line_scroll_y[self._scanline_index] = self.registers[9] & 0xFF
            if (not self.interrupt_fired) and self._scanline_index >= FRAME_HEIGHT:
                self._capture_render_state()
                self.status |= 0x80
                self._frame_interrupt_pending = True
                self._service_interrupt()
                self.interrupt_fired = True
            self._next_scanline_tstate += self._scanline_tstates

    def _service_interrupt(self) -> None:
        if (
            (self._line_interrupt_pending and (self.registers[0] & 0x10))
            or (self._frame_interrupt_pending and (self.registers[1] & 0x20))
        ):
            self.machine.cpu.interrupt()

    def end_frame(self) -> None:
        if self._render_vram is not None:
            self.framebuffer_rgb24 = self._render_frame_from_state(
                self._render_vram,
                self._render_cram,
                self._render_registers,
                self._render_line_r0,
                self._render_line_scroll_x,
                self._render_line_scroll_y,
            )
        else:
            self.framebuffer_rgb24 = self.render_frame()

    def _capture_render_state(self) -> None:
        if self._render_vram is None:
            self._render_vram = bytes(self.vram)
            self._render_cram = bytes(self.cram)
            self._render_registers = bytes(self.registers)
            self._render_line_r0 = bytes(self._line_r0)
            self._render_line_scroll_x = bytes(self._line_scroll_x)
            self._render_line_scroll_y = bytes(self._line_scroll_y)

    def _autoincrement(self) -> int:
        cdef int step = self.registers[15] or 1
        self.address = (self.address + step) & 0x3FFF
        return step

    def write_control(self, int value) -> None:
        cdef int first
        cdef int command
        value &= 0xFF
        if self.first_control is None:
            self.first_control = value
            return
        first = self.first_control
        self.first_control = None
        command = (value >> 6) & 0x03
        if command == 0x02:
            self.registers[value & 0x0F] = first
            self._service_interrupt()
            return
        self.code = command
        self.address = (((value & 0x3F) << 8) | first) & 0x3FFF
        if self.code == 0x00:
            self.read_buffer = self.vram[self.address]
            self._autoincrement()

    def read_control(self) -> int:
        cdef int value
        self.first_control = None
        value = self.status & 0xFF
        self.status &= ~0xE0
        self._line_interrupt_pending = False
        self._frame_interrupt_pending = False
        return value

    def read_v_counter(self) -> int:
        cdef int scanline = (self.last_tstates * self.TOTAL_SCANLINES) // max(1, self.machine.TSTATES_PER_FRAME)
        scanline &= 0x1FF
        if scanline >= 0xDA:
            scanline -= 6
        return scanline & 0xFF

    def read_h_counter(self) -> int:
        return self.latched_h_counter & 0xFF

    def latch_h_counter(self) -> None:
        cdef int tstates_in_line = self.machine.TSTATES_PER_FRAME // self.TOTAL_SCANLINES
        cdef int pos
        if tstates_in_line <= 0:
            self.latched_h_counter = 0
            return
        pos = self.last_tstates % tstates_in_line
        self.latched_h_counter = ((pos * 256) // tstates_in_line) & 0xFF

    def write_data(self, int value) -> None:
        value &= 0xFF
        self.first_control = None
        self.data_latch = value
        if self.code == 0x03:
            self.cram[self.address & (self.CRAM_SIZE - 1)] = value
        else:
            self.vram[self.address] = value
        self.read_buffer = value
        self._autoincrement()

    def read_data(self) -> int:
        cdef int value
        self.first_control = None
        value = self.read_buffer
        self.read_buffer = self.vram[self.address]
        self._autoincrement()
        return value & 0xFF

    def _name_table_base(self, object registers=None) -> int:
        cdef object regs = self.registers if registers is None else registers
        return ((regs[2] & 0x0E) << 10) & 0x3FFF

    def _display_enabled(self, object registers=None) -> bool:
        cdef object regs = self.registers if registers is None else registers
        return (regs[1] & 0x40) != 0

    def _cram_color(self, int index, object cram=None) -> tuple[int, int, int]:
        cdef object cram_data = self.cram if cram is None else cram
        cdef int value
        cdef int r
        cdef int g
        cdef int b
        cdef int addr
        if self.is_game_gear:
            addr = (index & 0x1F) * 2
            value = cram_data[addr] | (cram_data[(addr + 1) & 0x3F] << 8)
            r = (value & 0x000F) * 17
            g = ((value >> 4) & 0x000F) * 17
            b = ((value >> 8) & 0x000F) * 17
            return (r, g, b)
        value = cram_data[index & 0x1F]
        r = (value & 0x03) * 85
        g = ((value >> 2) & 0x03) * 85
        b = ((value >> 4) & 0x03) * 85
        return (r, g, b)

    def _tile_color_index(self, int tile, int row, int column, object vram=None) -> int:
        cdef object vram_data = self.vram if vram is None else vram
        cdef int tile_addr = ((tile & 0x1FF) * 32 + row * 4) & 0x3FFF
        cdef int bit = 7 - column
        cdef int p0 = (vram_data[tile_addr + 0] >> bit) & 1
        cdef int p1 = (vram_data[tile_addr + 1] >> bit) & 1
        cdef int p2 = (vram_data[tile_addr + 2] >> bit) & 1
        cdef int p3 = (vram_data[tile_addr + 3] >> bit) & 1
        return p0 | (p1 << 1) | (p2 << 2) | (p3 << 3)

    def _sprite_attribute_base(self, object registers=None) -> int:
        cdef object regs = self.registers if registers is None else registers
        return ((regs[5] & 0x7E) << 7) & 0x3FFF

    def _sprite_pattern_base(self, object registers=None) -> int:
        cdef object regs = self.registers if registers is None else registers
        return ((regs[6] & 0x04) << 11) & 0x2000

    def _sprite_height(self, object registers=None) -> int:
        cdef object regs = self.registers if registers is None else registers
        return 16 if (regs[1] & 0x02) else 8

    def _sprite_zoom(self, object registers=None) -> int:
        cdef object regs = self.registers if registers is None else registers
        return 2 if (regs[1] & 0x01) else 1

    def _render_frame_from_state(self, object vram, object cram, object registers, object line_r0=None, object line_scroll_x=None, object line_scroll_y=None) -> bytes:
        cdef int tile_y
        cdef int tile_x
        cdef int row
        cdef int col
        cdef int px
        cdef int py
        cdef int base_py
        cdef int scroll_y
        cdef int scroll_x
        cdef int effective_scroll_y
        cdef int effective_scroll_x
        cdef int coarse_x
        cdef int fine_x
        cdef int map_y
        cdef int map_x
        cdef int entry_addr
        cdef int low
        cdef int high
        cdef int tile
        cdef int palette
        cdef int source_row
        cdef int source_col
        cdef int tile_addr
        cdef int b0
        cdef int b1
        cdef int b2
        cdef int b3
        cdef int row_base
        cdef int bit
        cdef int color
        cdef int pixel_index
        cdef int offset
        cdef int name_base
        cdef int width
        cdef int r0
        cdef int r0_row
        cdef bint right_cols_no_vscroll
        cdef bint top_rows_no_hscroll
        cdef bint hflip
        cdef bint vflip
        cdef bint priority
        cdef object rgb
        cdef object bg_rgb
        cdef object palette_rgb
        cdef bytearray out
        cdef bytearray bg_priority_mask

        palette_rgb = [self._cram_color(index, cram) for index in range(0x20)]
        bg = palette_rgb[registers[7] & 0x0F]
        out = bytearray(bytes(bg) * (FRAME_WIDTH * FRAME_HEIGHT))
        bg_priority_mask = bytearray(FRAME_WIDTH * FRAME_HEIGHT)

        if not self._display_enabled(registers):
            return bytes(out)

        name_base = self._name_table_base(registers)
        if line_r0 is None:
            line_r0 = bytes([registers[0] & 0xFF]) * FRAME_HEIGHT
        if line_scroll_x is None:
            line_scroll_x = bytes([registers[8] & 0xFF]) * FRAME_HEIGHT
        if line_scroll_y is None:
            line_scroll_y = bytes([registers[9] & 0xFF]) * FRAME_HEIGHT
        width = FRAME_WIDTH
        bg_rgb = palette_rgb[registers[7] & 0x0F]

        for tile_y in range(28):
            for tile_x in range(-1, 32):
                for row in range(8):
                    base_py = tile_y * 8 + row
                    if base_py >= FRAME_HEIGHT:
                        continue
                    scroll_y = line_scroll_y[base_py] & 0xFF
                    r0_row = line_r0[base_py] & 0xFF
                    right_cols_no_vscroll = (r0_row & 0x80) != 0
                    effective_scroll_y = 0 if (right_cols_no_vscroll and tile_x >= 24) else scroll_y
                    py = tile_y * 8 + row - (effective_scroll_y & 0x07)
                    if py >= FRAME_HEIGHT or py < 0:
                        continue
                    scroll_x = line_scroll_x[py] & 0xFF
                    r0 = line_r0[py] & 0xFF
                    top_rows_no_hscroll = (r0 & 0x40) != 0
                    effective_scroll_x = 0 if (top_rows_no_hscroll and py < 16) else scroll_x
                    coarse_x = (effective_scroll_x >> 3) % 32
                    fine_x = effective_scroll_x & 0x07
                    map_y = ((tile_y * 8 + effective_scroll_y) // 8) % 28
                    map_x = (tile_x - coarse_x) & 0x1F
                    entry_addr = (name_base + (map_y * 32 + map_x) * 2) & 0x3FFF
                    low = vram[entry_addr]
                    high = vram[(entry_addr + 1) & 0x3FFF]
                    tile = low | ((high & 0x01) << 8)
                    hflip = (high & 0x02) != 0
                    vflip = (high & 0x04) != 0
                    palette = 0x10 if (high & 0x08) else 0x00
                    priority = (high & 0x10) != 0
                    source_row = 7 - row if vflip else row
                    tile_addr = ((tile & 0x1FF) * 32 + source_row * 4) & 0x3FFF
                    b0 = vram[tile_addr + 0]
                    b1 = vram[tile_addr + 1]
                    b2 = vram[tile_addr + 2]
                    b3 = vram[tile_addr + 3]
                    row_base = py * width

                    for col in range(8):
                        source_col = 7 - col if hflip else col
                        px = tile_x * 8 + col + fine_x
                        if px >= width or px < 0:
                            continue
                        bit = 7 - source_col
                        color = (
                            ((b0 >> bit) & 1)
                            | (((b1 >> bit) & 1) << 1)
                            | (((b2 >> bit) & 1) << 2)
                            | (((b3 >> bit) & 1) << 3)
                        )
                        if color == 0:
                            continue
                        pixel_index = row_base + px
                        rgb = palette_rgb[palette + color]
                        offset = pixel_index * 3
                        out[offset] = rgb[0]
                        out[offset + 1] = rgb[1]
                        out[offset + 2] = rgb[2]
                        if priority:
                            bg_priority_mask[pixel_index] = 1

        self._render_sprites(out, palette_rgb, bg_priority_mask, vram, registers)
        if any((line_r0[py] & 0x20) != 0 for py in range(FRAME_HEIGHT)):
            for py in range(FRAME_HEIGHT):
                if (line_r0[py] & 0x20) == 0:
                    continue
                row_base = py * width
                for px in range(8):
                    pixel_index = row_base + px
                    offset = pixel_index * 3
                    out[offset] = bg_rgb[0]
                    out[offset + 1] = bg_rgb[1]
                    out[offset + 2] = bg_rgb[2]
        return bytes(out)

    def _render_sprites(self, bytearray out, object palette_rgb, bytearray bg_priority_mask, object vram=None, object registers=None) -> None:
        cdef object vram_data = self.vram if vram is None else vram
        cdef object regs = self.registers if registers is None else registers
        cdef int sat_base = self._sprite_attribute_base(regs)
        cdef int sprite_height = 16 if (regs[1] & 0x02) else 8
        cdef int zoom = 2 if (regs[1] & 0x01) else 1
        cdef bint sprite_shift_left = (regs[0] & 0x08) != 0
        cdef int visible_sprite_height = sprite_height * zoom
        cdef int pattern_base = ((regs[6] & 0x04) << 11) & 0x2000
        cdef list line_counts = [0] * FRAME_HEIGHT
        cdef bytearray sprite_mask = bytearray(FRAME_WIDTH * FRAME_HEIGHT)
        cdef int sprite_count = 0
        cdef int sprite_x[64]
        cdef int sprite_tile[64]
        cdef int sprite_row_count[64]
        cdef int sprite_py[64][32]
        cdef int sprite_source_row[64][32]
        cdef int index
        cdef int row
        cdef int y
        cdef int sprite_y
        cdef int x
        cdef int tile
        cdef int py
        cdef int source_row
        cdef int tile_index
        cdef int color_row
        cdef int tile_addr
        cdef int b0
        cdef int b1
        cdef int b2
        cdef int b3
        cdef int col
        cdef int bit
        cdef int color
        cdef int zoom_col
        cdef int px
        cdef int pixel_index
        cdef int offset
        cdef int sprite
        cdef int visible_count
        cdef object rgb

        for index in range(64):
            y = vram_data[(sat_base + index) & 0x3FFF]
            if y == 0xD0:
                break
            sprite_y = (y + 1) & 0xFF
            x = vram_data[(sat_base + 0x80 + index * 2) & 0x3FFF]
            if sprite_shift_left:
                x -= 8
            tile = vram_data[(sat_base + 0x81 + index * 2) & 0x3FFF]
            if sprite_height == 16:
                tile &= 0xFE
            visible_count = 0
            for row in range(visible_sprite_height):
                py = sprite_y + row
                if py < 0 or py >= FRAME_HEIGHT:
                    continue
                if line_counts[py] >= 8:
                    self.status |= 0x40
                    continue
                line_counts[py] += 1
                source_row = row // zoom
                sprite_py[sprite_count][visible_count] = py
                sprite_source_row[sprite_count][visible_count] = source_row
                visible_count += 1
            if visible_count:
                sprite_x[sprite_count] = x
                sprite_tile[sprite_count] = tile
                sprite_row_count[sprite_count] = visible_count
                sprite_count += 1

        for sprite in range(sprite_count - 1, -1, -1):
            x = sprite_x[sprite]
            tile = sprite_tile[sprite]
            for row in range(sprite_row_count[sprite]):
                py = sprite_py[sprite][row]
                source_row = sprite_source_row[sprite][row]
                tile_index = tile + (source_row // 8)
                color_row = source_row & 0x07
                tile_addr = (pattern_base + (tile_index & 0x1FF) * 32 + color_row * 4) & 0x3FFF
                b0 = vram_data[tile_addr + 0]
                b1 = vram_data[tile_addr + 1]
                b2 = vram_data[tile_addr + 2]
                b3 = vram_data[tile_addr + 3]
                for col in range(8):
                    bit = 7 - col
                    color = (
                        ((b0 >> bit) & 1)
                        | (((b1 >> bit) & 1) << 1)
                        | (((b2 >> bit) & 1) << 2)
                        | (((b3 >> bit) & 1) << 3)
                    )
                    if color == 0:
                        continue
                    for zoom_col in range(zoom):
                        px = x + col * zoom + zoom_col
                        if px < 0 or px >= FRAME_WIDTH:
                            continue
                        pixel_index = py * FRAME_WIDTH + px
                        if bg_priority_mask[pixel_index]:
                            continue
                        if sprite_mask[pixel_index]:
                            self.status |= 0x20
                        sprite_mask[pixel_index] = 1
                        rgb = palette_rgb[0x10 + color]
                        offset = pixel_index * 3
                        out[offset] = rgb[0]
                        out[offset + 1] = rgb[1]
                        out[offset + 2] = rgb[2]

    def render_frame(self) -> bytes:
        self.framebuffer_rgb24 = self._render_frame_from_state(self.vram, self.cram, self.registers)
        return self.framebuffer_rgb24

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "Sega8VDP"},
            "status": self.status,
            "address": self.address,
            "code": self.code,
            "read_buffer": self.read_buffer,
            "data_latch": self.data_latch,
            "latched_h_counter": self.latched_h_counter,
            "interrupt_fired": self.interrupt_fired,
            "last_tstates": self.last_tstates,
            "_line_irq_counter": self._line_irq_counter,
            "_scanline_index": self._scanline_index,
            "_next_scanline_tstate": self._next_scanline_tstate,
            "_line_interrupt_pending": self._line_interrupt_pending,
            "_frame_interrupt_pending": self._frame_interrupt_pending,
            "vram": list(self.vram),
            "cram": list(self.cram),
            "registers": list(self.registers),
            "first_control": self.first_control,
            "render_vram": None if self._render_vram is None else list(self._render_vram),
            "render_cram": None if self._render_cram is None else list(self._render_cram),
            "render_registers": None if self._render_registers is None else list(self._render_registers),
            "render_line_r0": None if self._render_line_r0 is None else list(self._render_line_r0),
            "render_line_scroll_x": None if self._render_line_scroll_x is None else list(self._render_line_scroll_x),
            "render_line_scroll_y": None if self._render_line_scroll_y is None else list(self._render_line_scroll_y),
            "line_r0": list(self._line_r0),
            "line_scroll_x": list(self._line_scroll_x),
            "line_scroll_y": list(self._line_scroll_y),
        }

    def write_state(self, dict state) -> None:
        cdef object value
        cdef object values
        if "status" in state:
            self.status = int(state["status"]) & 0xFF
        if "address" in state:
            self.address = int(state["address"]) & 0x3FFF
        if "code" in state:
            self.code = int(state["code"]) & 0x03
        if "read_buffer" in state:
            self.read_buffer = int(state["read_buffer"]) & 0xFF
        if "data_latch" in state:
            self.data_latch = int(state["data_latch"]) & 0xFF
        if "latched_h_counter" in state:
            self.latched_h_counter = int(state["latched_h_counter"]) & 0xFF
        if "interrupt_fired" in state:
            self.interrupt_fired = bool(state["interrupt_fired"])
        if "last_tstates" in state:
            self.last_tstates = int(state["last_tstates"])
        if "_line_irq_counter" in state:
            self._line_irq_counter = int(state["_line_irq_counter"]) & 0xFF
        if "_scanline_index" in state:
            self._scanline_index = int(state["_scanline_index"])
        if "_next_scanline_tstate" in state:
            self._next_scanline_tstate = int(state["_next_scanline_tstate"])
        if "_line_interrupt_pending" in state:
            self._line_interrupt_pending = bool(state["_line_interrupt_pending"])
        if "_frame_interrupt_pending" in state:
            self._frame_interrupt_pending = bool(state["_frame_interrupt_pending"])
        if "vram" in state:
            self.vram[:] = bytes(int(v) & 0xFF for v in state["vram"][: self.VRAM_SIZE]).ljust(self.VRAM_SIZE, b"\x00")
        if "cram" in state:
            self.cram[:] = bytes(int(v) & 0xFF for v in state["cram"][: self.CRAM_SIZE]).ljust(self.CRAM_SIZE, b"\x00")
        if "registers" in state:
            self.registers[:] = bytes(int(v) & 0xFF for v in state["registers"][:16]).ljust(16, b"\x00")
        if "first_control" in state:
            value = state["first_control"]
            self.first_control = None if value is None else int(value) & 0xFF
        if "render_vram" in state:
            values = state["render_vram"]
            self._render_vram = None if values is None else bytes(int(v) & 0xFF for v in values)
        if "render_cram" in state:
            values = state["render_cram"]
            self._render_cram = None if values is None else bytes(int(v) & 0xFF for v in values)
        if "render_registers" in state:
            values = state["render_registers"]
            self._render_registers = None if values is None else bytes(int(v) & 0xFF for v in values)
        if "render_line_r0" in state:
            values = state["render_line_r0"]
            self._render_line_r0 = None if values is None else bytes(int(v) & 0xFF for v in values)
        if "render_line_scroll_x" in state:
            values = state["render_line_scroll_x"]
            self._render_line_scroll_x = None if values is None else bytes(int(v) & 0xFF for v in values)
        if "render_line_scroll_y" in state:
            values = state["render_line_scroll_y"]
            self._render_line_scroll_y = None if values is None else bytes(int(v) & 0xFF for v in values)
        if "line_r0" in state:
            values = state["line_r0"]
            self._line_r0[:] = bytes(int(v) & 0xFF for v in values[:FRAME_HEIGHT]).ljust(FRAME_HEIGHT, b"\x00")
        if "line_scroll_x" in state:
            values = state["line_scroll_x"]
            self._line_scroll_x[:] = bytes(int(v) & 0xFF for v in values[:FRAME_HEIGHT]).ljust(FRAME_HEIGHT, b"\x00")
        if "line_scroll_y" in state:
            values = state["line_scroll_y"]
            self._line_scroll_y[:] = bytes(int(v) & 0xFF for v in values[:FRAME_HEIGHT]).ljust(FRAME_HEIGHT, b"\x00")
        self.framebuffer_rgb24 = self.render_frame()


SMSVDP = Sega8VDP
