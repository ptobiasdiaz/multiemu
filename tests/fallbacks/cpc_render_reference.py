from __future__ import annotations


def build_horizontal_display_map(
    total_raster_width: int,
    pixels_per_char: int,
    horizontal_total: int,
    visible_char_count: int,
    display_start_char: int,
) -> list[int]:
    mapping = [-1] * max(0, total_raster_width)
    if total_raster_width <= 0 or pixels_per_char <= 0 or horizontal_total <= 0 or visible_char_count <= 0:
        return mapping

    for raster_x in range(total_raster_width):
        crtc_char = raster_x // pixels_per_char
        pixel_in_char = raster_x % pixels_per_char
        if not (0 <= crtc_char < horizontal_total):
            continue
        display_char = (crtc_char - display_start_char) % horizontal_total
        if display_char >= visible_char_count:
            continue
        mapping[raster_x] = (display_char * pixels_per_char) + pixel_in_char
    return mapping


def build_vertical_display_map(
    frame_scanline_count: int,
    raster_height: int,
    visible_raster_height: int,
    vertical_total: int,
    vertical_total_adjust: int,
    visible_row_count: int,
    display_start_row: int,
    vsync_start: int,
    vsync_height: int,
) -> list[int]:
    mapping = [-1] * max(0, frame_scanline_count)
    if (
        frame_scanline_count <= 0
        or raster_height <= 0
        or visible_raster_height <= 0
        or vertical_total <= 0
        or visible_row_count <= 0
    ):
        return mapping

    vsync_end = min(frame_scanline_count, vsync_start + max(0, vsync_height))
    row_limit = vertical_total * raster_height

    for scanline in range(frame_scanline_count):
        if vsync_start <= scanline < vsync_end:
            continue

        if scanline < row_limit:
            crtc_row = scanline // raster_height
            raster = scanline % raster_height
        else:
            adjust_scanline = scanline - row_limit
            if adjust_scanline >= max(0, vertical_total_adjust):
                continue
            crtc_row = vertical_total - 1
            raster = raster_height + adjust_scanline

        if raster >= visible_raster_height:
            continue

        display_row = (crtc_row - display_start_row) % vertical_total
        if display_row >= visible_row_count:
            continue

        mapping[scanline] = (display_row * visible_raster_height) + raster

    return mapping


def compose_display_row(
    row_bytes: list[int],
    horizontal_map: list[int],
    raster_origin_x: int,
    frame_width: int,
    border_rgb: tuple[int, int, int],
    mode: int,
    pen_rgb_map: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    row = [border_rgb] * max(0, frame_width)
    if not row_bytes or not horizontal_map or frame_width <= 0:
        return row

    if mode == 0:
        pixels_per_byte = 2
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
        if not (0 <= byte_index < len(row_bytes)):
            continue

        value = row_bytes[byte_index]
        pixel_index = display_pixel % pixels_per_byte

        if mode == 0:
            if pixel_index == 0:
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


def render_scanline_from_ram(
    ram,
    display_start_address: int,
    char_row: int,
    horizontal_displayed: int,
    visible_char_count: int,
    raster: int,
    horizontal_map: list[int],
    raster_origin_x: int,
    frame_width: int,
    border_rgb: tuple[int, int, int],
    mode: int,
    pen_rgb_map: list[tuple[int, int, int]],
) -> list[tuple[int, int, int]]:
    start_ma = (display_start_address + (char_row * horizontal_displayed)) & 0x3FFF
    row_bytes: list[int] = []

    for char_index in range(visible_char_count):
        ma = (start_ma + char_index) & 0x3FFF
        char_base = (((ma & 0x3000) << 2) | ((raster & 0x07) << 11) | ((ma & 0x03FF) << 1)) & 0xFFFF
        row_bytes.append(ram.peek(char_base))
        row_bytes.append(ram.peek((char_base + 1) & 0xFFFF))

    return compose_display_row(
        row_bytes,
        horizontal_map,
        raster_origin_x,
        frame_width,
        border_rgb,
        mode,
        pen_rgb_map,
    )


def render_frame_rgb24_from_ram(
    ram,
    display_start_address: int,
    horizontal_displayed: int,
    visible_char_count: int,
    visible_raster_height: int,
    horizontal_map: list[int],
    vertical_map: list[int],
    raster_origin_x: int,
    total_top: int,
    frame_width: int,
    frame_height: int,
    border_rgb: tuple[int, int, int],
    mode: int,
    pen_rgb_map: list[tuple[int, int, int]],
) -> bytes:
    out = bytearray(max(0, frame_width * frame_height * 3))
    if frame_width <= 0 or frame_height <= 0:
        return bytes(out)

    border_r, border_g, border_b = border_rgb
    for i in range(0, len(out), 3):
        out[i] = border_r
        out[i + 1] = border_g
        out[i + 2] = border_b

    if visible_char_count <= 0 or visible_raster_height <= 0:
        return bytes(out)

    if mode == 0:
        pixels_per_byte = 2
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
            if not (0 <= char_index < visible_char_count):
                continue

            ma = (start_ma + char_index) & 0x3FFF
            char_base = (((ma & 0x3000) << 2) | ((raster & 0x07) << 11) | ((ma & 0x03FF) << 1)) & 0xFFFF
            value = ram.peek((char_base + (byte_index & 1)) & 0xFFFF)
            pixel_index = display_pixel % pixels_per_byte

            if mode == 0:
                if pixel_index == 0:
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


__all__ = [
    "build_horizontal_display_map",
    "build_vertical_display_map",
    "compose_display_row",
    "render_frame_rgb24_from_ram",
    "render_scanline_from_ram",
]

