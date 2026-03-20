from __future__ import annotations

from machines.frame_runner import ScanlineFrameRunner, SteppedFrameRunner


class _FakeMachine:
    def __init__(self):
        self.tstates = 0
        self.frame_tstates = 0
        self.events = []


class _FakeStepCPU:
    def __init__(self, steps):
        self._steps = list(steps)

    def step(self):
        return self._steps.pop(0) if self._steps else 0


class _FakeCycleCPU:
    def __init__(self, per_line):
        self.per_line = per_line

    def run_cycles(self, cycles):
        assert cycles == self.per_line
        return cycles


def test_stepped_frame_runner_updates_machine_tstate_counters():
    machine = _FakeMachine()
    cpu = _FakeStepCPU([4, 4, 4, 4, 4])
    runner = SteppedFrameRunner(16)

    def before_frame():
        machine.events.append(("begin", machine.frame_tstates))

    def run_devices_until(tstates):
        machine.events.append(("devices", tstates))

    def after_loop():
        machine.events.append(("end", machine.frame_tstates))

    used = runner.run(
        machine,
        cpu_step=cpu.step,
        run_devices_until=run_devices_until,
        before_frame=before_frame,
        after_loop=after_loop,
    )

    assert used == 16
    assert machine.tstates == 16
    assert machine.frame_tstates == 16
    assert machine.events == [
        ("begin", 0),
        ("devices", 4),
        ("devices", 8),
        ("devices", 12),
        ("devices", 16),
        ("end", 16),
    ]


def test_stepped_frame_runner_exposes_live_frame_tstates_to_callbacks():
    machine = _FakeMachine()
    cpu = _FakeStepCPU([3, 5, 8])
    runner = SteppedFrameRunner(16)
    seen = []

    def run_devices_until(_tstates):
        seen.append((machine.tstates, machine.frame_tstates))

    runner.run(machine, cpu.step, run_devices_until)

    assert seen == [(3, 3), (8, 8), (16, 16)]


def test_scanline_frame_runner_calls_hooks_in_scanline_order():
    machine = _FakeMachine()
    cpu = _FakeCycleCPU(8)
    runner = ScanlineFrameRunner(3, 8)

    def before_frame():
        machine.events.append(("begin",))

    def before_scanline(scanline):
        machine.events.append(("line_begin", scanline))

    def after_cpu(frame_tstates, scanline):
        machine.events.append(("after_cpu", scanline, frame_tstates))

    def end_scanline(scanline):
        machine.events.append(("line_end", scanline))

    def after_frame():
        machine.events.append(("end", machine.frame_tstates))

    used = runner.run(
        machine,
        cpu_run_cycles=cpu.run_cycles,
        before_frame=before_frame,
        before_scanline=before_scanline,
        after_cpu=after_cpu,
        end_scanline=end_scanline,
        after_frame=after_frame,
    )

    assert used == 24
    assert machine.tstates == 24
    assert machine.frame_tstates == 24
    assert machine.events == [
        ("begin",),
        ("line_begin", 0),
        ("after_cpu", 0, 8),
        ("line_end", 0),
        ("line_begin", 1),
        ("after_cpu", 1, 16),
        ("line_end", 1),
        ("line_begin", 2),
        ("after_cpu", 2, 24),
        ("line_end", 2),
        ("end", 24),
    ]
