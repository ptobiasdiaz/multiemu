from __future__ import annotations

from cpu.m6502 import M6502Bus, M6502Core
from machines.base import BaseMachine, Bus, CPU


class M6502MachineBase(BaseMachine):
    """Family anchor for future 6502-based machines.

    The 6502 bus/device model differs enough from Z80-derived machines that it
    should grow under its own namespace instead of reusing Z80-specific bases.
    """

    def __init__(
        self,
        *,
        bus: Bus | None = None,
        cpu: CPU | None = None,
        audio_sample_rate: int = 44100,
    ):
        if bus is None:
            bus = M6502Bus()
        if cpu is None:
            cpu = M6502Core(bus)
        super().__init__(bus=bus, cpu=cpu, audio_sample_rate=audio_sample_rate)
