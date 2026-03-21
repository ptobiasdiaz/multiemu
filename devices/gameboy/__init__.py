"""Devices used by the original Nintendo Game Boy."""

from .apu import GameBoyAPU
from .cartridge import GameBoyCartridge
from .dma import GameBoyDMAController
from .huc1 import HuC1
from .interrupts import GameBoyInterruptController
from .joypad import GameBoyJoypad
from .mbc1 import MBC1
from .mbc2 import MBC2
from .mbc5 import MBC5
from .ppu import GameBoyPPU
from .serial import GameBoySerialPort
from .timer import GameBoyTimer

__all__ = [
    "GameBoyAPU",
    "GameBoyCartridge",
    "GameBoyDMAController",
    "HuC1",
    "GameBoyInterruptController",
    "GameBoyJoypad",
    "MBC2",
    "MBC5",
    "GameBoyPPU",
    "GameBoySerialPort",
    "GameBoyTimer",
    "MBC1",
]
