"""Interrupt controller placeholder for the Game Boy."""

from __future__ import annotations


class GameBoyInterruptController:
    """Tracks IF/IE and interrupt requests for the DMG."""

    def __init__(self):
        self.interrupt_enable = 0x00
        self.interrupt_flags = 0x00

    def reset(self):
        self.interrupt_enable = 0x00
        self.interrupt_flags = 0x00

    def request(self, bit: int) -> None:
        self.interrupt_flags |= 1 << bit
        self.interrupt_flags &= 0x1F

    def acknowledge(self, bit: int) -> None:
        self.interrupt_flags &= ~(1 << bit)
        self.interrupt_flags &= 0x1F
