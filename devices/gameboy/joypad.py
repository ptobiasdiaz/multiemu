"""Joypad placeholder for the Game Boy."""

from __future__ import annotations


class GameBoyJoypad:
    """Models the P1/JOYP register and button matrix."""

    BUTTON_RIGHT = (0, 0)
    BUTTON_LEFT = (0, 1)
    BUTTON_UP = (0, 2)
    BUTTON_DOWN = (0, 3)
    BUTTON_A = (1, 0)
    BUTTON_B = (1, 1)
    BUTTON_SELECT = (1, 2)
    BUTTON_START = (1, 3)

    def __init__(self, interrupts=None):
        self.interrupts = interrupts
        self.select_bits = 0x00
        self.direction_state = 0x0F
        self.button_state = 0x0F

    def reset(self):
        self.select_bits = 0x00
        self.direction_state = 0x0F
        self.button_state = 0x0F

    def clear_pressed_state(self) -> None:
        self.direction_state = 0x0F
        self.button_state = 0x0F

    def press(self, group: int, bit: int) -> None:
        if group == 0:
            previous_pressed = (self.direction_state & (1 << bit)) == 0
        else:
            previous_pressed = (self.button_state & (1 << bit)) == 0
        if group == 0:
            self.direction_state &= ~(1 << bit)
            self.direction_state &= 0x0F
        else:
            self.button_state &= ~(1 << bit)
            self.button_state &= 0x0F
        if self.interrupts is not None and not previous_pressed:
            self.interrupts.request(4)

    def release(self, group: int, bit: int) -> None:
        if group == 0:
            self.direction_state |= 1 << bit
            self.direction_state &= 0x0F
        else:
            self.button_state |= 1 << bit
            self.button_state &= 0x0F

    def write_p1(self, value: int) -> None:
        self.select_bits = value & 0x30

    def read_p1(self) -> int:
        low = 0x0F
        if (self.select_bits & 0x10) == 0:
            low &= self.direction_state
        if (self.select_bits & 0x20) == 0:
            low &= self.button_state
        return 0xC0 | self.select_bits | low
