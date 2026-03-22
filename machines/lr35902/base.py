from __future__ import annotations

from cpu.lr35902 import LR35902Bus, LR35902Core
from machines.single_cpu import SingleCPUMachineBase


class LR35902MachineBase(SingleCPUMachineBase):
    """Base for machines built around a standalone LR35902 CPU and bus."""

    def __init__(self, *, memory, audio_sample_rate: int = 44100):
        bus = LR35902Bus(memory)
        cpu = LR35902Core(bus)
        super().__init__(bus=bus, cpu=cpu, audio_sample_rate=audio_sample_rate)
