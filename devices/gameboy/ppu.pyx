# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""PPU support for the original Game Boy."""

from __future__ import annotations


cdef class GameBoyPPU:
    """Owns DMG LCD registers, timing and background rendering."""

    FRAME_WIDTH = 160
    FRAME_HEIGHT = 144
    CYCLES_PER_LINE = 456
    TOTAL_LINES = 154
    VISIBLE_LINES = 144
    PALETTE = (
        (224, 248, 208),
        (136, 192, 112),
        (52, 104, 86),
        (8, 24, 32),
    )

    cdef public object bus, interrupts
    cdef public int frame_width, frame_height
    cdef public int lcdc, stat, scy, scx, ly, lyc, bgp, obp0, obp1, wy, wx
    cdef int _last_tstates, _last_mode, _last_ly
    cdef object _line_scx, _line_scy, _line_wx, _line_wy, _line_lcdc, _line_bgp, _line_obp0, _line_obp1, _line_latched
    cdef public bytes framebuffer_rgb24

    def __init__(self, bus, interrupts=None):
        self.bus = bus
        self.interrupts = interrupts
        self.frame_width = self.FRAME_WIDTH
        self.frame_height = self.FRAME_HEIGHT
        self.reset()

    cpdef void reset(self):
        self.lcdc = 0x91
        self.stat = 0x85
        self.scy = 0x00
        self.scx = 0x00
        self.ly = 0x00
        self.lyc = 0x00
        self.bgp = 0xFC
        self.obp0 = 0xFF
        self.obp1 = 0xFF
        self.wy = 0x00
        self.wx = 0x00
        self._last_tstates = 0
        self._last_mode = 0
        self._last_ly = 0
        self._line_scx = [0] * self.FRAME_HEIGHT
        self._line_scy = [0] * self.FRAME_HEIGHT
        self._line_wx = [0] * self.FRAME_HEIGHT
        self._line_wy = [0] * self.FRAME_HEIGHT
        self._line_lcdc = [0] * self.FRAME_HEIGHT
        self._line_bgp = [0] * self.FRAME_HEIGHT
        self._line_obp0 = [0] * self.FRAME_HEIGHT
        self._line_obp1 = [0] * self.FRAME_HEIGHT
        self._line_latched = [False] * self.FRAME_HEIGHT
        self.framebuffer_rgb24 = self._make_blank_frame(self._palette_color(0))
        self._update_stat_mode(0)
        self._apply_bus_access(0)

    cpdef void begin_frame(self):
        self._last_tstates = 0
        self.ly = 0
        self._last_ly = 0
        self._last_mode = 2
        self._line_latched = [False] * self.FRAME_HEIGHT
        self._update_stat_mode(2)
        self._apply_bus_access(2)

    cpdef void run_until(self, int tstates):
        cdef int cursor
        cdef object boundary
        if tstates < 0:
            tstates = 0
        if tstates < self._last_tstates:
            self._last_tstates = tstates
            self._sync_state(tstates)
            return

        cursor = self._last_tstates
        while True:
            boundary = self._next_boundary_after(cursor)
            if boundary is None or boundary > tstates:
                break
            self._sync_state(boundary)
            cursor = boundary

        self._sync_state(tstates)

    cdef void _sync_state(self, int tstates):
        cdef int line = min(tstates // self.CYCLES_PER_LINE, self.TOTAL_LINES - 1)
        cdef int line_cycle = tstates % self.CYCLES_PER_LINE
        cdef int mode = self._mode_for_position(line, line_cycle)
        cdef int new_ly = line & 0xFF
        cdef bint lyc_match_before = (self.stat & 0x04) != 0
        cdef bint lyc_match_now

        self._last_tstates = tstates
        self.ly = new_ly
        lyc_match_now = new_ly == self.lyc
        if lyc_match_now:
            self.stat |= 0x04
        else:
            self.stat &= ~0x04

        if self.interrupts is not None:
            if lyc_match_now and not lyc_match_before and (self.stat & 0x40):
                self.interrupts.request(1)
            if new_ly >= self.VISIBLE_LINES and self._last_ly < self.VISIBLE_LINES:
                self.interrupts.request(0)

        if mode == 3 and self._last_mode != 3 and line < self.VISIBLE_LINES:
            self._latch_line_registers(line)

        if mode != self._last_mode and self.interrupts is not None:
            if mode == 0 and (self.stat & 0x08):
                self.interrupts.request(1)
            elif mode == 1 and (self.stat & 0x10):
                self.interrupts.request(1)
            elif mode == 2 and (self.stat & 0x20):
                self.interrupts.request(1)

        self._update_stat_mode(mode)
        self._apply_bus_access(mode)
        self._last_mode = mode
        self._last_ly = new_ly

    cdef inline int _mode_for_position(self, int line, int line_cycle):
        if line >= self.VISIBLE_LINES:
            return 1
        if line_cycle < 80:
            return 2
        if line_cycle < 252:
            return 3
        return 0

    cdef object _next_boundary_after(self, int tstates):
        cdef int line = min(tstates // self.CYCLES_PER_LINE, self.TOTAL_LINES - 1)
        cdef int line_cycle = tstates % self.CYCLES_PER_LINE
        cdef list candidates = []
        cdef int next_line_start
        if line >= self.TOTAL_LINES - 1 and line_cycle >= self.CYCLES_PER_LINE - 1:
            return None

        if line < self.VISIBLE_LINES:
            if line_cycle < 80:
                candidates.append(line * self.CYCLES_PER_LINE + 80)
            if line_cycle < 252:
                candidates.append(line * self.CYCLES_PER_LINE + 252)
        next_line_start = (line + 1) * self.CYCLES_PER_LINE
        if next_line_start <= (self.TOTAL_LINES - 1) * self.CYCLES_PER_LINE:
            candidates.append(next_line_start)
        if not candidates:
            return None
        return min(candidate for candidate in candidates if candidate > tstates)

    def render_frame(self) -> bytes:
        cdef bytearray out
        cdef bytearray bg_color_ids
        cdef tuple default_rgb, rgb
        cdef int y, x, offset
        cdef int line_lcdc, line_scx, line_scy, line_wx, line_wy, line_bgp
        cdef int line_bg_tile_map_base, line_window_tile_map_base
        cdef bint line_signed_tile_data, window_enabled, use_window
        cdef int window_x_start, map_base, source_y, source_x, tile_row, row_in_tile, tile_col, tile_index
        cdef int low, high, bit, color_id

        if (self.lcdc & 0x80) == 0:
            self.framebuffer_rgb24 = self._make_blank_frame(self._palette_color(0))
            return self.framebuffer_rgb24

        out = bytearray(self.FRAME_WIDTH * self.FRAME_HEIGHT * 3)
        bg_color_ids = bytearray(self.FRAME_WIDTH * self.FRAME_HEIGHT)
        default_rgb = self._palette_color(0)
        for y in range(self.FRAME_HEIGHT):
            line_lcdc = self._line_lcdc[y] if self._line_latched[y] else self.lcdc
            if (line_lcdc & 0x01) == 0:
                for x in range(self.FRAME_WIDTH):
                    offset = (y * self.FRAME_WIDTH + x) * 3
                    out[offset] = default_rgb[0]
                    out[offset + 1] = default_rgb[1]
                    out[offset + 2] = default_rgb[2]
                continue

            line_scx = self._line_scx[y] if self._line_latched[y] else self.scx
            line_scy = self._line_scy[y] if self._line_latched[y] else self.scy
            line_wx = self._line_wx[y] if self._line_latched[y] else self.wx
            line_wy = self._line_wy[y] if self._line_latched[y] else self.wy
            line_bgp = self._line_bgp[y] if self._line_latched[y] else self.bgp
            line_bg_tile_map_base = 0x1C00 if (line_lcdc & 0x08) else 0x1800
            line_window_tile_map_base = 0x1C00 if (line_lcdc & 0x40) else 0x1800
            line_signed_tile_data = (line_lcdc & 0x10) == 0
            window_enabled = (line_lcdc & 0x20) != 0
            window_x_start = line_wx - 7

            for x in range(self.FRAME_WIDTH):
                use_window = window_enabled and y >= line_wy and x >= window_x_start
                if use_window:
                    map_base = line_window_tile_map_base
                    source_y = y - line_wy
                    source_x = x - window_x_start
                else:
                    map_base = line_bg_tile_map_base
                    source_y = (line_scy + y) & 0xFF
                    source_x = (line_scx + x) & 0xFF

                tile_row = (source_y // 8) & 0x1F
                row_in_tile = source_y & 0x07
                tile_col = (source_x // 8) & 0x1F
                tile_index = self.bus.vram[map_base + tile_row * 32 + tile_col]
                low, high = self._read_tile_row(tile_index, row_in_tile, line_signed_tile_data)
                bit = 7 - (source_x & 0x07)
                color_id = (((high >> bit) & 1) << 1) | ((low >> bit) & 1)
                bg_color_ids[y * self.FRAME_WIDTH + x] = color_id
                rgb = self._palette_color(color_id, palette_reg=line_bgp)
                offset = (y * self.FRAME_WIDTH + x) * 3
                out[offset] = rgb[0]
                out[offset + 1] = rgb[1]
                out[offset + 2] = rgb[2]

        self._render_sprites(out, bg_color_ids)
        self.framebuffer_rgb24 = bytes(out)
        return self.framebuffer_rgb24

    def read_lcdc(self) -> int:
        return self.lcdc

    def write_lcdc(self, int value) -> None:
        self.lcdc = value & 0xFF
        if (self.lcdc & 0x80) == 0:
            self.ly = 0
            self._update_stat_mode(0)
            self._apply_bus_access(0)

    def read_stat(self) -> int:
        return self.stat | 0x80

    def write_stat(self, int value) -> None:
        self.stat = (self.stat & 0x07) | (value & 0x78)

    def read_scy(self) -> int:
        return self.scy

    def write_scy(self, int value) -> None:
        self.scy = value & 0xFF

    def read_scx(self) -> int:
        return self.scx

    def write_scx(self, int value) -> None:
        self.scx = value & 0xFF

    def read_ly(self) -> int:
        return self.ly

    def write_ly(self, value: int) -> None:
        self.ly = 0

    def read_lyc(self) -> int:
        return self.lyc

    def write_lyc(self, int value) -> None:
        self.lyc = value & 0xFF
        if self.ly == self.lyc:
            self.stat |= 0x04
        else:
            self.stat &= ~0x04

    def read_bgp(self) -> int:
        return self.bgp

    def write_bgp(self, int value) -> None:
        self.bgp = value & 0xFF

    def read_obp0(self) -> int:
        return self.obp0

    def write_obp0(self, int value) -> None:
        self.obp0 = value & 0xFF

    def read_obp1(self) -> int:
        return self.obp1

    def write_obp1(self, int value) -> None:
        self.obp1 = value & 0xFF

    def read_wy(self) -> int:
        return self.wy

    def write_wy(self, int value) -> None:
        self.wy = value & 0xFF

    def read_wx(self) -> int:
        return self.wx

    def write_wx(self, int value) -> None:
        self.wx = value & 0xFF

    cdef inline void _update_stat_mode(self, int mode):
        self.stat = (self.stat & ~0x03) | (mode & 0x03)

    cdef void _apply_bus_access(self, int mode):
        if (self.lcdc & 0x80) == 0:
            self.bus.set_ppu_access(vram_accessible=True, oam_accessible=True)
            return
        if mode == 2:
            self.bus.set_ppu_access(vram_accessible=True, oam_accessible=False)
            return
        if mode == 3:
            self.bus.set_ppu_access(vram_accessible=False, oam_accessible=False)
            return
        self.bus.set_ppu_access(vram_accessible=True, oam_accessible=True)

    cdef void _latch_line_registers(self, int line):
        if not (0 <= line < self.FRAME_HEIGHT):
            return
        if self._line_latched[line]:
            return
        self._line_scx[line] = self.scx
        self._line_scy[line] = self.scy
        self._line_wx[line] = self.wx
        self._line_wy[line] = self.wy
        self._line_lcdc[line] = self.lcdc
        self._line_bgp[line] = self.bgp
        self._line_obp0[line] = self.obp0
        self._line_obp1[line] = self.obp1
        self._line_latched[line] = True

    cdef tuple _read_tile_row(self, int tile_index, int row_in_tile, bint signed_tile_data):
        cdef int signed_index
        cdef int tile_addr
        cdef int low, high
        if signed_tile_data:
            signed_index = tile_index if tile_index < 0x80 else tile_index - 0x100
            tile_addr = 0x1000 + signed_index * 16
        else:
            tile_addr = tile_index * 16

        tile_addr &= 0x1FFF
        low = self.bus.vram[(tile_addr + row_in_tile * 2) & 0x1FFF]
        high = self.bus.vram[(tile_addr + row_in_tile * 2 + 1) & 0x1FFF]
        return low, high

    cdef void _render_sprites(self, bytearray out, bytearray bg_color_ids):
        cdef int screen_y, line_lcdc, sprite_height, index, base, y_pos, x_pos, tile_index, attrs
        cdef list line_sprites
        cdef int line_obp0, line_obp1, palette_reg, sprite_row, tile_y, tile_addr, low, high, sx, screen_x, bit, color_id, offset, shade
        cdef bint x_flip, y_flip, priority_behind_bg
        cdef tuple rgb

        sprite_height = 16 if (self.lcdc & 0x04) else 8
        for screen_y in range(self.FRAME_HEIGHT):
            line_lcdc = self._line_lcdc[screen_y] if self._line_latched[screen_y] else self.lcdc
            if (line_lcdc & 0x02) == 0:
                continue
            sprite_height = 16 if (line_lcdc & 0x04) else 8
            line_sprites = []
            for index in range(40):
                base = index * 4
                y_pos = self.bus.oam[base] - 16
                x_pos = self.bus.oam[base + 1] - 8
                tile_index = self.bus.oam[base + 2]
                attrs = self.bus.oam[base + 3]
                if x_pos <= -8 or x_pos >= self.FRAME_WIDTH:
                    continue
                if not (y_pos <= screen_y < y_pos + sprite_height):
                    continue
                line_sprites.append((x_pos, index, y_pos, tile_index, attrs))
                if len(line_sprites) == 10:
                    break

            line_sprites.sort(key=lambda item: (item[0], item[1]), reverse=True)

            for x_pos, index, y_pos, tile_index, attrs in line_sprites:
                line_obp0 = self._line_obp0[screen_y] if self._line_latched[screen_y] else self.obp0
                line_obp1 = self._line_obp1[screen_y] if self._line_latched[screen_y] else self.obp1
                palette_reg = line_obp1 if (attrs & 0x10) else line_obp0
                x_flip = (attrs & 0x20) != 0
                y_flip = (attrs & 0x40) != 0
                priority_behind_bg = (attrs & 0x80) != 0

                if sprite_height == 16:
                    tile_index &= 0xFE

                sprite_row = screen_y - y_pos
                tile_y = sprite_height - 1 - sprite_row if y_flip else sprite_row
                tile_addr = (tile_index * 16 + tile_y * 2) & 0x1FFF
                low = self.bus.vram[tile_addr]
                high = self.bus.vram[(tile_addr + 1) & 0x1FFF]

                for sx in range(8):
                    screen_x = x_pos + sx
                    if not (0 <= screen_x < self.FRAME_WIDTH):
                        continue
                    bit = sx if x_flip else 7 - sx
                    color_id = (((high >> bit) & 1) << 1) | ((low >> bit) & 1)
                    if color_id == 0:
                        continue
                    offset = (screen_y * self.FRAME_WIDTH + screen_x) * 3
                    if priority_behind_bg and bg_color_ids[screen_y * self.FRAME_WIDTH + screen_x] != 0:
                        continue
                    shade = (palette_reg >> (color_id * 2)) & 0x03
                    rgb = self.PALETTE[shade]
                    out[offset] = rgb[0]
                    out[offset + 1] = rgb[1]
                    out[offset + 2] = rgb[2]

    cdef tuple _palette_color(self, int color_id, int palette_reg=-1):
        cdef int shade
        if palette_reg < 0:
            palette_reg = self.bgp
        shade = (palette_reg >> (color_id * 2)) & 0x03
        return self.PALETTE[shade]

    cdef bytes _make_blank_frame(self, tuple rgb):
        cdef bytes pixel = bytes(rgb)
        return pixel * (self.FRAME_WIDTH * self.FRAME_HEIGHT)
