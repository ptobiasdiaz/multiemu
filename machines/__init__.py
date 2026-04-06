"""Supported machine families."""

from .base import BaseMachine
from .gameboy import CGB, DMG, GameBoyMachineBase
from .m6502 import KIM1, M6502MachineBase, VIC20, VIC20NTSC, VIC20PAL
from .z80 import CPC464, CPC6128, CPC664, Spectrum128K, Spectrum16K, Spectrum48K, SpectrumBase

__all__ = [
    "BaseMachine",
    "M6502MachineBase",
    "KIM1",
    "VIC20",
    "VIC20NTSC",
    "VIC20PAL",
    "GameBoyMachineBase",
    "DMG",
    "CGB",
    "CPC464",
    "CPC6128",
    "CPC664",
    "Spectrum128K",
    "SpectrumBase",
    "Spectrum16K",
    "Spectrum48K",
]
