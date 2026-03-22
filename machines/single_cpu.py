from __future__ import annotations

from machines.base import BaseMachine, Bus, CPU


class SingleCPUMachineBase(BaseMachine):
    """Shared base for machines driven by a single CPU and a primary bus."""

    def __init__(self, *, bus: Bus, cpu: CPU, audio_sample_rate: int = 44100):
        super().__init__(bus=bus, cpu=cpu, audio_sample_rate=audio_sample_rate)
