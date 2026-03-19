# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from devices.cpc_render import (
    build_horizontal_display_map,
    build_vertical_display_map,
    render_frame_rgb24_from_ram,
)


cdef class CPCVideo:
    cdef public object machine
    cdef public object framebuffer_rgb24

    def __init__(self, machine):
        self.machine = machine
        self.framebuffer_rgb24 = self._make_blank_framebuffer_rgb24(machine._BLANK_PIXEL)

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
    def frame_width(self):
        return self.machine.frame_width

    @property
    def frame_height(self):
        return self.machine.frame_height

    @property
    def display_profile(self):
        return self.machine.display_profile

    cpdef reset(self):
        self.framebuffer_rgb24 = self._make_blank_framebuffer_rgb24(self.machine._BLANK_PIXEL)

    cpdef render_frame(self):
        self.framebuffer_rgb24 = self._render_crtc_frame_rgb24()
        return self.framebuffer_rgb24

    cdef bytes _render_crtc_frame_rgb24(self):
        cdef tuple border = self.gate_array.HARDWARE_PALETTE[self.machine.frame_border_hardware_color]
        cdef list pen_rgb_map = []
        cdef int pen
        cdef tuple origin = self._get_total_raster_origin()
        cdef int total_left = origin[0]
        cdef int total_top = origin[1]
        for pen in range(16):
            pen_rgb_map.append(self.gate_array.get_pen_rgb(pen))
        cdef list horizontal_map = build_horizontal_display_map(
            self._get_total_raster_width(),
            self._get_pixels_per_character(),
            self.crtc.horizontal_total,
            self._get_visible_char_count(),
            self._get_display_start_char(),
        )
        cdef list vertical_map = build_vertical_display_map(
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

    cpdef int _get_visible_width(self):
        cdef int chars = self._get_visible_char_count()
        cdef int mode = self.gate_array.mode
        if mode == 0:
            return chars * 4
        if mode == 2:
            return chars * 16
        return chars * 8

    cpdef int _get_visible_height(self):
        return self.crtc.vertical_displayed * self._get_visible_raster_height()

    cpdef tuple _get_active_display_origin(self):
        cdef tuple total = self._get_total_raster_origin()
        cdef int total_x = total[0]
        cdef int total_y = total[1]
        cdef int active_x = total_x + self._get_active_x_offset_in_raster()
        cdef int active_y = total_y + self._get_active_y_offset_in_raster()
        cdef int max_x = max(0, self.frame_width - min(self._get_visible_width(), self.frame_width))
        cdef int max_y = max(0, self.frame_height - min(self._get_visible_height(), self.frame_height))
        return (
            max(0, min(max_x, active_x)),
            max(0, min(max_y, active_y)),
        )

    cpdef tuple _get_total_raster_origin(self):
        return -self._get_horizontal_raster_view_x(), self._get_vertical_raster_origin()

    cpdef _decode_display_scanline(self, int raster_scanline):
        cdef object crtc_pos
        cdef int crtc_row
        cdef int raster
        cdef object display_row

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

    cpdef _decode_crtc_scanline(self, int scanline):
        cdef int raster_height
        cdef int row_limit
        cdef int adjust_scanline

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

    cpdef int _get_frame_scanline_count(self):
        return max(1, self.crtc.total_scanlines)

    cpdef int _get_visible_raster_height(self):
        return min(self.crtc.raster_height, 8)

    cpdef int _get_visible_char_count(self):
        return min(self.crtc.horizontal_displayed, self.crtc.horizontal_total)

    cpdef _map_crtc_char_to_display_char(self, int crtc_char):
        cdef int start_char
        cdef int display_char

        if not (0 <= crtc_char < self.crtc.horizontal_total):
            return None

        start_char = self._get_display_start_char()
        display_char = (crtc_char - start_char) % self.crtc.horizontal_total
        if display_char >= self._get_visible_char_count():
            return None
        return display_char

    cpdef _map_raster_x_to_display_pixel(self, int raster_x):
        cdef int pixels_per_char
        cdef int crtc_char
        cdef int pixel_in_char
        cdef object display_char

        if not (0 <= raster_x < self._get_total_raster_width()):
            return None

        pixels_per_char = self._get_pixels_per_character()
        crtc_char = raster_x // pixels_per_char
        pixel_in_char = raster_x % pixels_per_char
        display_char = self._map_crtc_char_to_display_char(crtc_char)
        if display_char is None:
            return None
        return (display_char * pixels_per_char) + pixel_in_char

    cpdef int _get_display_start_char(self):
        return (
            self.crtc.horizontal_sync_position
            - self._get_visible_char_count()
            + self.machine.HORIZONTAL_DISPLAY_OFFSET_CHARS
        ) % self.crtc.horizontal_total

    cpdef int _get_visible_row_count(self):
        return min(self.crtc.vertical_displayed, self.crtc.vertical_total)

    cpdef int _get_display_start_row(self):
        return (
            self.crtc.vertical_sync_position
            - self._get_visible_row_count()
            + self.machine.VERTICAL_DISPLAY_OFFSET_ROWS
        ) % self.crtc.vertical_total

    cpdef _map_crtc_row_to_display_row(self, int crtc_row):
        cdef int start_row
        cdef int display_row

        if not (0 <= crtc_row < self.crtc.vertical_total):
            return None

        start_row = self._get_display_start_row()
        display_row = (crtc_row - start_row) % self.crtc.vertical_total
        if display_row >= self._get_visible_row_count():
            return None
        return display_row

    cpdef _map_raster_y_to_display_scanline(self, int raster_scanline):
        cdef object crtc_pos
        cdef int crtc_row
        cdef int raster
        cdef object display_row

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

    cpdef int _get_vsync_start_line(self):
        return min(
            self._get_frame_scanline_count() - 1,
            (self.crtc.vertical_sync_position % self.crtc.vertical_total) * self.crtc.raster_height,
        )

    cpdef int _get_vsync_height(self):
        return min(self._get_frame_scanline_count(), self.crtc.vertical_sync_width)

    cpdef bint _is_vsync_scanline(self, int scanline):
        cdef int start = self._get_vsync_start_line()
        cdef int end = min(self._get_frame_scanline_count(), start + self._get_vsync_height())
        return start <= scanline < end

    cpdef int _get_pixels_per_character(self):
        cdef int mode = self.gate_array.mode
        if mode == 0:
            return 4
        if mode == 2:
            return 16
        return 8

    cpdef int _get_total_raster_width(self):
        return max(1, self.crtc.horizontal_total * self._get_pixels_per_character())

    cpdef int _get_total_raster_height(self):
        return max(1, self._get_frame_scanline_count())

    cpdef int _get_vertical_raster_origin(self):
        cdef int origin = (self.frame_height - self._get_total_raster_height()) // 2
        if self.display_profile.cpc_raster_shift_y is not None:
            origin += self.display_profile.cpc_raster_shift_y
        return origin

    cpdef int _get_horizontal_raster_view_x(self):
        cdef int total_width

        if self.display_profile.cpc_raster_view_x is not None:
            return self.display_profile.cpc_raster_view_x

        total_width = self._get_total_raster_width()
        if total_width <= self.frame_width:
            return 0
        return (total_width - self.frame_width) // 2

    cpdef bytes _make_blank_framebuffer_rgb24(self, tuple rgb):
        return bytes(rgb) * (self.frame_width * self.frame_height)

    cpdef int _get_video_bytes_per_row(self):
        return self._get_visible_char_count() * 2

    cpdef list _get_display_row_bytes(self, int char_row, int raster, display_start_address=None):
        cdef int start_ma = (
            (self.crtc.display_start_address if display_start_address is None else display_start_address)
            + (char_row * self.crtc.horizontal_displayed)
        ) & 0x3FFF
        cdef list row_bytes = []
        cdef int char_index
        cdef int char_base
        for char_index in range(self._get_visible_char_count()):
            char_base = self._map_crtc_address_to_ram((start_ma + char_index) & 0x3FFF, raster)
            row_bytes.append(self.ram.peek(char_base & 0xFFFF))
            row_bytes.append(self.ram.peek((char_base + 1) & 0xFFFF))
        return row_bytes

    cpdef int _get_display_line_base_address(self, int char_row, int raster, display_start_address=None):
        cdef int line_ma = (
            (self.crtc.display_start_address if display_start_address is None else display_start_address)
            + (char_row * self.crtc.horizontal_displayed)
        ) & 0x3FFF
        return self._map_crtc_address_to_ram(line_ma, raster)

    cpdef int _map_crtc_address_to_ram(self, int ma, int raster):
        ma &= 0x3FFF
        raster &= 0x07
        return (((ma & 0x3000) << 2) | ((raster & 0x07) << 11) | ((ma & 0x03FF) << 1)) & 0xFFFF

    cpdef int _get_active_x_offset_in_raster(self):
        return self._get_display_start_char() * self._get_pixels_per_character()

    cpdef int _get_active_y_offset_in_raster(self):
        return self._get_display_start_row() * self.crtc.raster_height

    cpdef tuple _get_hsync_pixel_range(self):
        cdef int pixels_per_char = self._get_pixels_per_character()
        cdef int start = self.crtc.horizontal_sync_position * pixels_per_char
        cdef int end = start + (self.crtc.horizontal_sync_width * pixels_per_char)
        return start, end

    cpdef int _get_line_display_start_address(self, int raster_scanline):
        if 0 <= raster_scanline < len(self.machine.line_display_start_addresses):
            return self.machine.line_display_start_addresses[raster_scanline]
        return self.crtc.display_start_address

    cpdef int _get_line_gate_mode(self, int raster_scanline):
        if 0 <= raster_scanline < len(self.machine.line_gate_modes):
            return self.machine.line_gate_modes[raster_scanline]
        return self.gate_array.mode

    cpdef tuple _get_line_border_rgb(self, int raster_scanline):
        if 0 <= raster_scanline < len(self.machine.line_border_colours):
            return self.gate_array.HARDWARE_PALETTE[self.machine.line_border_colours[raster_scanline]]
        return self.gate_array.get_border_rgb()

    cpdef list _decode_video_byte(self, int value, mode=None):
        cdef list pixels
        cdef int bit
        if mode is None:
            mode = self.gate_array.mode

        if mode == 0:
            return [
                self.gate_array.get_pen_rgb(((value >> 7) & 1) | (((value >> 3) & 1) << 1) | (((value >> 5) & 1) << 2) | (((value >> 1) & 1) << 3)),
                self.gate_array.get_pen_rgb(((value >> 6) & 1) | (((value >> 2) & 1) << 1) | (((value >> 4) & 1) << 2) | ((value & 1) << 3)),
            ]

        if mode == 2:
            pixels = []
            for bit in range(7, -1, -1):
                pixels.append(self.gate_array.get_pen_rgb((value >> bit) & 1))
            return pixels

        return [
            self.gate_array.get_pen_rgb((((value >> 7) & 1) << 1) | ((value >> 3) & 1)),
            self.gate_array.get_pen_rgb((((value >> 6) & 1) << 1) | ((value >> 2) & 1)),
            self.gate_array.get_pen_rgb((((value >> 5) & 1) << 1) | ((value >> 1) & 1)),
            self.gate_array.get_pen_rgb((((value >> 4) & 1) << 1) | (value & 1)),
        ]


AmstradCPCVideo = CPCVideo
