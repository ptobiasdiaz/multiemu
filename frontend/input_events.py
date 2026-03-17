from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class InputEvent:
    kind: str
    control_a: int
    control_b: int
    active: bool
