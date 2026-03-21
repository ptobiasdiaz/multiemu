# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from cpu.z80.memory cimport RAMBlock


cpdef list build_horizontal_display_map(
    int total_raster_width,
    int pixels_per_char,
    int horizontal_total,
    int visible_char_count,
    int display_start_char,
):
    cdef list mapping = [-1] * max(0, total_raster_width)
    cdef int raster_x
    cdef int crtc_char
    cdef int pixel_in_char
    cdef int display_char
    cdef int delta

    if total_raster_width <= 0 or pixels_per_char <= 0 or horizontal_total <= 0 or visible_char_count <= 0:
        return mapping

    for raster_x in range(total_raster_width):
        crtc_char = raster_x // pixels_per_char
        pixel_in_char = raster_x % pixels_per_char
        if crtc_char < 0 or crtc_char >= horizontal_total:
            continue
        delta = crtc_char - display_start_char
        display_char = delta % horizontal_total
        if display_char < 0:
            display_char += horizontal_total
        if display_char >= visible_char_count:
            continue
        mapping[raster_x] = (display_char * pixels_per_char) + pixel_in_char
    return mapping


cpdef list build_vertical_display_map(
    int frame_scanline_count,
    int raster_height,
    int visible_raster_height,
    int vertical_total,
    int vertical_total_adjust,
    int visible_row_count,
    int display_start_row,
    int vsync_start,
    int vsync_height,
):
    cdef list mapping = [-1] * max(0, frame_scanline_count)
    cdef int vsync_end
    cdef int row_limit
    cdef int scanline
    cdef int adjust_scanline
    cdef int crtc_row
    cdef int raster
    cdef int display_row
    cdef int delta

    if (
        frame_scanline_count <= 0
        or raster_height <= 0
        or visible_raster_height <= 0
        or vertical_total <= 0
        or visible_row_count <= 0
    ):
        return mapping

    vsync_end = frame_scanline_count
    if vsync_start + vsync_height < vsync_end:
        vsync_end = vsync_start + vsync_height
    row_limit = vertical_total * raster_height

    for scanline in range(frame_scanline_count):
        if scanline >= vsync_start and scanline < vsync_end:
            continue

        if scanline < row_limit:
            crtc_row = scanline // raster_height
            raster = scanline % raster_height
        else:
            adjust_scanline = scanline - row_limit
            if adjust_scanline >= vertical_total_adjust:
                continue
            crtc_row = vertical_total - 1
            raster = raster_height + adjust_scanline

        if raster >= visible_raster_height:
            continue

        delta = crtc_row - display_start_row
        display_row = delta % vertical_total
        if display_row < 0:
            display_row += vertical_total
        if display_row >= visible_row_count:
            continue

        mapping[scanline] = (display_row * visible_raster_height) + raster

    return mapping


cpdef list compose_display_row(
    list row_bytes,
    list horizontal_map,
    int raster_origin_x,
    int frame_width,
    tuple border_rgb,
    int mode,
    list pen_rgb_map,
):
    cdef list row = [border_rgb] * max(0, frame_width)
    cdef int pixels_per_byte
    cdef int dst_x
    cdef int display_pixel
    cdef int raster_x
    cdef int byte_index
    cdef int pixel_index
    cdef int value
    cdef int pen

    if not row_bytes or not horizontal_map or frame_width <= 0:
        return row

    if mode == 0:
        pixels_per_byte = 4
    elif mode == 2:
        pixels_per_byte = 8
    else:
        pixels_per_byte = 4

    for dst_x in range(frame_width):
        raster_x = dst_x - raster_origin_x
        display_pixel = horizontal_map[raster_x] if 0 <= raster_x < len(horizontal_map) else -1
        if display_pixel < 0:
            continue

        byte_index = display_pixel // pixels_per_byte
        if byte_index < 0 or byte_index >= len(row_bytes):
            continue

        value = row_bytes[byte_index]
        pixel_index = display_pixel % pixels_per_byte

        if mode == 0:
            if (pixel_index >> 1) == 0:
                pen = ((value >> 7) & 1) | (((value >> 3) & 1) << 1) | (((value >> 5) & 1) << 2) | (((value >> 1) & 1) << 3)
            else:
                pen = ((value >> 6) & 1) | (((value >> 2) & 1) << 1) | (((value >> 4) & 1) << 2) | ((value & 1) << 3)
        elif mode == 2:
            pen = (value >> (7 - pixel_index)) & 1
        else:
            if pixel_index == 0:
                pen = (((value >> 7) & 1) << 1) | ((value >> 3) & 1)
            elif pixel_index == 1:
                pen = (((value >> 6) & 1) << 1) | ((value >> 2) & 1)
            elif pixel_index == 2:
                pen = (((value >> 5) & 1) << 1) | ((value >> 1) & 1)
            else:
                pen = (((value >> 4) & 1) << 1) | (value & 1)

        row[dst_x] = pen_rgb_map[pen & 0x0F]

    return row


cpdef list render_scanline_from_ram(
    RAMBlock ram,
    int display_start_address,
    int char_row,
    int horizontal_displayed,
    int visible_char_count,
    int raster,
    list horizontal_map,
    int raster_origin_x,
    int frame_width,
    tuple border_rgb,
    int mode,
    list pen_rgb_map,
):
    cdef list row = [border_rgb] * max(0, frame_width)
    cdef int pixels_per_byte
    cdef int start_ma
    cdef int dst_x
    cdef int raster_x
    cdef int display_pixel
    cdef int byte_index
    cdef int pixel_index
    cdef int char_index
    cdef int ma
    cdef int char_base
    cdef int value
    cdef int pen

    if frame_width <= 0 or visible_char_count <= 0:
        return row

    if mode == 0:
        pixels_per_byte = 4
    elif mode == 2:
        pixels_per_byte = 8
    else:
        pixels_per_byte = 4

    start_ma = (display_start_address + (char_row * horizontal_displayed)) & 0x3FFF

    for dst_x in range(frame_width):
        raster_x = dst_x - raster_origin_x
        display_pixel = horizontal_map[raster_x] if 0 <= raster_x < len(horizontal_map) else -1
        if display_pixel < 0:
            continue

        byte_index = display_pixel // pixels_per_byte
        char_index = byte_index >> 1
        if char_index < 0 or char_index >= visible_char_count:
            continue

        ma = (start_ma + char_index) & 0x3FFF
        char_base = (((ma & 0x3000) << 2) | ((raster & 0x07) << 11) | ((ma & 0x03FF) << 1)) & 0xFFFF
        value = ram.data[char_base + (byte_index & 1)]
        pixel_index = display_pixel % pixels_per_byte

        if mode == 0:
            if (pixel_index >> 1) == 0:
                pen = ((value >> 7) & 1) | (((value >> 3) & 1) << 1) | (((value >> 5) & 1) << 2) | (((value >> 1) & 1) << 3)
            else:
                pen = ((value >> 6) & 1) | (((value >> 2) & 1) << 1) | (((value >> 4) & 1) << 2) | ((value & 1) << 3)
        elif mode == 2:
            pen = (value >> (7 - pixel_index)) & 1
        else:
            if pixel_index == 0:
                pen = (((value >> 7) & 1) << 1) | ((value >> 3) & 1)
            elif pixel_index == 1:
                pen = (((value >> 6) & 1) << 1) | ((value >> 2) & 1)
            elif pixel_index == 2:
                pen = (((value >> 5) & 1) << 1) | ((value >> 1) & 1)
            else:
                pen = (((value >> 4) & 1) << 1) | (value & 1)

        row[dst_x] = pen_rgb_map[pen & 0x0F]

    return row


cpdef bytes render_frame_rgb24_from_ram(
    RAMBlock ram,
    int display_start_address,
    int horizontal_displayed,
    int visible_char_count,
    int visible_raster_height,
    list horizontal_map,
    list vertical_map,
    int raster_origin_x,
    int total_top,
    int frame_width,
    int frame_height,
    tuple border_rgb,
    int mode,
    list pen_rgb_map,
):
    cdef bytearray out = bytearray(max(0, frame_width * frame_height * 3))
    cdef int border_r
    cdef int border_g
    cdef int border_b
    cdef int i
    cdef int pixels_per_byte
    cdef int dst_y
    cdef int raster_scanline
    cdef int display_scanline
    cdef int char_row
    cdef int raster
    cdef int start_ma
    cdef int row_offset
    cdef int dst_x
    cdef int raster_x
    cdef int display_pixel
    cdef int byte_index
    cdef int char_index
    cdef int ma
    cdef int char_base
    cdef int value
    cdef int pixel_index
    cdef int pen
    cdef tuple rgb
    cdef int out_index

    if frame_width <= 0 or frame_height <= 0:
        return bytes(out)

    border_r = border_rgb[0]
    border_g = border_rgb[1]
    border_b = border_rgb[2]
    for i in range(0, len(out), 3):
        out[i] = border_r
        out[i + 1] = border_g
        out[i + 2] = border_b

    if visible_char_count <= 0 or visible_raster_height <= 0:
        return bytes(out)

    if mode == 0:
        pixels_per_byte = 4
    elif mode == 2:
        pixels_per_byte = 8
    else:
        pixels_per_byte = 4

    for dst_y in range(frame_height):
        raster_scanline = dst_y - total_top
        display_scanline = vertical_map[raster_scanline] if 0 <= raster_scanline < len(vertical_map) else -1
        if display_scanline < 0:
            continue

        char_row = display_scanline // visible_raster_height
        raster = display_scanline % visible_raster_height
        start_ma = (display_start_address + (char_row * horizontal_displayed)) & 0x3FFF
        row_offset = dst_y * frame_width * 3

        for dst_x in range(frame_width):
            raster_x = dst_x - raster_origin_x
            display_pixel = horizontal_map[raster_x] if 0 <= raster_x < len(horizontal_map) else -1
            if display_pixel < 0:
                continue

            byte_index = display_pixel // pixels_per_byte
            char_index = byte_index >> 1
            if char_index < 0 or char_index >= visible_char_count:
                continue

            ma = (start_ma + char_index) & 0x3FFF
            char_base = (((ma & 0x3000) << 2) | ((raster & 0x07) << 11) | ((ma & 0x03FF) << 1)) & 0xFFFF
            value = ram.data[(char_base + (byte_index & 1)) & 0xFFFF]
            pixel_index = display_pixel % pixels_per_byte

            if mode == 0:
                if (pixel_index >> 1) == 0:
                    pen = ((value >> 7) & 1) | (((value >> 3) & 1) << 1) | (((value >> 5) & 1) << 2) | (((value >> 1) & 1) << 3)
                else:
                    pen = ((value >> 6) & 1) | (((value >> 2) & 1) << 1) | (((value >> 4) & 1) << 2) | ((value & 1) << 3)
            elif mode == 2:
                pen = (value >> (7 - pixel_index)) & 1
            else:
                if pixel_index == 0:
                    pen = (((value >> 7) & 1) << 1) | ((value >> 3) & 1)
                elif pixel_index == 1:
                    pen = (((value >> 6) & 1) << 1) | ((value >> 2) & 1)
                elif pixel_index == 2:
                    pen = (((value >> 5) & 1) << 1) | ((value >> 1) & 1)
                else:
                    pen = (((value >> 4) & 1) << 1) | (value & 1)

            rgb = pen_rgb_map[pen & 0x0F]
            out_index = row_offset + (dst_x * 3)
            out[out_index] = rgb[0]
            out[out_index + 1] = rgb[1]
            out[out_index + 2] = rgb[2]

    return bytes(out)
