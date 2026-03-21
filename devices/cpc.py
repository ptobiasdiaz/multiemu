from __future__ import annotations

"""Compatibility facade for CPC device classes split into per-chip modules."""

from .cpc_crtc import CPCCRTC, HD6845
from .cpc_gate_array import CPCGateArray
from .cpc_ppi import CPCPPI, Intel8255
from .cpc_tape import CPCCassetteTape
from .cpc_video import AmstradCPCVideo, CPCVideo

__all__ = [
    "CPCGateArray",
    "HD6845",
    "CPCCRTC",
    "Intel8255",
    "CPCPPI",
    "CPCCassetteTape",
    "CPCVideo",
    "AmstradCPCVideo",
]
