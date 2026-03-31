"""Supported machine families."""

from .base import BaseMachine
from .gameboy import DMG, GameBoyMachineBase
from .lr35902 import LR35902MachineBase
from .m6502 import KIM1, M6502MachineBase, VIC20, VIC20NTSC, VIC20PAL
from .single_cpu import SingleCPUMachineBase
from .z80 import CPC464, Spectrum16K, Spectrum48K, SpectrumBase, Z80MachineBase

__all__ = [
    "BaseMachine",
    "SingleCPUMachineBase",
    "LR35902MachineBase",
    "M6502MachineBase",
    "KIM1",
    "VIC20",
    "VIC20NTSC",
    "VIC20PAL",
    "GameBoyMachineBase",
    "DMG",
    "Z80MachineBase",
    "CPC464",
    "SpectrumBase",
    "Spectrum16K",
    "Spectrum48K",
]
