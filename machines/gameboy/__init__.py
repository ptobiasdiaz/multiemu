"""Nintendo Game Boy machine family."""

from .base import GameBoyMachineBase
from .cgb import CGB
from .dmg import DMG

__all__ = ["GameBoyMachineBase", "DMG", "CGB"]
