from __future__ import annotations

from tests.fallbacks.cpc_render_reference import (
    build_horizontal_display_map,
    build_vertical_display_map,
    render_frame_rgb24_from_ram,
)


class CPCVideo:
    """Reference pure-Python CPC video integrator kept only for tests."""

    def __init__(self, machine):
        self.machine = machine
        self._framebuffer_cache = self._make_blank_framebuffer(machine._BLANK_PIXEL)
        self.framebuffer_rgb24 = self._make_blank_framebuffer_rgb24(machine._BLANK_PIXEL)

    @property
    def framebuffer(self):
        if self._framebuffer_cache is not None:
            return self._framebuffer_cache
        if self.framebuffer_rgb24 is None:
            return None
        self._framebuffer_cache = self._decode_framebuffer_rgb24(self.framebuffer_rgb24)
        return self._framebuffer_cache

    @framebuffer.setter
    def framebuffer(self, value):
        self._framebuffer_cache = value

    @property
    def crtc(self):
        return self.machine.crtc

    @property
    def gate_array(self):
        return self.machine.gate_array

    @property
    def ram(self):
        return self.machine.ram

    @property
    def frame_width(self) -> int:
        return self.machine.frame_width

    @property
    def frame_height(self) -> int:
        return self.machine.frame_height

    @property
    def display_profile(self):
        return self.machine.display_profile

    def reset(self) -> None:
        self.framebuffer = self._make_blank_framebuffer(self.machine._BLANK_PIXEL)
        self.framebuffer_rgb24 = self._make_blank_framebuffer_rgb24(self.machine._BLANK_PIXEL)

    def render_frame(self):
        self.framebuffer_rgb24 = self._render_crtc_frame_rgb24()
        self.framebuffer = None
        return self.framebuffer_rgb24

    def _render_crtc_frame_rgb24(self) -> bytes:
        border = self.gate_array.HARDWARE_PALETTE[self.machine.frame_border_hardware_color]
        pen_rgb_map = [self.gate_array.get_pen_rgb(pen) for pen in range(16)]
        total_left, total_top = self._get_total_raster_origin()
        horizontal_map = build_horizontal_display_map(
            self._get_total_raster_width(),
            self._get_pixels_per_character(),
            self.crtc.horizontal_total,
            self._get_visible_char_count(),
            self._get_display_start_char(),
        )
        vertical_map = build_vertical_display_map(
            self._get_frame_scanline_count(),
            self.crtc.raster_height,
            self._get_visible_raster_height(),
            self.crtc.vertical_total,
            self.crtc.vertical_total_adjust,
            self._get_visible_row_count(),
            self._get_display_start_row(),
            self._get_vsync_start_line(),
            self._get_vsync_height(),
        )

        return render_frame_rgb24_from_ram(
            self.ram,
            self.machine.frame_display_start_address,
            self.crtc.horizontal_displayed,
            self._get_visible_char_count(),
            self._get_visible_raster_height(),
            horizontal_map,
            vertical_map,
            total_left,
            total_top,
            self.frame_width,
            self.frame_height,
            border,
            self.machine.frame_gate_mode,
            pen_rgb_map,
        )

    def _get_visible_width(self) -> int:
        chars = self._get_visible_char_count()
        mode = self.gate_array.mode
        if mode == 0:
            return chars * 4
        if mode == 2:
            return chars * 16
        return chars * 8

    def _get_visible_height(self) -> int:
        return self.crtc.vertical_displayed * self._get_visible_raster_height()

    def _get_active_display_origin(self) -> tuple[int, int]:
        total_x, total_y = self._get_total_raster_origin()
        active_x = total_x + self._get_active_x_offset_in_raster()
        active_y = total_y + self._get_active_y_offset_in_raster()
        max_x = max(0, self.frame_width - min(self._get_visible_width(), self.frame_width))
        max_y = max(0, self.frame_height - min(self._get_visible_height(), self.frame_height))
        return (
            max(0, min(max_x, active_x)),
            max(0, min(max_y, active_y)),
        )

    def _get_total_raster_origin(self) -> tuple[int, int]:
        return -self._get_horizontal_raster_view_x(), self._get_vertical_raster_origin()

    def _decode_display_scanline(self, raster_scanline: int) -> tuple[int, int] | None:
        if self._is_vsync_scanline(raster_scanline):
            return None

        crtc_pos = self._decode_crtc_scanline(raster_scanline)
        if crtc_pos is None:
            return None

        crtc_row, raster = crtc_pos
        if raster >= self._get_visible_raster_height():
            return None
        display_row = self._map_crtc_row_to_display_row(crtc_row)
        if display_row is None:
            return None
        return display_row, raster

    def _decode_crtc_scanline(self, scanline: int) -> tuple[int, int] | None:
        if not (0 <= scanline < self._get_frame_scanline_count()):
            return None

        raster_height = self.crtc.raster_height
        row_limit = self.crtc.vertical_total * raster_height
        if scanline < row_limit:
            return scanline // raster_height, scanline % raster_height

        adjust_scanline = scanline - row_limit
        if adjust_scanline < self.crtc.vertical_total_adjust:
            return self.crtc.vertical_total - 1, raster_height + adjust_scanline

        return None

    def _get_frame_scanline_count(self) -> int:
        return max(1, self.crtc.total_scanlines)

    def _get_visible_raster_height(self) -> int:
        return min(self.crtc.raster_height, 8)

    def _get_visible_char_count(self) -> int:
        return min(self.crtc.horizontal_displayed, self.crtc.horizontal_total)

    def _map_crtc_char_to_display_char(self, crtc_char: int) -> int | None:
        if not (0 <= crtc_char < self.crtc.horizontal_total):
            return None

        start_char = self._get_display_start_char()
        display_char = (crtc_char - start_char) % self.crtc.horizontal_total
        if display_char >= self._get_visible_char_count():
            return None
        return display_char

    def _map_raster_x_to_display_pixel(self, raster_x: int) -> int | None:
        if not (0 <= raster_x < self._get_total_raster_width()):
            return None

        pixels_per_char = self._get_pixels_per_character()
        crtc_char = raster_x // pixels_per_char
        pixel_in_char = raster_x % pixels_per_char
        display_char = self._map_crtc_char_to_display_char(crtc_char)
        if display_char is None:
            return None
        return (display_char * pixels_per_char) + pixel_in_char

    def _get_display_start_char(self) -> int:
        return (
            self.crtc.horizontal_sync_position
            - self._get_visible_char_count()
            + self.machine.HORIZONTAL_DISPLAY_OFFSET_CHARS
        ) % self.crtc.horizontal_total

    def _get_visible_row_count(self) -> int:
        return min(self.crtc.vertical_displayed, self.crtc.vertical_total)

    def _get_display_start_row(self) -> int:
        return (
            self.crtc.vertical_sync_position
            - self._get_visible_row_count()
            + self.machine.VERTICAL_DISPLAY_OFFSET_ROWS
        ) % self.crtc.vertical_total

    def _map_crtc_row_to_display_row(self, crtc_row: int) -> int | None:
        if not (0 <= crtc_row < self.crtc.vertical_total):
            return None

        start_row = self._get_display_start_row()
        display_row = (crtc_row - start_row) % self.crtc.vertical_total
        if display_row >= self._get_visible_row_count():
            return None
        return display_row

    def _map_raster_y_to_display_scanline(self, raster_scanline: int) -> int | None:
        crtc_pos = self._decode_crtc_scanline(raster_scanline)
        if crtc_pos is None:
            return None

        crtc_row, raster = crtc_pos
        if raster >= self._get_visible_raster_height():
            return None
        display_row = self._map_crtc_row_to_display_row(crtc_row)
        if display_row is None:
            return None
        return (display_row * self._get_visible_raster_height()) + raster

    def _get_vsync_start_line(self) -> int:
        return min(
            self._get_frame_scanline_count() - 1,
            (self.crtc.vertical_sync_position % self.crtc.vertical_total) * self.crtc.raster_height,
        )

    def _get_vsync_height(self) -> int:
        return min(self._get_frame_scanline_count(), self.crtc.vertical_sync_width)

    def _is_vsync_scanline(self, scanline: int) -> bool:
        start = self._get_vsync_start_line()
        end = min(self._get_frame_scanline_count(), start + self._get_vsync_height())
        return start <= scanline < end

    def _get_pixels_per_character(self) -> int:
        mode = self.gate_array.mode
        if mode == 0:
            return 4
        if mode == 2:
            return 16
        return 8

    def _get_total_raster_width(self) -> int:
        return max(1, self.crtc.horizontal_total * self._get_pixels_per_character())

    def _get_total_raster_height(self) -> int:
        return max(1, self._get_frame_scanline_count())

    def _get_vertical_raster_origin(self) -> int:
        origin = (self.frame_height - self._get_total_raster_height()) // 2
        if self.display_profile.cpc_raster_shift_y is not None:
            origin += self.display_profile.cpc_raster_shift_y
        return origin

    def _get_horizontal_raster_view_x(self) -> int:
        if self.display_profile.cpc_raster_view_x is not None:
            return self.display_profile.cpc_raster_view_x

        total_width = self._get_total_raster_width()
        if total_width <= self.frame_width:
            return 0
        return (total_width - self.frame_width) // 2

    def _make_blank_framebuffer(self, rgb: tuple[int, int, int]):
        return tuple(tuple(rgb for _ in range(self.frame_width)) for _ in range(self.frame_height))

    def _make_blank_framebuffer_rgb24(self, rgb: tuple[int, int, int]) -> bytes:
        return bytes(rgb) * (self.frame_width * self.frame_height)

    def _decode_framebuffer_rgb24(self, packed: bytes):
        if not packed:
            return self._make_blank_framebuffer(self.machine._BLANK_PIXEL)

        rows = []
        stride = self.frame_width * 3
        for y in range(self.frame_height):
            row_start = y * stride
            row = []
            for x in range(self.frame_width):
                pixel = row_start + (x * 3)
                row.append((packed[pixel], packed[pixel + 1], packed[pixel + 2]))
            rows.append(tuple(row))
        return tuple(rows)

    def _get_video_bytes_per_row(self) -> int:
        return self._get_visible_char_count() * 2

    def _get_display_row_bytes(
        self,
        char_row: int,
        raster: int,
        *,
        display_start_address: int | None = None,
    ) -> list[int]:
        start_ma = (
            (self.crtc.display_start_address if display_start_address is None else display_start_address)
            + (char_row * self.crtc.horizontal_displayed)
        ) & 0x3FFF
        row_bytes: list[int] = []
        for char_index in range(self._get_visible_char_count()):
            char_base = self._map_crtc_address_to_ram((start_ma + char_index) & 0x3FFF, raster)
            row_bytes.append(self.ram.peek(char_base & 0xFFFF))
            row_bytes.append(self.ram.peek((char_base + 1) & 0xFFFF))
        return row_bytes

    def _get_display_line_base_address(
        self,
        char_row: int,
        raster: int,
        *,
        display_start_address: int | None = None,
    ) -> int:
        line_ma = (
            (self.crtc.display_start_address if display_start_address is None else display_start_address)
            + (char_row * self.crtc.horizontal_displayed)
        ) & 0x3FFF
        return self._map_crtc_address_to_ram(line_ma, raster)

    def _map_crtc_address_to_ram(self, ma: int, raster: int) -> int:
        ma &= 0x3FFF
        raster &= 0x07
        return (((ma & 0x3000) << 2) | ((raster & 0x07) << 11) | ((ma & 0x03FF) << 1)) & 0xFFFF

    def _get_active_x_offset_in_raster(self) -> int:
        return self._get_display_start_char() * self._get_pixels_per_character()

    def _get_active_y_offset_in_raster(self) -> int:
        return self._get_display_start_row() * self.crtc.raster_height

    def _get_hsync_pixel_range(self) -> tuple[int, int]:
        pixels_per_char = self._get_pixels_per_character()
        start = self.crtc.horizontal_sync_position * pixels_per_char
        end = start + (self.crtc.horizontal_sync_width * pixels_per_char)
        return start, end

    def _get_line_display_start_address(self, raster_scanline: int) -> int:
        if 0 <= raster_scanline < len(self.machine.line_display_start_addresses):
            return self.machine.line_display_start_addresses[raster_scanline]
        return self.crtc.display_start_address

    def _get_line_gate_mode(self, raster_scanline: int) -> int:
        if 0 <= raster_scanline < len(self.machine.line_gate_modes):
            return self.machine.line_gate_modes[raster_scanline]
        return self.gate_array.mode

    def _get_line_border_rgb(self, raster_scanline: int) -> tuple[int, int, int]:
        if 0 <= raster_scanline < len(self.machine.line_border_colours):
            return self.gate_array.HARDWARE_PALETTE[self.machine.line_border_colours[raster_scanline]]
        return self.gate_array.get_border_rgb()

    def _decode_video_byte(self, value: int, *, mode: int | None = None) -> list[tuple[int, int, int]]:
        mode = self.gate_array.mode if mode is None else mode

        if mode == 0:
            pens = [
                ((value >> 7) & 1) | (((value >> 3) & 1) << 1) | (((value >> 5) & 1) << 2) | (((value >> 1) & 1) << 3),
                ((value >> 6) & 1) | (((value >> 2) & 1) << 1) | (((value >> 4) & 1) << 2) | ((value & 1) << 3),
            ]
            return [self.gate_array.get_pen_rgb(pen) for pen in pens]

        if mode == 2:
            return [self.gate_array.get_pen_rgb((value >> bit) & 1) for bit in range(7, -1, -1)]

        pens = [
            (((value >> 7) & 1) << 1) | ((value >> 3) & 1),
            (((value >> 6) & 1) << 1) | ((value >> 2) & 1),
            (((value >> 5) & 1) << 1) | ((value >> 1) & 1),
            (((value >> 4) & 1) << 1) | (value & 1),
        ]
        return [self.gate_array.get_pen_rgb(pen) for pen in pens]
