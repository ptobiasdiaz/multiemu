from __future__ import annotations

"""Z80-specific cold-path helpers for machine wiring.

Family-agnostic helpers live in ``machines.common``. Keep this module limited
to Z80 bus setup helpers so responsibilities remain clear.
"""

from cpu.z80 import PythonPortHandler, Z80Bus


def install_uniform_port_handlers(bus: Z80Bus, read_port, write_port) -> None:
    for port_low in range(256):
        bus.set_port_handler(port_low, PythonPortHandler(read_port, write_port))
