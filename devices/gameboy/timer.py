"""Timer support for the Game Boy."""

from __future__ import annotations


class GameBoyTimer:
    """Models the DMG divider and programmable timer.

    This is still simpler than real edge-based hardware timing, but it keeps
    the public registers and interrupt behavior coherent enough for early ROMs.
    """

    TIMER_PERIODS = {
        0x00: 1024,
        0x01: 16,
        0x02: 64,
        0x03: 256,
    }

    def __init__(self, interrupts=None):
        self.interrupts = interrupts
        self.reset()

    def reset(self):
        self._div_counter = 0xAB00
        self._tima_counter = 0
        self.div = 0xAB
        self.tima = 0x00
        self.tma = 0x00
        self.tac = 0x00

    def run_cycles(self, cycles: int) -> None:
        cycles = max(0, int(cycles))
        if cycles <= 0:
            return

        self._div_counter = (self._div_counter + cycles) & 0xFFFF
        self.div = (self._div_counter >> 8) & 0xFF

        if (self.tac & 0x04) == 0:
            return

        self._tima_counter += cycles
        period = self.TIMER_PERIODS[self.tac & 0x03]
        while self._tima_counter >= period:
            self._tima_counter -= period
            if self.tima == 0xFF:
                self.tima = self.tma
                if self.interrupts is not None:
                    self.interrupts.request(2)
            else:
                self.tima = (self.tima + 1) & 0xFF

    def read_div(self) -> int:
        return self.div

    def write_div(self, value: int) -> None:
        del value
        self._div_counter = 0
        self.div = 0x00

    def read_tima(self) -> int:
        return self.tima

    def write_tima(self, value: int) -> None:
        self.tima = value & 0xFF

    def read_tma(self) -> int:
        return self.tma

    def write_tma(self, value: int) -> None:
        self.tma = value & 0xFF

    def read_tac(self) -> int:
        return self.tac | 0xF8

    def write_tac(self, value: int) -> None:
        self.tac = value & 0x07
