from .types cimport uint8_t, uint16_t

cdef class PortHandler:
    cpdef uint8_t read(self, uint16_t port)
    cpdef void write(self, uint16_t port, uint8_t value)


cdef class PythonPortHandler(PortHandler):
    cdef object read_cb
    cdef object write_cb
