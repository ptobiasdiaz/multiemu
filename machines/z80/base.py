from __future__ import annotations

from cpu.z80 import Z80Bus, Z80Core
from machines.base import BaseMachine


class Z80MachineBase(BaseMachine):
    def __init__(self, *, audio_sample_rate: int = 44100):
        bus = Z80Bus()
        cpu = Z80Core(bus)
        super().__init__(bus=bus, cpu=cpu, audio_sample_rate=audio_sample_rate)
