from __future__ import annotations

from chipsets.sms_vdp_reference import SMSVDPReference


class SMSVDP(SMSVDPReference):
    """Pure Python SMS VDP fallback kept outside the runtime package."""

    def _render_frame_from_state(self, vram, cram, registers, line_r0=None, line_scroll_x=None, line_scroll_y=None) -> bytes:
        palette_rgb = [self._cram_color(index, cram) for index in range(0x20)]
        bg = palette_rgb[registers[7] & 0x0F]
        out = bytearray(bytes(bg) * (self.FRAME_WIDTH * self.FRAME_HEIGHT))
        bg_priority_mask = bytearray(self.FRAME_WIDTH * self.FRAME_HEIGHT)

        if not self._display_enabled(registers):
            return bytes(out)

        name_base = self._name_table_base(registers)
        if line_r0 is None:
            line_r0 = bytes([registers[0] & 0xFF]) * self.FRAME_HEIGHT
        if line_scroll_x is None:
            line_scroll_x = bytes([registers[8] & 0xFF]) * self.FRAME_HEIGHT
        if line_scroll_y is None:
            line_scroll_y = bytes([registers[9] & 0xFF]) * self.FRAME_HEIGHT
        width = self.FRAME_WIDTH
        bg_rgb = palette_rgb[registers[7] & 0x0F]

        for tile_y in range(28):
            for tile_x in range(-1, 32):
                for row in range(8):
                    base_py = tile_y * 8 + row
                    if base_py >= self.FRAME_HEIGHT:
                        continue
                    scroll_y = line_scroll_y[base_py] & 0xFF
                    r0_row = line_r0[base_py] & 0xFF
                    right_cols_no_vscroll = bool(r0_row & 0x80)
                    effective_scroll_y = 0 if (right_cols_no_vscroll and tile_x >= 24) else scroll_y
                    py = tile_y * 8 + row - (effective_scroll_y & 0x07)
                    if py >= self.FRAME_HEIGHT or py < 0:
                        continue
                    scroll_x = line_scroll_x[py] & 0xFF
                    r0 = line_r0[py] & 0xFF
                    top_rows_no_hscroll = bool(r0 & 0x40)
                    effective_scroll_x = 0 if (top_rows_no_hscroll and py < 16) else scroll_x
                    coarse_x = (effective_scroll_x >> 3) % 32
                    fine_x = effective_scroll_x & 0x07
                    map_y = ((tile_y * 8 + effective_scroll_y) // 8) % 28
                    map_x = (tile_x - coarse_x) % 32
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
        if any((line_r0[py] & 0x20) != 0 for py in range(self.FRAME_HEIGHT)):
            for py in range(self.FRAME_HEIGHT):
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

    def render_frame(self) -> bytes:
        self.framebuffer_rgb24 = self._render_frame_from_state(self.vram, self.cram, self.registers)
        return self.framebuffer_rgb24
