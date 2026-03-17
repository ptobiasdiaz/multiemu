from .types cimport uint8_t, uint16_t
from .io cimport PortHandler, PythonPortHandler


cdef class PortHandler:

    cpdef uint8_t read(self, uint16_t port):
        return 0xFF

    cpdef void write(self, uint16_t port, uint8_t value):
        pass


cdef class PythonPortHandler(PortHandler):

    def __init__(self, read_cb=None, write_cb=None):
        self.read_cb = read_cb
        self.write_cb = write_cb

    cpdef uint8_t read(self, uint16_t port):
        if self.read_cb is None:
            return 0xFF
        return <uint8_t>(int(self.read_cb(port)) & 0xFF)

    cpdef void write(self, uint16_t port, uint8_t value):
        if self.write_cb is not None:
            self.write_cb(port, value)
