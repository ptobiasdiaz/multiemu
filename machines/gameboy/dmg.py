"""Original monochrome Game Boy (DMG) machine."""

from __future__ import annotations

from .base import GameBoyMachineBase


class DMG(GameBoyMachineBase):
    """Nintendo Game Boy (DMG-01)."""

    def __init__(self, rom_data: bytes):
        super().__init__(rom_data)
