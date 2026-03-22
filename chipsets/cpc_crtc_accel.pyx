# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

cdef class HD6845:
    cdef public int selected_register
    cdef public list registers

    DEFAULT_REGISTERS = (
        63, 40, 46, 0x8E, 38, 0, 25, 30, 0, 7, 0, 0, 0x30, 0x00, 0, 0, 0, 0,
    )
    REGISTER_COUNT = 18

    def __init__(self):
        self.selected_register = 0
        self.registers = list(self.DEFAULT_REGISTERS)

    cpdef reset(self):
        self.selected_register = 0
        self.registers[:] = self.DEFAULT_REGISTERS

    cpdef select_register(self, int register_index):
        self.selected_register = register_index & 0x1F

    cpdef write_selected(self, int value):
        if self.selected_register < self.REGISTER_COUNT:
            self.registers[self.selected_register] = value & 0xFF

    @property
    def horizontal_total(self):
        return max(1, self.registers[0] + 1)

    @property
    def horizontal_displayed(self):
        return max(1, self.registers[1])

    @property
    def horizontal_sync_position(self):
        return self.registers[2]

    @property
    def horizontal_sync_width(self):
        cdef int width = self.registers[3] & 0x0F
        return width or 16

    @property
    def vertical_total(self):
        return max(1, self.registers[4] + 1)

    @property
    def vertical_total_adjust(self):
        return self.registers[5] & 0x1F

    @property
    def vertical_displayed(self):
        return max(1, self.registers[6])

    @property
    def vertical_sync_position(self):
        return self.registers[7]

    @property
    def vertical_sync_width(self):
        cdef int width = (self.registers[3] >> 4) & 0x0F
        return width or 16

    @property
    def maximum_raster_address(self):
        return self.registers[9] & 0x1F

    @property
    def raster_height(self):
        return self.maximum_raster_address + 1

    @property
    def total_scanlines(self):
        return (self.vertical_total * self.raster_height) + self.vertical_total_adjust

    @property
    def display_start_address(self):
        return ((self.registers[12] << 8) | self.registers[13]) & 0x3FFF

CPCCRTC = HD6845

