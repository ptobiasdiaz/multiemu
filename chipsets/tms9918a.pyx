from __future__ import annotations


cdef class TMS9918A:
    cdef public object machine
    cdef public bytearray vram
    cdef public bytearray registers
    cdef public int status
    cdef public int address
    cdef public int read_buffer
    cdef public object first_control
    cdef public int code
    cdef public bytes framebuffer_rgb24
    cdef public bint interrupt_fired
    cdef public bint interrupt_line_asserted
    cdef public int last_tstates
    cdef public int VBLANK_TSTATE

    FRAME_WIDTH = 256
    FRAME_HEIGHT = 192
    VRAM_SIZE = 0x4000
    TOTAL_SCANLINES = 262

    PALETTE = (
        (0, 0, 0),
        (0, 0, 0),
        (33, 200, 66),
        (94, 220, 120),
        (84, 85, 237),
        (125, 118, 252),
        (212, 82, 77),
        (66, 235, 245),
        (252, 85, 84),
        (255, 121, 120),
        (212, 193, 84),
        (230, 206, 128),
        (33, 176, 59),
        (201, 91, 186),
        (204, 204, 204),
        (255, 255, 255),
    )

    def __init__(self, machine):
        self.machine = machine
        self.vram = bytearray(self.VRAM_SIZE)
        self.registers = bytearray(8)
        self.status = 0x00
        self.address = 0x0000
        self.read_buffer = 0x00
        self.first_control = None
        self.code = 0
        self.framebuffer_rgb24 = bytes(self.FRAME_WIDTH * self.FRAME_HEIGHT * 3)
        self.interrupt_fired = False
        self.interrupt_line_asserted = False
        self.last_tstates = 0
        self._refresh_timing_constants()

    def _refresh_timing_constants(self) -> None:
        scanline_tstates = max(1, self.machine.TSTATES_PER_FRAME // self.TOTAL_SCANLINES)
        self.VBLANK_TSTATE = scanline_tstates * self.FRAME_HEIGHT

    def reset(self) -> None:
        self.vram[:] = b"\x00" * self.VRAM_SIZE
        self.registers[:] = b"\x00" * 8
        self.status = 0x00
        self.address = 0x0000
        self.read_buffer = 0x00
        self.first_control = None
        self.code = 0
        self.framebuffer_rgb24 = bytes(self.FRAME_WIDTH * self.FRAME_HEIGHT * 3)
        self.interrupt_fired = False
        self.interrupt_line_asserted = False
        self.last_tstates = 0
        self._refresh_timing_constants()

    def begin_frame(self) -> None:
        self._refresh_timing_constants()
        self.interrupt_fired = False
        self.last_tstates = 0

    def run_until(self, tstates: int) -> None:
        self.last_tstates = tstates
        if self.interrupt_fired:
            return
        if tstates < self.VBLANK_TSTATE:
            return
        self._latch_sprite_status_for_frame()
        if (self.status & 0x80) == 0:
            self.status |= 0x80
        if (self.registers[1] & 0x20) and not self.interrupt_line_asserted:
            if getattr(self.machine, "vdp_vblank_uses_nmi", False) and hasattr(self.machine.cpu, "nmi"):
                self.machine.cpu.nmi()
            else:
                self.machine.cpu.interrupt()
            self.interrupt_line_asserted = True
        self.interrupt_fired = True

    def end_frame(self) -> None:
        self.framebuffer_rgb24 = self.render_frame()

    def write_control(self, value: int) -> None:
        value &= 0xFF
        if self.first_control is None:
            self.first_control = value
            return

        first = self.first_control
        self.first_control = None
        if value & 0x80:
            self.registers[value & 0x07] = first
            return

        self.code = 1 if (value & 0x40) else 0
        self.address = (((value & 0x3F) << 8) | first) & 0x3FFF
        if self.code == 0:
            self.read_buffer = self.vram[self.address]
            self.address = (self.address + 1) & 0x3FFF

    def read_control(self) -> int:
        self.first_control = None
        value = self.status & 0xFF
        self.status = 0x00
        self.interrupt_line_asserted = False
        return value

    def write_data(self, value: int) -> None:
        value &= 0xFF
        self.first_control = None
        self.vram[self.address] = value
        self.read_buffer = value
        self.address = (self.address + 1) & 0x3FFF

    def read_data(self) -> int:
        self.first_control = None
        value = self.read_buffer
        self.read_buffer = self.vram[self.address]
        self.address = (self.address + 1) & 0x3FFF
        return value & 0xFF

    def _display_enabled(self) -> bool:
        return (self.registers[1] & 0x40) != 0

    def _name_table_base(self) -> int:
        return ((self.registers[2] & 0x0F) << 10) & 0x3FFF

    def _color_table_base(self) -> int:
        return ((self.registers[3] & 0xFF) << 6) & 0x3FFF

    def _pattern_table_base(self) -> int:
        return ((self.registers[4] & 0x07) << 11) & 0x3FFF

    def _graphics2_color_base(self) -> int:
        return self._color_table_base() & 0x2000

    def _graphics2_pattern_base(self) -> int:
        return self._pattern_table_base() & 0x2000

    def _sprite_attribute_base(self) -> int:
        return ((self.registers[5] & 0x7F) << 7) & 0x3FFF

    def _sprite_pattern_base(self) -> int:
        return ((self.registers[6] & 0x07) << 11) & 0x3FFF

    def _backdrop_color(self) -> int:
        return (self.registers[7] >> 4) & 0x0F

    def _text_colors(self) -> tuple[int, int]:
        return (self.registers[7] & 0x0F, (self.registers[7] >> 4) & 0x0F)

    def _mode(self) -> str:
        text = bool(self.registers[1] & 0x10)
        graphics2 = bool(self.registers[0] & 0x02)
        multicolor = bool(self.registers[1] & 0x08)
        if text and not graphics2 and not multicolor:
            return "text"
        if graphics2 and not text and not multicolor:
            return "graphics2"
        if multicolor and not text and not graphics2:
            return "multicolor"
        return "graphics1"

    def _palette_color(self, index: int) -> tuple[int, int, int]:
        return self.PALETTE[index & 0x0F]

    def _fill_backdrop(self) -> bytearray:
        rgb = self._palette_color(self._backdrop_color())
        return bytearray(bytes(rgb) * (self.FRAME_WIDTH * self.FRAME_HEIGHT))

    def _set_pixel(self, out: bytearray, x: int, y: int, color: int) -> None:
        cdef tuple rgb
        cdef int offset
        if not (0 <= x < self.FRAME_WIDTH and 0 <= y < self.FRAME_HEIGHT):
            return
        rgb = self._palette_color(color)
        offset = (y * self.FRAME_WIDTH + x) * 3
        out[offset] = rgb[0]
        out[offset + 1] = rgb[1]
        out[offset + 2] = rgb[2]

    def _render_graphics1(self, out: bytearray) -> None:
        cdef int name_base = self._name_table_base()
        cdef int color_base = self._color_table_base()
        cdef int pattern_base = self._pattern_table_base()
        cdef int backdrop = self._backdrop_color()
        cdef int y, name_row, line_name_addr, tile_row, tile_x, tile, color, fg, bg, pattern, col, x, bit, bg_color
        cdef int sprite_color
        for y in range(self.FRAME_HEIGHT):
            sprite_buffer = self._find_sprites_on_line(y)
            name_row = y // 8
            line_name_addr = (name_base + name_row * 32) & 0x3FFF
            tile_row = y % 8
            for tile_x in range(32):
                tile = self.vram[(line_name_addr + tile_x) & 0x3FFF]
                color = self.vram[(color_base + (tile >> 3)) & 0x3FFF]
                fg = (color >> 4) & 0x0F
                bg = color & 0x0F
                pattern = self.vram[(pattern_base + tile * 8 + tile_row) & 0x3FFF]
                for col in range(8):
                    x = tile_x * 8 + col
                    sprite_color = self._resolve_sprite_color(sprite_buffer, y, x)
                    if sprite_color:
                        self._set_pixel(out, x, y, sprite_color)
                        continue
                    bit = 7 - col
                    bg_color = fg if ((pattern >> bit) & 1) else bg
                    self._set_pixel(out, x, y, bg_color if bg_color else backdrop)

    def _render_graphics2(self, out: bytearray) -> None:
        cdef int name_base = self._name_table_base()
        cdef int color_base = self._graphics2_color_base()
        cdef int pattern_base = self._graphics2_pattern_base()
        cdef int backdrop = self._backdrop_color()
        cdef int y, name_row, line_name_addr, table_offset, tile_row, tile_x, tile, pattern, color, fg, bg, col, x, bit, bg_color
        cdef int sprite_color
        for y in range(self.FRAME_HEIGHT):
            sprite_buffer = self._find_sprites_on_line(y)
            name_row = y // 8
            line_name_addr = (name_base + name_row * 32) & 0x3FFF
            table_offset = 0x1000 if name_row >= 16 else (0x0800 if name_row >= 8 else 0x0000)
            tile_row = y % 8
            for tile_x in range(32):
                tile = self.vram[(line_name_addr + tile_x) & 0x3FFF]
                pattern = self.vram[(pattern_base + table_offset + tile * 8 + tile_row) & 0x3FFF]
                color = self.vram[(color_base + table_offset + tile * 8 + tile_row) & 0x3FFF]
                fg = (color >> 4) & 0x0F
                bg = color & 0x0F
                for col in range(8):
                    x = tile_x * 8 + col
                    sprite_color = self._resolve_sprite_color(sprite_buffer, y, x)
                    if sprite_color:
                        self._set_pixel(out, x, y, sprite_color)
                        continue
                    bit = 7 - col
                    bg_color = fg if ((pattern >> bit) & 1) else bg
                    self._set_pixel(out, x, y, bg_color if bg_color else backdrop)

    def _render_text(self, out: bytearray) -> None:
        cdef int name_base = self._name_table_base()
        cdef int pattern_base = self._pattern_table_base()
        cdef int fg, bg
        cdef int left_border = 8
        cdef int row, col, tile, char_row, pattern, y, char_col, bit, palette_index
        fg, bg = self._text_colors()
        for row in range(24):
            for col in range(40):
                tile = self.vram[(name_base + row * 40 + col) & 0x3FFF]
                for char_row in range(8):
                    pattern = self.vram[(pattern_base + tile * 8 + char_row) & 0x3FFF]
                    y = row * 8 + char_row
                    for char_col in range(6):
                        bit = 7 - char_col
                        palette_index = fg if ((pattern >> bit) & 1) else bg
                        self._set_pixel(out, left_border + col * 6 + char_col, y, palette_index)

    def _render_multicolor(self, out: bytearray) -> None:
        cdef int name_base = self._name_table_base()
        cdef int pattern_base = self._pattern_table_base()
        cdef int backdrop = self._backdrop_color()
        cdef int y, name_row, line_name_addr, pattern_y, tile_x, tile, colors, left, right, col, x, bg_color
        cdef int sprite_color
        for y in range(self.FRAME_HEIGHT):
            sprite_buffer = self._find_sprites_on_line(y)
            name_row = y // 8
            line_name_addr = (name_base + name_row * 32) & 0x3FFF
            pattern_y = (y // 4) % 8
            for tile_x in range(32):
                tile = self.vram[(line_name_addr + tile_x) & 0x3FFF]
                colors = self.vram[(pattern_base + tile * 8 + pattern_y) & 0x3FFF]
                left = (colors >> 4) & 0x0F
                right = colors & 0x0F
                for col in range(8):
                    x = tile_x * 8 + col
                    sprite_color = self._resolve_sprite_color(sprite_buffer, y, x)
                    if sprite_color:
                        self._set_pixel(out, x, y, sprite_color)
                        continue
                    bg_color = left if col < 4 else right
                    self._set_pixel(out, x, y, bg_color if bg_color else backdrop)

    def _find_sprites_on_line(self, y: int):
        cdef int sat_base = self._sprite_attribute_base()
        cdef bint large_sprites = bool(self.registers[1] & 0x02)
        cdef bint magnify = bool(self.registers[1] & 0x01)
        cdef int sprite_size = 8 << (int(large_sprites) + int(magnify))
        cdef list sprites = []
        cdef int sprite_index, attr, sprite_y, sprite_bottom, sprite_x, pattern, attributes, color
        cdef bint in_range
        for sprite_index in range(32):
            attr = (sat_base + sprite_index * 4) & 0x3FFF
            sprite_y = self.vram[attr]
            if sprite_y == 0xD0:
                break
            sprite_bottom = (sprite_y + sprite_size) & 0xFF
            in_range = (
                sprite_y <= y < sprite_bottom
                if sprite_y < sprite_bottom
                else (y >= sprite_y or y < sprite_bottom)
            )
            if not in_range:
                continue
            if len(sprites) == 4:
                if (self.status & 0x40) == 0:
                    self.status = (self.status & 0xA0) | 0x40 | (sprite_index & 0x1F)
                break
            sprite_x = self.vram[(attr + 1) & 0x3FFF]
            pattern = self.vram[(attr + 2) & 0x3FFF]
            attributes = self.vram[(attr + 3) & 0x3FFF]
            color = attributes & 0x0F
            if color == 0:
                continue
            sprites.append((sprite_y, sprite_x, pattern, color, bool(attributes & 0x80)))
        return sprites

    def _resolve_sprite_color(self, sprites, int y, int x) -> int:
        cdef int pattern_base = self._sprite_pattern_base()
        cdef bint large_sprites = bool(self.registers[1] & 0x02)
        cdef bint magnify = bool(self.registers[1] & 0x01)
        cdef int sprite_size = 8 << (int(large_sprites) + int(magnify))
        cdef int found_color = 0
        cdef int sprite_y, sprite_x, pattern, color, actual_x, sprite_row, sprite_col, pattern_mask, pattern_addr, sprite_pattern
        cdef bint early_clock
        for sprite_y, sprite_x, pattern, color, early_clock in sprites:
            actual_x = sprite_x - 32 if early_clock else sprite_x
            if not (actual_x <= x < actual_x + sprite_size):
                continue
            sprite_row = (y - sprite_y) & 0xFF
            sprite_col = x - actual_x
            if magnify:
                sprite_row >>= 1
                sprite_col >>= 1
            pattern_mask = 0xFC if large_sprites else 0xFF
            pattern_addr = pattern_base + 8 * (pattern & pattern_mask) + (sprite_row % 8)
            if sprite_row >= 8:
                pattern_addr += 8
            if sprite_col >= 8:
                pattern_addr += 16
            sprite_pattern = self.vram[pattern_addr & 0x3FFF]
            if ((sprite_pattern >> (7 - (sprite_col % 8))) & 1) == 0:
                continue
            if found_color != 0:
                self.status |= 0x20
                return found_color
            found_color = color
        return found_color

    def _latch_sprite_status_for_frame(self) -> None:
        cdef int y, x
        cdef list sprites
        if not self._display_enabled():
            return
        for y in range(self.FRAME_HEIGHT):
            sprites = self._find_sprites_on_line(y)
            if (self.status & 0x20) != 0:
                continue
            for x in range(self.FRAME_WIDTH):
                self._resolve_sprite_color(sprites, y, x)
                if (self.status & 0x20) != 0:
                    break

    def render_frame(self) -> bytes:
        out = self._fill_backdrop()
        if not self._display_enabled():
            return bytes(out)

        mode = self._mode()
        if mode == "graphics2":
            self._render_graphics2(out)
        elif mode == "text":
            self._render_text(out)
        elif mode == "multicolor":
            self._render_multicolor(out)
        else:
            self._render_graphics1(out)
        return bytes(out)

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "TMS9918A"},
            "status": self.status,
            "address": self.address,
            "read_buffer": self.read_buffer,
            "first_control": self.first_control,
            "code": self.code,
            "interrupt_fired": self.interrupt_fired,
            "interrupt_line_asserted": self.interrupt_line_asserted,
            "last_tstates": self.last_tstates,
            "vram": list(self.vram),
            "registers": list(self.registers),
        }

    def write_state(self, state: dict) -> None:
        if "status" in state:
            self.status = int(state["status"]) & 0xFF
        if "address" in state:
            self.address = int(state["address"]) & 0x3FFF
        if "read_buffer" in state:
            self.read_buffer = int(state["read_buffer"]) & 0xFF
        if "first_control" in state:
            value = state["first_control"]
            self.first_control = None if value is None else (int(value) & 0xFF)
        if "code" in state:
            self.code = int(state["code"]) & 0x01
        if "interrupt_fired" in state:
            self.interrupt_fired = bool(state["interrupt_fired"])
        if "interrupt_line_asserted" in state:
            self.interrupt_line_asserted = bool(state["interrupt_line_asserted"])
        if "last_tstates" in state:
            self.last_tstates = int(state["last_tstates"])
        if "vram" in state:
            self.vram[:] = bytes(int(v) & 0xFF for v in state["vram"][: self.VRAM_SIZE]).ljust(self.VRAM_SIZE, b"\x00")
        if "registers" in state:
            self.registers[:] = bytes(int(v) & 0xFF for v in state["registers"][:8]).ljust(8, b"\x00")
        self.framebuffer_rgb24 = self.render_frame()
