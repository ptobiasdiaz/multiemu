"""Timer support for the Game Boy."""


cdef class GameBoyTimer:
    """Models the DMG divider and programmable timer."""

    cdef object interrupts
    cdef int _div_counter
    cdef int _tima_counter
    cdef public int div
    cdef public int tima
    cdef public int tma
    cdef public int tac

    def __init__(self, interrupts=None):
        self.interrupts = interrupts
        self.reset()

    def reset(self):
        self._div_counter = 0
        self._tima_counter = 0
        self.div = 0x00
        self.tima = 0x00
        self.tma = 0x00
        self.tac = 0x00

    def run_cycles(self, int cycles):
        cdef int period
        if cycles <= 0:
            return

        self._div_counter = (self._div_counter + cycles) & 0xFFFF
        self.div = (self._div_counter >> 8) & 0xFF

        if (self.tac & 0x04) == 0:
            return

        self._tima_counter += cycles
        if (self.tac & 0x03) == 0x00:
            period = 1024
        elif (self.tac & 0x03) == 0x01:
            period = 16
        elif (self.tac & 0x03) == 0x02:
            period = 64
        else:
            period = 256

        while self._tima_counter >= period:
            self._tima_counter -= period
            if self.tima == 0xFF:
                self.tima = self.tma
                if self.interrupts is not None:
                    self.interrupts.request(2)
            else:
                self.tima = (self.tima + 1) & 0xFF

    def read_div(self):
        return self.div

    def write_div(self, value):
        self._div_counter = 0
        self.div = 0x00

    def read_tima(self):
        return self.tima

    def write_tima(self, value):
        self.tima = value & 0xFF

    def read_tma(self):
        return self.tma

    def write_tma(self, value):
        self.tma = value & 0xFF

    def read_tac(self):
        return self.tac | 0xF8

    def write_tac(self, value):
        self.tac = value & 0x07
