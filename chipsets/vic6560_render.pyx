# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

cdef tuple _palette_color(int color_index):
    cdef int idx = color_index & 0x0F
    if idx == 0x0:
        return (0, 0, 0)
    if idx == 0x1:
        return (255, 255, 255)
    if idx == 0x2:
        return (240, 0, 0)
    if idx == 0x3:
        return (0, 240, 240)
    if idx == 0x4:
        return (96, 0, 96)
    if idx == 0x5:
        return (0, 160, 0)
    if idx == 0x6:
        return (0, 0, 240)
    if idx == 0x7:
        return (208, 208, 0)
    if idx == 0x8:
        return (192, 160, 0)
    if idx == 0x9:
        return (255, 160, 0)
    if idx == 0xA:
        return (240, 128, 128)
    if idx == 0xB:
        return (0, 255, 255)
    if idx == 0xC:
        return (255, 0, 255)
    if idx == 0xD:
        return (0, 255, 0)
    if idx == 0xE:
        return (0, 160, 255)
    return (255, 255, 0)


cdef int _foreground_phase(int pixel, int half_flag):
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


cdef int _pixel_color_index(
    int screen_code,
    int color_nibble,
    int glyph_bits,
    int reg_e,
    int reg_f,
    int pixel_x,
    int char_height,
):
    cdef bint reverse_code = (screen_code & 0x80) != 0 and char_height <= 8
    cdef bint effective_reverse = (((reg_f & 0x08) == 0) != reverse_code)
    cdef bint multicolor_mode = (color_nibble & 0x08) != 0
    cdef int bg = (reg_f >> 4) & 0x0F
    cdef int pair_bits
    cdef int row_bits
    cdef bint pixel_on

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


cpdef void draw_char_cell_scanline_rgb24(
    bytearray out,
    int width,
    int height,
    int x,
    int y,
    int screen_code,
    int color_nibble,
    int glyph_bits,
    int char_height,
    int half_flag,
    int phase0_e,
    int phase0_f,
    int phase1_e,
    int phase1_f,
    int phase2_e,
    int phase2_f,
):
    cdef int col
    cdef int dst_x
    cdef int idx
    cdef int phase
    cdef int pixel_reg_e
    cdef int pixel_reg_f
    cdef int color_index
    cdef tuple rgb

    if y < 0 or y >= height:
        return

    for col in range(8):
        dst_x = x + col
        if dst_x < 0 or dst_x >= width:
            continue
        phase = _foreground_phase(col, half_flag)
        if phase == 0:
            pixel_reg_e = phase0_e
            pixel_reg_f = phase0_f
        elif phase == 1:
            pixel_reg_e = phase1_e
            pixel_reg_f = phase1_f
        else:
            pixel_reg_e = phase2_e
            pixel_reg_f = phase2_f

        color_index = _pixel_color_index(
            screen_code,
            color_nibble,
            glyph_bits,
            pixel_reg_e,
            pixel_reg_f,
            col,
            char_height,
        )
        rgb = _palette_color(color_index)
        idx = (y * width + dst_x) * 3
        out[idx] = rgb[0]
        out[idx + 1] = rgb[1]
        out[idx + 2] = rgb[2]


cpdef void draw_scanline_cells_rgb24(
    bytearray out,
    int width,
    int height,
    int y,
    int char_height,
    object cell_xs,
    object screen_codes,
    object color_nibbles,
    object glyph_bits_list,
    object half_flags,
    object phase0_es,
    object phase0_fs,
    object phase1_es,
    object phase1_fs,
    object phase2_es,
    object phase2_fs,
):
    cdef Py_ssize_t i
    cdef Py_ssize_t count = len(cell_xs)
    cdef int x
    cdef int screen_code
    cdef int color_nibble
    cdef int glyph_bits
    cdef int half_flag
    cdef int phase0_e
    cdef int phase0_f
    cdef int phase1_e
    cdef int phase1_f
    cdef int phase2_e
    cdef int phase2_f

    if y < 0 or y >= height:
        return

    for i in range(count):
        x = <int>cell_xs[i]
        screen_code = <int>screen_codes[i]
        color_nibble = <int>color_nibbles[i]
        glyph_bits = <int>glyph_bits_list[i]
        half_flag = <int>half_flags[i]
        phase0_e = <int>phase0_es[i]
        phase0_f = <int>phase0_fs[i]
        phase1_e = <int>phase1_es[i]
        phase1_f = <int>phase1_fs[i]
        phase2_e = <int>phase2_es[i]
        phase2_f = <int>phase2_fs[i]
        draw_char_cell_scanline_rgb24(
            out,
            width,
            height,
            x,
            y,
            screen_code,
            color_nibble,
            glyph_bits,
            char_height,
            half_flag,
            phase0_e,
            phase0_f,
            phase1_e,
            phase1_f,
            phase2_e,
            phase2_f,
        )


cpdef void draw_scanline_contexts_rgb24(
    bytearray out,
    int width,
    int height,
    int y,
    int char_height,
    object fetch_contexts,
):
    cdef Py_ssize_t i
    cdef Py_ssize_t count = len(fetch_contexts)
    cdef tuple ctx
    cdef int x
    cdef int screen_code
    cdef int color_nibble
    cdef int glyph_bits
    cdef int half_flag
    cdef int phase0_e
    cdef int phase0_f
    cdef int phase1_e
    cdef int phase1_f
    cdef int phase2_e
    cdef int phase2_f

    if y < 0 or y >= height:
        return

    for i in range(count):
        ctx = fetch_contexts[i]
        x = <int>ctx[2]
        screen_code = <int>ctx[6]
        color_nibble = <int>ctx[7]
        glyph_bits = <int>ctx[9]
        half_flag = <int>ctx[13]
        phase0_e = <int>ctx[14]
        phase0_f = <int>ctx[15]
        phase1_e = <int>ctx[16]
        phase1_f = <int>ctx[17]
        phase2_e = <int>ctx[18]
        phase2_f = <int>ctx[19]
        draw_char_cell_scanline_rgb24(
            out,
            width,
            height,
            x,
            y,
            screen_code,
            color_nibble,
            glyph_bits,
            char_height,
            half_flag,
            phase0_e,
            phase0_f,
            phase1_e,
            phase1_f,
            phase2_e,
            phase2_f,
        )


cpdef list build_scanline_contexts(
    object vic,
    int y,
    int frame_width,
    int frame_height,
    object screen_codes,
    object color_nibbles,
    object glyph_bits,
):
    cdef list cells = vic.display_fetch_cells_for_scanline(y, frame_width, frame_height)
    cdef list contexts = []
    cdef Py_ssize_t index
    cdef Py_ssize_t limit = len(cells)
    cdef tuple cell
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
    cdef object phases
    cdef object modes
    cdef int effective_reverse
    cdef int multicolor_mode
    cdef int char_height = vic.char_height()

    if limit > len(screen_codes):
        limit = len(screen_codes)
    if limit > len(color_nibbles):
        limit = len(color_nibbles)
    if limit > len(glyph_bits):
        limit = len(glyph_bits)

    for index in range(limit):
        cell = cells[index]
        row = <int>cell[0]
        col = <int>cell[1]
        cell_x = <int>cell[2]
        pixel_y = <int>cell[3]
        screen_addr = <int>cell[4]
        color_addr = <int>cell[5]
        screen_code = (<int>screen_codes[index]) & 0xFF
        color_nibble = (<int>color_nibbles[index]) & 0x0F
        glyph_addr = <int>vic.glyph_row_address_for_cell(screen_code, pixel_y)
        glyph_row_bits = (<int>glyph_bits[index]) & 0xFF
        reg_e, reg_f = vic.color_regs_for_position(y, cell_x)
        phases = vic.foreground_reg_phase_values_for_cell(y, col, reg_e, reg_f)
        half_flag = <int>phases[0]
        phase0_e = <int>phases[1]
        phase0_f = <int>phases[2]
        phase1_e = <int>phases[3]
        phase1_f = <int>phases[4]
        phase2_e = <int>phases[5]
        phase2_f = <int>phases[6]
        modes = vic.effective_cell_mode(
            screen_code=screen_code,
            color_nibble=color_nibble,
            reg_f=reg_f,
            char_height=char_height,
        )
        effective_reverse = 1 if modes[0] else 0
        multicolor_mode = 1 if modes[1] else 0
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
                effective_reverse | (multicolor_mode << 1),
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
