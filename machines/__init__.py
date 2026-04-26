"""Supported machine families."""

from .base import BaseMachine
from .gameboy import CGB, DMG, GameBoyMachineBase
from .m6502 import KIM1, M6502MachineBase, VIC20, VIC20NTSC, VIC20PAL
from .z80 import ColecoVision, CPC464, CPC6128, CPC664, GameGear, MasterSystem2, Spectrum128K, Spectrum16K, Spectrum48K, SpectrumBase, SpectrumPlus2

__all__ = [
    "BaseMachine",
    "ColecoVision",
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
    "GameGear",
    "MasterSystem2",
    "Spectrum128K",
    "SpectrumPlus2",
    "SpectrumBase",
    "Spectrum16K",
    "Spectrum48K",
]
