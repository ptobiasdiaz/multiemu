from __future__ import annotations

from dataclasses import dataclass


JOYSTICK_UP = 0x01
JOYSTICK_DOWN = 0x02
JOYSTICK_LEFT = 0x04
JOYSTICK_RIGHT = 0x08
JOYSTICK_FIRE = 0x10
JOYSTICK_FIRE_2 = 0x20


@dataclass(slots=True)
class InputEvent:
    kind: str
    control_a: int
    control_b: int
    active: bool
