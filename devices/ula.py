from __future__ import annotations

try:
    from .ula_accel import Spectrum48KULA, ULABeeper
except ImportError:
    from .ula_fallback import Spectrum48KULA, ULABeeper

__all__ = ["Spectrum48KULA", "ULABeeper"]
