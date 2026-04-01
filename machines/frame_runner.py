from __future__ import annotations


class SteppedFrameRunner:
    """Generic frame runner for machines that advance by CPU steps."""

    def __init__(self, tstates_per_frame: int):
        self.tstates_per_frame = int(tstates_per_frame)

    def run(
        self,
        machine,
        cpu_step,
        run_devices_until=None,
        before_frame=None,
        after_loop=None,
        run_delta_devices=(),
        run_tstate_devices=(),
        device_clock_attr=None,
    ):
        tstates = machine.tstates
        frame_tstates = 0
        device_clock = 0

        machine.frame_tstates = 0
        if before_frame is not None:
            before_frame()

        while frame_tstates < self.tstates_per_frame:
            used = cpu_step()
            tstates += used
            frame_tstates += used
            machine.tstates = tstates
            machine.frame_tstates = frame_tstates
            if run_devices_until is not None:
                run_devices_until(frame_tstates)
            elif device_clock_attr is not None:
                delta = frame_tstates - device_clock
                if delta > 0:
                    for run_delta in run_delta_devices:
                        run_delta(delta)
                    for run_tstate in run_tstate_devices:
                        run_tstate(frame_tstates)
                    device_clock = frame_tstates
            if used <= 0:
                break

        if device_clock_attr is not None:
            setattr(machine, device_clock_attr, device_clock)
        if after_loop is not None:
            after_loop()
        return tstates

    def run_scaled(
        self,
        machine,
        cpu_step,
        tstates_per_frame,
        scale_divisor=1,
        before_frame=None,
        after_loop=None,
        run_delta_devices=(),
        scaled_run_delta_devices=(),
        scaled_run_tstate_devices=(),
        device_clock_attr=None,
        scaled_clock_attr=None,
    ):
        tstates = machine.tstates
        frame_tstates = 0
        device_clock = 0
        scaled_clock = 0
        scale_remainder = 0

        scale_divisor = max(1, int(scale_divisor))
        machine.frame_tstates = 0
        if before_frame is not None:
            before_frame()

        while frame_tstates < int(tstates_per_frame):
            used = cpu_step()
            tstates += used
            frame_tstates += used
            machine.tstates = tstates
            machine.frame_tstates = frame_tstates
            delta = frame_tstates - device_clock
            if delta > 0:
                for run_delta in run_delta_devices:
                    run_delta(delta)
                if scale_divisor == 1:
                    scaled_delta = delta
                else:
                    scale_remainder += delta
                    scaled_delta = scale_remainder // scale_divisor
                    scale_remainder %= scale_divisor
                if scaled_delta > 0:
                    scaled_clock += scaled_delta
                    for run_delta in scaled_run_delta_devices:
                        run_delta(scaled_delta)
                    for run_tstate in scaled_run_tstate_devices:
                        run_tstate(scaled_clock)
                device_clock = frame_tstates
            if used <= 0:
                break

        if device_clock_attr is not None:
            setattr(machine, device_clock_attr, device_clock)
        if scaled_clock_attr is not None:
            setattr(machine, scaled_clock_attr, scaled_clock)
        if after_loop is not None:
            after_loop()
        return tstates


class ScanlineFrameRunner:
    """Generic frame runner for machines that advance one scanline at a time."""

    def __init__(self, scanline_count: int, tstates_per_line: int):
        self.scanline_count = int(scanline_count)
        if isinstance(tstates_per_line, (list, tuple)):
            self.tstates_per_line = [int(v) for v in tstates_per_line]
        else:
            self.tstates_per_line = int(tstates_per_line)

    def run(
        self,
        machine,
        cpu_run_cycles,
        before_frame=None,
        before_scanline=None,
        after_cpu=None,
        end_scanline=None,
        after_frame=None,
    ):
        machine.frame_tstates = 0

        if before_frame is not None:
            before_frame()

        for scanline in range(self.scanline_count):
            if before_scanline is not None:
                before_scanline(scanline)

            if isinstance(self.tstates_per_line, list):
                line_tstates = self.tstates_per_line[scanline]
            else:
                line_tstates = self.tstates_per_line

            used = cpu_run_cycles(line_tstates)
            machine.tstates += used
            machine.frame_tstates += used

            if after_cpu is not None:
                after_cpu(machine.frame_tstates, scanline)

            if end_scanline is not None:
                end_scanline(scanline)

        if after_frame is not None:
            after_frame()

        return machine.tstates
