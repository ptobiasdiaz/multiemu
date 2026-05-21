# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from multiemu.state_codec import read_state_fields, write_state_fields


cdef class OpenBus:
    cdef public int size
    cdef public int read_value

    def __cinit__(self, int size=0x0400, int read_value=0xFF):
        self.size = size
        self.read_value = read_value & 0xFF

    cpdef int read(self, int addr):
        return self.read_value

    cpdef void write(self, int addr, int value):
        return

    def read_state(self) -> dict:
        return read_state_fields(
            self,
            scalar_fields=("size", "read_value"),
            meta={"type": "OpenBus"},
        )

    def write_state(self, state: dict) -> None:
        write_state_fields(self, state, scalar_fields=("size", "read_value"))
        self.read_value &= 0xFF


cdef class ByteRAM:
    cdef public int size
    cdef public int read_default
    cdef bytearray data

    def __cinit__(self, int size=0x0400, int read_default=0xFF):
        self.size = size
        self.read_default = read_default & 0xFF
        self.data = bytearray(self.size)

    cpdef int read(self, int addr):
        if 0 <= addr < self.size:
            return self.data[addr]
        return self.read_default

    cpdef void write(self, int addr, int value):
        if 0 <= addr < self.size:
            self.data[addr] = value & 0xFF

    cpdef int peek(self, int addr):
        return self.read(addr)

    cpdef void clear(self):
        self.data[:] = bytes(self.size)

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "ByteRAM"},
            "size": self.size,
            "read_default": self.read_default,
            "data": list(self.data),
        }

    def write_state(self, state: dict) -> None:
        if "size" in state and int(state["size"]) != self.size:
            raise ValueError("tamaño de ByteRAM incompatible")
        if "read_default" in state:
            self.read_default = int(state["read_default"]) & 0xFF
        if "data" in state:
            self.data[:] = bytes(int(v) & 0xFF for v in state["data"][: self.size]).ljust(self.size, b"\x00")


cdef class NibbleRAM:
    cdef public int size
    cdef public int read_default
    cdef bytearray data

    def __cinit__(self, int size=0x0400, int read_default=0x0F):
        self.size = size
        self.read_default = read_default & 0x0F
        self.data = bytearray(self.size)

    cpdef int read(self, int addr):
        if 0 <= addr < self.size:
            return self.data[addr] & 0x0F
        return self.read_default

    cpdef void write(self, int addr, int value):
        if 0 <= addr < self.size:
            self.data[addr] = value & 0x0F

    cpdef int peek(self, int addr):
        return self.read(addr)

    cpdef void clear(self):
        self.data[:] = bytes(self.size)

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "NibbleRAM"},
            "size": self.size,
            "read_default": self.read_default,
            "data": list(self.data),
        }

    def write_state(self, state: dict) -> None:
        if "size" in state and int(state["size"]) != self.size:
            raise ValueError("tamaño de NibbleRAM incompatible")
        if "read_default" in state:
            self.read_default = int(state["read_default"]) & 0x0F
        if "data" in state:
            self.data[:] = bytes(int(v) & 0x0F for v in state["data"][: self.size]).ljust(self.size, b"\x00")
