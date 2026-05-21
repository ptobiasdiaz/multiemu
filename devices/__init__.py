"""External media and peripheral devices.

Internal machine chipsets should live under `chipsets/`. This package is kept
for media/peripherals and for transitional compatibility during the refactor.
"""

from .cpc_disk import CPCDiskImage
from .cpc_fdc import CPCFDC
from .cpc_tape import CPCCassetteTape
from .mapped_memory import ByteRAM, NibbleRAM, OpenBus
from .spectrum_tape import SpectrumCassetteTape

__all__ = [
    "CPCDiskImage",
    "CPCFDC",
    "CPCCassetteTape",
    "OpenBus",
    "ByteRAM",
    "NibbleRAM",
    "SpectrumCassetteTape",
]
