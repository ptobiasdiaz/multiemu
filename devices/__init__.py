'''
    Emulated devices
'''

from .ay38912 import AY38912
from .cpc import CPCGateArray, CPCCRTC, CPCPPI, AmstradCPCVideo, CPCVideo, HD6845, Intel8255
from .cpc_tape import CPCCassetteTape
from .spectrum_tape import SpectrumCassetteTape

__all__ = [
    "AY38912",
    "CPCGateArray",
    "HD6845",
    "CPCCRTC",
    "Intel8255",
    "CPCPPI",
    "CPCVideo",
    "AmstradCPCVideo",
    "CPCCassetteTape",
    "SpectrumCassetteTape",
]
