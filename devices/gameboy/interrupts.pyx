# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

"""Interrupt controller placeholder for the Game Boy."""

from multiemu.state_codec import read_state_fields, write_state_fields


cdef class GameBoyInterruptController:
    """Tracks IF/IE and interrupt requests for the DMG."""

    cdef public int interrupt_enable
    cdef public int interrupt_flags

    def __init__(self):
        self.interrupt_enable = 0x00
        self.interrupt_flags = 0x01

    cpdef void reset(self):
        self.interrupt_enable = 0x00
        self.interrupt_flags = 0x01

    cpdef void request(self, int bit):
        self.interrupt_flags |= 1 << bit
        self.interrupt_flags &= 0x1F

    cpdef void acknowledge(self, int bit):
        self.interrupt_flags &= ~(1 << bit)
        self.interrupt_flags &= 0x1F

    def read_state(self) -> dict:
        return read_state_fields(
            self,
            scalar_fields=("interrupt_enable", "interrupt_flags"),
            meta={"type": "GameBoyInterruptController"},
        )

    def write_state(self, state: dict) -> None:
        write_state_fields(self, state, scalar_fields=("interrupt_enable", "interrupt_flags"))
