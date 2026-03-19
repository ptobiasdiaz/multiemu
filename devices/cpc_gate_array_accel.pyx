# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

cdef class CPCGateArray:
    cdef public object machine
    cdef public int selected_pen
    cdef public int border_hardware_color
    cdef public list pen_colors
    cdef public int mode
    cdef public int interrupt_line_counter
    cdef public bint pending_interrupt
    cdef public bint _last_vsync_active
    cdef public int _vsync_delay_lines

    HARDWARE_PALETTE = (
        (255, 255, 255), (255, 255, 255), (0, 128, 128), (255, 255, 128),
        (0, 0, 128), (128, 0, 128), (0, 255, 255), (255, 128, 192),
        (128, 0, 128), (255, 255, 128), (255, 255, 0), (255, 255, 255),
        (255, 0, 0), (255, 0, 255), (255, 128, 0), (255, 128, 255),
        (0, 0, 128), (0, 128, 128), (0, 255, 0), (0, 255, 255),
        (0, 0, 0), (0, 0, 255), (0, 128, 0), (128, 192, 255),
        (255, 0, 255), (128, 255, 128), (128, 255, 0), (128, 255, 255),
        (128, 0, 0), (128, 0, 255), (255, 255, 0), (128, 128, 255),
    )

    def __init__(self, machine):
        self.machine = machine
        self.selected_pen = 0
        self.border_hardware_color = 20
        self.pen_colors = [20] * 16
        self.mode = 1
        self.interrupt_line_counter = 0
        self.pending_interrupt = False
        self._last_vsync_active = False
        self._vsync_delay_lines = 0

    cpdef reset(self):
        self.selected_pen = 0
        self.border_hardware_color = 20
        self.pen_colors = [20] * 16
        self.mode = 1
        self.interrupt_line_counter = 0
        self.pending_interrupt = False
        self._last_vsync_active = False
        self._vsync_delay_lines = 0
        self.machine.set_rom_configuration(
            lower_rom_enabled=True,
            upper_rom_enabled=self.machine._has_upper_rom,
        )

    cpdef write(self, int value):
        cdef int command
        value &= 0xFF
        command = (value >> 6) & 0b11
        if command == 0b00:
            self._select_pen(value)
            return
        if command == 0b01:
            self._select_colour(value)
            return
        if command == 0b10:
            self._select_mode_and_roms(value)

    cdef _select_pen(self, int value):
        if value & 0x10:
            self.selected_pen = -1
            return
        self.selected_pen = value & 0x0F

    cdef _select_colour(self, int value):
        cdef int hardware_color = value & 0x1F
        if self.selected_pen < 0:
            self.border_hardware_color = hardware_color
            self.machine.frame_border_hardware_color = hardware_color
            return
        self.pen_colors[self.selected_pen] = hardware_color

    cdef _select_mode_and_roms(self, int value):
        self.mode = value & 0x03
        self.machine.frame_gate_mode = self.mode
        if value & 0x10:
            self.interrupt_line_counter = 0
        self.machine.set_rom_configuration(
            lower_rom_enabled=(value & 0x04) == 0,
            upper_rom_enabled=(value & 0x08) == 0,
        )

    cpdef tuple get_border_rgb(self):
        return self.HARDWARE_PALETTE[self.border_hardware_color]

    cpdef tuple get_pen_rgb(self, int pen):
        return self.HARDWARE_PALETTE[self.pen_colors[pen & 0x0F]]

    cpdef begin_scanline(self, bint vsync_active):
        if vsync_active and not self._last_vsync_active:
            self._vsync_delay_lines = 2
        self._last_vsync_active = vsync_active

    cpdef end_scanline(self):
        self.interrupt_line_counter += 1
        if self.interrupt_line_counter >= self.machine.INTERRUPT_PERIOD_LINES:
            self.pending_interrupt = True
            self.interrupt_line_counter = 0
        if self._vsync_delay_lines > 0:
            self._vsync_delay_lines -= 1
            if self._vsync_delay_lines == 0:
                if self.interrupt_line_counter >= 32:
                    self.pending_interrupt = True
                self.interrupt_line_counter = 0

    cpdef bint pop_pending_interrupt(self):
        cdef bint pending = self.pending_interrupt
        self.pending_interrupt = False
        return pending

    cpdef acknowledge_interrupt(self):
        self.interrupt_line_counter &= 0x1F

