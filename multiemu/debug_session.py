from __future__ import annotations

"""Step-by-step debug session for a machine instance.

Wraps a machine and exposes instruction-level stepping while managing frame
boundaries transparently (_begin_frame / _finish_frame via duck typing so
BaseMachine does not need to declare them).
"""


class DebugSession:
    def __init__(self, machine):
        self.machine = machine
        self._in_frame: bool = False
        self._tstates_per_frame: int = int(getattr(machine, "TSTATES_PER_FRAME", 0))
        self._begin_frame = getattr(machine, "_begin_frame", None)
        self._finish_frame = getattr(machine, "_finish_frame", None)

        # Populated after each step() call.
        self.last_step_cycles: int = 0
        self.frame_completed: bool = False

    def _iter_named_debug_devices(self):
        yielded: set[str] = set()
        machine = self.machine

        def maybe_yield(device_id: str, obj, kind: str, label: str | None = None, writable: bool | None = None):
            if obj is None or device_id in yielded:
                return
            if not hasattr(obj, "read_state"):
                return
            yielded.add(device_id)
            yield {
                "id": device_id,
                "kind": kind,
                "label": label or device_id,
                "writable": bool(hasattr(obj, "write_state")) if writable is None else bool(writable),
            }

        if hasattr(machine, "debug_devices"):
            for descriptor in machine.debug_devices():
                yield from maybe_yield(
                    descriptor["id"],
                    descriptor.get("obj"),
                    descriptor.get("kind", "device"),
                    descriptor.get("label"),
                    descriptor.get("writable"),
                )
            return

        yield from maybe_yield("machine", machine, "machine", "Machine")
        yield from maybe_yield("cpu", getattr(machine, "cpu", None), "cpu", "CPU")
        yield from maybe_yield("bus", getattr(machine, "bus", None), "bus", "Bus")

        for name, value in sorted(vars(machine).items()):
            if name.startswith("_"):
                continue
            if name in {"cpu", "bus"}:
                continue
            kind = "device"
            if "via" in name or "vic" in name or "ula" in name or "apu" in name or "ppu" in name:
                kind = "chip"
            elif "ram" in name or "rom" in name or "memory" in name:
                kind = "memory"
            yield from maybe_yield(name, value, kind)

    def list_devices(self) -> list[dict]:
        return list(self._iter_named_debug_devices())

    def _resolve_device(self, device_id: str):
        if device_id == "machine":
            return self.machine
        if device_id == "cpu":
            return getattr(self.machine, "cpu", None)
        if device_id == "bus":
            return getattr(self.machine, "bus", None)
        return getattr(self.machine, device_id, None)

    def get_device_state(self, device_id: str) -> dict:
        device = self._resolve_device(device_id)
        if device is None or not hasattr(device, "read_state"):
            raise ValueError(f"dispositivo de debug no soportado: {device_id!r}")
        return device.read_state()

    def set_device_state(self, device_id: str, state: dict) -> None:
        device = self._resolve_device(device_id)
        if device is None or not hasattr(device, "write_state"):
            raise ValueError(f"dispositivo de debug no escribible: {device_id!r}")
        device.write_state(state)

    def step(self) -> dict:
        """Execute one CPU instruction and sync devices.

        Returns the CPU snapshot after the step.  Sets ``frame_completed``
        to True when this step crosses a frame boundary.
        """
        self.frame_completed = False

        if not self._in_frame:
            self.machine.frame_tstates = 0
            if self._begin_frame is not None:
                self._begin_frame()
            self._in_frame = True

        used = self.machine.cpu.step()
        self.last_step_cycles = used

        if used > 0:
            self.machine.tstates += used
            self.machine.frame_tstates += used
            self.machine._run_devices_until(self.machine.frame_tstates)

        if (
            self._tstates_per_frame > 0
            and self.machine.frame_tstates >= self._tstates_per_frame
        ):
            if self._finish_frame is not None:
                self._finish_frame()
            self.machine.frame_tstates = 0
            self._in_frame = False
            self.frame_completed = True

        return self.machine.cpu.snapshot()

    def read_state(self) -> dict:
        if hasattr(self.machine, "read_state"):
            return self.machine.read_state()
        state = {
            "__meta__": {"type": type(self.machine).__name__},
            "tstates": getattr(self.machine, "tstates", 0),
            "frame_tstates": getattr(self.machine, "frame_tstates", 0),
            "frame_counter": getattr(self.machine, "frame_counter", 0),
        }
        cpu = getattr(self.machine, "cpu", None)
        if cpu is not None and hasattr(cpu, "read_state"):
            state["cpu"] = cpu.read_state()
        return state

    def write_state(self, state: dict) -> None:
        if hasattr(self.machine, "write_state"):
            self.machine.write_state(state)
            return
        if "tstates" in state:
            self.machine.tstates = int(state["tstates"])
        if "frame_tstates" in state:
            self.machine.frame_tstates = int(state["frame_tstates"])
        if "frame_counter" in state:
            self.machine.frame_counter = int(state["frame_counter"])
        cpu = getattr(self.machine, "cpu", None)
        if cpu is not None and "cpu" in state and hasattr(cpu, "write_state"):
            cpu.write_state(state["cpu"])

    def read_memory(self, addr: int, count: int) -> list[int]:
        return [self.machine.bus.read8(addr + i) for i in range(count)]

    def write_memory(self, addr: int, data: list[int]) -> None:
        for i, value in enumerate(data):
            self.machine.bus.write8(addr + i, value & 0xFF)
