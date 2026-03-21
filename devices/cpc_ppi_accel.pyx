# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

cdef class Intel8255:
    cdef public object machine
    cdef public int control
    cdef public int port_a_latch
    cdef public int port_b_latch
    cdef public int port_c_latch
    cdef public int last_port_a_read
    cdef public int last_port_a_write
    cdef public int last_control_write
    cdef public bint port_a_input
    cdef public bint port_b_input
    cdef public bint port_c_upper_input
    cdef public bint port_c_lower_input

    DEFAULT_CONTROL = 0x82
    DEFAULT_PORT_B = 0xDE

    def __init__(self, machine):
        self.machine = machine
        self.control = self.DEFAULT_CONTROL
        self.port_a_latch = 0
        self.port_b_latch = 0
        self.port_c_latch = 0
        self.last_port_a_read = 0xFF
        self.last_port_a_write = 0x00
        self.last_control_write = self.DEFAULT_CONTROL
        self.port_a_input = False
        self.port_b_input = True
        self.port_c_upper_input = False
        self.port_c_lower_input = False

    @property
    def selected_keyboard_line(self):
        return self.port_c_latch & 0x0F

    @property
    def psg_function(self):
        return (self.port_c_latch >> 6) & 0b11

    cpdef reset(self):
        self.control = self.DEFAULT_CONTROL
        self.port_a_latch = 0
        self.port_b_latch = 0
        self.port_c_latch = 0
        self.last_port_a_read = 0xFF
        self.last_port_a_write = 0x00
        self.last_control_write = self.DEFAULT_CONTROL
        self.port_a_input = False
        self.port_b_input = True
        self.port_c_upper_input = False
        self.port_c_lower_input = False

    cpdef write_port_a(self, int value):
        self.port_a_latch = value & 0xFF
        self.last_port_a_write = self.port_a_latch
        self.machine._apply_psg_bus_control()

    cpdef int read_port_a(self):
        if self.port_a_input and self.psg_function == 0b01:
            self.last_port_a_read = self.machine.psg.read_selected()
            return self.last_port_a_read
        self.last_port_a_read = self.port_a_latch if not self.port_a_input else 0xFF
        return self.last_port_a_read

    cpdef write_port_b(self, int value):
        self.port_b_latch = value & 0xFF

    cpdef int read_port_b(self):
        cdef int base
        if self.port_b_input:
            base = self.DEFAULT_PORT_B & 0xFE
            if self.machine.read_cassette_input():
                base |= 0x80
            else:
                base &= 0x7F
            return base | (1 if self.machine.vsync_active else 0)
        return self.port_b_latch

    cpdef write_port_c(self, int value):
        self.port_c_latch = value & 0xFF
        self.machine._apply_psg_bus_control()
        self.machine._apply_tape_port_c()

    cpdef int read_port_c(self):
        return self.port_c_latch

    cpdef write_control(self, int value):
        cdef int bit_index
        value &= 0xFF
        if value & 0x80:
            self.control = value
            self.last_control_write = value
            self.port_a_input = bool(value & 0x10)
            self.port_b_input = bool(value & 0x02)
            self.port_c_upper_input = bool(value & 0x08)
            self.port_c_lower_input = bool(value & 0x01)
            return
        bit_index = (value >> 1) & 0x07
        if value & 0x01:
            self.port_c_latch |= 1 << bit_index
        else:
            self.port_c_latch &= ~(1 << bit_index)
        self.machine._apply_psg_bus_control()
        self.machine._apply_tape_port_c()

CPCPPI = Intel8255
