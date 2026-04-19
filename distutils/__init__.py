from __future__ import annotations

"""Compatibility shim for Python 3.13 build tooling.

Some setuptools/Cython entry points still import ``distutils.*`` directly.
Python 3.13 removes stdlib ``distutils``, so editable installs and
``setup.py build_ext --inplace`` can fail before setuptools activates its own
vendored replacement.

Expose ``setuptools._distutils`` under the traditional package name so legacy
imports keep working inside this repository's build workflow.
"""

from importlib import import_module

_distutils = import_module("setuptools._distutils")

globals().update(_distutils.__dict__)
__all__ = getattr(_distutils, "__all__", [])
__file__ = _distutils.__file__
__path__ = _distutils.__path__
