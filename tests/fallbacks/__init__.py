"""Reference pure-Python implementations used only by tests.

These modules are the readable equivalence oracles for Cython-backed runtime
code. Production imports must stay under ``chipsets/`` or other runtime
packages; tests are the only valid consumers of this namespace.
"""

from .sega8_vdp_reference import Sega8VDPReference
from .sn76489_reference import SN76489Reference
from .tms9918a_reference import TMS9918AReference

__all__ = [
    "Sega8VDPReference",
    "SN76489Reference",
    "TMS9918AReference",
]
