# cython: boundscheck=False
# cython: wraparound=False
# cython: initializedcheck=False
# cython: cdivision=True

from __future__ import annotations


cdef class SteppedFrameRunner:
    """Generic frame runner for machines that advance by CPU steps."""

    cdef public int tstates_per_frame

    def __init__(self, int tstates_per_frame):
        self.tstates_per_frame = tstates_per_frame

    cpdef object run(
        self,
        object machine,
        object cpu_step,
        object run_devices_until=None,
        object before_frame=None,
        object after_loop=None,
        object run_delta_devices=(),
        object run_tstate_devices=(),
        object device_clock_attr=None,
    ):
        cdef long long tstates = machine.tstates
        cdef int frame_tstates = 0
        cdef int device_clock = 0
        cdef int delta
        cdef int used
        cdef object run_delta
        cdef object run_tstate

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


cdef class ScanlineFrameRunner:
    """Generic frame runner for machines that advance one scanline at a time."""

    cdef public int scanline_count
    cdef public int tstates_per_line

    def __init__(self, int scanline_count, int tstates_per_line):
        self.scanline_count = scanline_count
        self.tstates_per_line = tstates_per_line

    cpdef object run(
        self,
        object machine,
        object cpu_run_cycles,
        object before_frame=None,
        object before_scanline=None,
        object after_cpu=None,
        object end_scanline=None,
        object after_frame=None,
    ):
        cdef int scanline
        cdef int used

        machine.frame_tstates = 0
        if before_frame is not None:
            before_frame()

        for scanline in range(self.scanline_count):
            if before_scanline is not None:
                before_scanline(scanline)

            used = cpu_run_cycles(self.tstates_per_line)
            machine.tstates += used
            machine.frame_tstates += used

            if after_cpu is not None:
                after_cpu(machine.frame_tstates, scanline)

            if end_scanline is not None:
                end_scanline(scanline)

        if after_frame is not None:
            after_frame()

        return machine.tstates
