from __future__ import annotations

from tests.fallbacks.sn76489_reference import SN76489Reference


class SN76489(SN76489Reference):
    """Pure Python SN76489 fallback kept outside the runtime package.

    Runtime code imports ``chipsets.sn76489`` from the Cython extension. This
    class remains available to tests when a direct Python implementation is
    useful as a debugging aid.
    """
