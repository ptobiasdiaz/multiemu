from __future__ import annotations

"""Local Python startup fixes for developer workflows.

This repo still relies on setuptools/Cython extension builds. On this Python
3.13 environment, some setuptools entry points try to import ``distutils``
before the local setuptools shim is active, which breaks editable installs and
``setup.py build_ext --inplace``.

Importing ``sitecustomize`` is a standard Python startup hook, so we can make
sure setuptools' vendored distutils shim is enabled before those imports
happen, without changing runtime package code.
"""

import os

os.environ.setdefault("SETUPTOOLS_USE_DISTUTILS", "local")

try:
    import _distutils_hack
except Exception:
    _distutils_hack = None

if _distutils_hack is not None:
    try:
        _distutils_hack.do_override()
    except Exception:
        pass
