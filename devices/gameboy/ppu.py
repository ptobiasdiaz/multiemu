"""PPU support for the original Game Boy."""

from __future__ import annotations


class GameBoyPPU:
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

    def __init__(self, bus, interrupts=None):
        self.bus = bus
        self.interrupts = interrupts
        self.frame_width = self.FRAME_WIDTH
        self.frame_height = self.FRAME_HEIGHT
        self.reset()

    def reset(self):
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

    def begin_frame(self):
        self._last_tstates = 0
        self.ly = 0
        self._last_ly = 0
        self._last_mode = 2
        self._line_latched = [False] * self.FRAME_HEIGHT
        self._update_stat_mode(2)
        self._apply_bus_access(2)

    def run_until(self, tstates: int) -> None:
        tstates = max(0, int(tstates))
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

    def _sync_state(self, tstates: int) -> None:
        self._last_tstates = tstates
        line = min(tstates // self.CYCLES_PER_LINE, self.TOTAL_LINES - 1)
        line_cycle = tstates % self.CYCLES_PER_LINE
        mode = self._mode_for_position(line, line_cycle)
        new_ly = line & 0xFF

        lyc_match_before = (self.stat & 0x04) != 0
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

    def _mode_for_position(self, line: int, line_cycle: int) -> int:
        if line >= self.VISIBLE_LINES:
            return 1
        if line_cycle < 80:
            return 2
        if line_cycle < 252:
            return 3
        return 0

    def _next_boundary_after(self, tstates: int) -> int | None:
        line = min(tstates // self.CYCLES_PER_LINE, self.TOTAL_LINES - 1)
        line_cycle = tstates % self.CYCLES_PER_LINE
        if line >= self.TOTAL_LINES - 1 and line_cycle >= self.CYCLES_PER_LINE - 1:
            return None

        candidates = []
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
                color_id = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
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

    def write_lcdc(self, value: int) -> None:
        self.lcdc = value & 0xFF
        if (self.lcdc & 0x80) == 0:
            self.ly = 0
            self._update_stat_mode(0)
            self._apply_bus_access(0)

    def read_stat(self) -> int:
        return self.stat | 0x80

    def write_stat(self, value: int) -> None:
        self.stat = (self.stat & 0x07) | (value & 0x78)

    def read_scy(self) -> int:
        return self.scy

    def write_scy(self, value: int) -> None:
        self.scy = value & 0xFF

    def read_scx(self) -> int:
        return self.scx

    def write_scx(self, value: int) -> None:
        self.scx = value & 0xFF

    def read_ly(self) -> int:
        return self.ly

    def write_ly(self, value: int) -> None:
        del value
        self.ly = 0

    def read_lyc(self) -> int:
        return self.lyc

    def write_lyc(self, value: int) -> None:
        self.lyc = value & 0xFF
        if self.ly == self.lyc:
            self.stat |= 0x04
        else:
            self.stat &= ~0x04

    def read_bgp(self) -> int:
        return self.bgp

    def write_bgp(self, value: int) -> None:
        self.bgp = value & 0xFF

    def read_obp0(self) -> int:
        return self.obp0

    def write_obp0(self, value: int) -> None:
        self.obp0 = value & 0xFF

    def read_obp1(self) -> int:
        return self.obp1

    def write_obp1(self, value: int) -> None:
        self.obp1 = value & 0xFF

    def read_wy(self) -> int:
        return self.wy

    def write_wy(self, value: int) -> None:
        self.wy = value & 0xFF

    def read_wx(self) -> int:
        return self.wx

    def write_wx(self, value: int) -> None:
        self.wx = value & 0xFF

    def _update_stat_mode(self, mode: int) -> None:
        self.stat = (self.stat & ~0x03) | (mode & 0x03)

    def _apply_bus_access(self, mode: int) -> None:
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

    def _latch_line_registers(self, line: int) -> None:
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

    def _read_tile_row(self, tile_index: int, row_in_tile: int, signed_tile_data: bool) -> tuple[int, int]:
        if signed_tile_data:
            signed_index = tile_index if tile_index < 0x80 else tile_index - 0x100
            tile_addr = 0x1000 + signed_index * 16
        else:
            tile_addr = tile_index * 16

        tile_addr &= 0x1FFF
        low = self.bus.vram[(tile_addr + row_in_tile * 2) & 0x1FFF]
        high = self.bus.vram[(tile_addr + row_in_tile * 2 + 1) & 0x1FFF]
        return low, high

    def _render_sprites(self, out: bytearray, bg_color_ids: bytearray) -> None:
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
                del index
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
                    color_id = ((high >> bit) & 1) << 1 | ((low >> bit) & 1)
                    if color_id == 0:
                        continue

                    offset = (screen_y * self.FRAME_WIDTH + screen_x) * 3
                    if priority_behind_bg:
                        if bg_color_ids[screen_y * self.FRAME_WIDTH + screen_x] != 0:
                            continue

                    shade = (palette_reg >> (color_id * 2)) & 0x03
                    rgb = self.PALETTE[shade]
                    out[offset] = rgb[0]
                    out[offset + 1] = rgb[1]
                    out[offset + 2] = rgb[2]

    def _palette_color(self, color_id: int, *, palette_reg: int | None = None) -> tuple[int, int, int]:
        if palette_reg is None:
            palette_reg = self.bgp
        shade = (palette_reg >> (color_id * 2)) & 0x03
        return self.PALETTE[shade]

    def _make_blank_frame(self, rgb: tuple[int, int, int]) -> bytes:
        pixel = bytes(rgb)
        return pixel * (self.FRAME_WIDTH * self.FRAME_HEIGHT)
