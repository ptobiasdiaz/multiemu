"""Internal machine chipsets and core subsystems.

This namespace hosts chips that are wired inside machines. External media and
peripherals such as tapes, disks and similar devices stay under `devices/`.
"""

from .ay38912 import AY38912
from .cpc_crtc import CPCCRTC, HD6845
from .cpc_gate_array import CPCGateArray
from .cpc_ppi import CPCPPI, Intel8255
from .cpc_render import (
    build_horizontal_display_map,
    build_vertical_display_map,
    compose_display_row,
    render_frame_rgb24_from_ram,
    render_scanline_from_ram,
)
from .cpc_video import AmstradCPCVideo, CPCVideo
from .m6530 import M6530
from .sega8_vdp import SMSVDP, Sega8VDP
from .sn76489 import SN76489
from .tms9918a import TMS9918A
from .ula import Spectrum48KULA, ULABeeper

__all__ = [
    "AY38912",
    "CPCGateArray",
    "HD6845",
    "CPCCRTC",
    "Intel8255",
    "CPCPPI",
    "CPCVideo",
    "AmstradCPCVideo",
    "build_horizontal_display_map",
    "build_vertical_display_map",
    "compose_display_row",
    "render_frame_rgb24_from_ram",
    "render_scanline_from_ram",
    "M6530",
    "Sega8VDP",
    "SMSVDP",
    "SN76489",
    "TMS9918A",
    "Spectrum48KULA",
    "ULABeeper",
]
