"""Pure-Python LR35902 reference used only by tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path


_CORE_PATH = Path(__file__).resolve().parents[2] / "cpu" / "lr35902" / "core.py"
_SPEC = importlib.util.spec_from_file_location("gameboy_lr35902_core_reference", _CORE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("no se pudo cargar la referencia Python pura de LR35902")

_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

LR35902Core = _MODULE.LR35902Core

__all__ = ["LR35902Core"]
