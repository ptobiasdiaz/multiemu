from __future__ import annotations

from collections import deque

from devices.cpc_disk import CPCDiskImage


class CPCFDC:
    """Very small NEC765-style subset for CPC disk bootstrapping.

    Current scope:
    - command handshake through status/data registers
    - `SPECIFY`, `SENSE INTERRUPT`, `RECALIBRATE`, `SEEK`
    - `READ ID` and `READ DATA` against a mounted DSK image
    """

    _COMMAND_LENGTHS = {
        0x03: 3,  # SPECIFY
        0x04: 2,  # SENSE DRIVE STATUS
        0x07: 2,  # RECALIBRATE
        0x08: 1,  # SENSE INTERRUPT STATUS
        0x0A: 2,  # READ ID
        0x0F: 3,  # SEEK
    }

    def __init__(self, disk_image: CPCDiskImage | None = None):
        self.disk_image = disk_image
        self.reset()

    def reset(self) -> None:
        self.motor_on = False
        self.current_cylinder = [0, 0, 0, 0]
        self.pending_interrupt = False
        self._command = []
        self._expected_command_length = 0
        self._output = deque()

    def mount_disk(self, disk_image: CPCDiskImage | None) -> None:
        self.disk_image = disk_image

    def write_motor_control(self, value: int) -> None:
        self.motor_on = bool(value & 0x01)

    def read_main_status(self) -> int:
        status = 0x80
        if self._output:
            status |= 0x40 | 0x10
        elif self._command:
            status |= 0x10
        return status

    def read_data(self) -> int:
        if self._output:
            return self._output.popleft()
        return 0xFF

    def write_data(self, value: int) -> None:
        value &= 0xFF
        if not self._command:
            self._expected_command_length = self._resolve_command_length(value)
        self._command.append(value)
        if len(self._command) >= self._expected_command_length:
            self._execute_command()

    def _resolve_command_length(self, value: int) -> int:
        base = value & 0x1F
        if base == 0x06:
            return 9
        return self._COMMAND_LENGTHS.get(base, 1)

    def _execute_command(self) -> None:
        command = self._command
        self._command = []
        self._expected_command_length = 0
        opcode = command[0] & 0x1F

        if opcode == 0x03:  # SPECIFY
            return
        if opcode == 0x04:  # SENSE DRIVE STATUS
            drive = command[1] & 0x03
            st3 = 0x20 | drive
            self._output.extend((st3,))
            return
        if opcode == 0x07:  # RECALIBRATE
            drive = command[1] & 0x03
            self.current_cylinder[drive] = 0
            self.pending_interrupt = True
            return
        if opcode == 0x08:  # SENSE INTERRUPT STATUS
            st0 = 0x20
            if self.pending_interrupt:
                st0 |= 0x00
            self.pending_interrupt = False
            self._output.extend((st0, self.current_cylinder[0] & 0xFF))
            return
        if opcode == 0x0F:  # SEEK
            drive = command[1] & 0x03
            cylinder = command[2] & 0xFF
            self.current_cylinder[drive] = cylinder
            self.pending_interrupt = True
            return
        if opcode == 0x0A:  # READ ID
            drive = command[1] & 0x03
            head = (command[1] >> 2) & 0x01
            track = self.disk_image.get_track(self.current_cylinder[drive], head) if self.disk_image else None
            if track is None or not track.sectors:
                self._queue_result(0x40, 0x04, 0x00, self.current_cylinder[drive], head, 0x00, 0x00)
                return
            sector = track.sectors[0]
            self._queue_result(0x00, sector.st1, sector.st2, sector.c, sector.h, sector.r, sector.n)
            return
        if opcode == 0x06:  # READ DATA
            drive = command[1] & 0x03
            c = command[2] & 0xFF
            h = command[3] & 0xFF
            r = command[4] & 0xFF
            n = command[5] & 0xFF
            sector = self.disk_image.get_sector(c, h, r) if self.disk_image else None
            if sector is None:
                self._queue_result(0x40, 0x04, 0x00, c, h, r, n)
                return
            self._output.extend(sector.data)
            self._queue_result(0x00, sector.st1, sector.st2, sector.c, sector.h, sector.r, sector.n)
            self.current_cylinder[drive] = c
            return

    def _queue_result(self, st0: int, st1: int, st2: int, c: int, h: int, r: int, n: int) -> None:
        self._output.extend((st0 & 0xFF, st1 & 0xFF, st2 & 0xFF, c & 0xFF, h & 0xFF, r & 0xFF, n & 0xFF))

    def read_state(self) -> dict:
        state = {
            "__meta__": {"type": "CPCFDC"},
            "motor_on": self.motor_on,
            "current_cylinder": list(self.current_cylinder),
            "pending_interrupt": self.pending_interrupt,
            "_command": list(self._command),
            "_expected_command_length": self._expected_command_length,
            "_output": list(self._output),
        }
        if self.disk_image is not None and hasattr(self.disk_image, "read_state"):
            state["disk_image"] = self.disk_image.read_state()
        return state

    def write_state(self, state: dict) -> None:
        if "motor_on" in state:
            self.motor_on = bool(state["motor_on"])
        if "current_cylinder" in state:
            self.current_cylinder = [int(v) & 0xFF for v in state["current_cylinder"][:4]]
        if "pending_interrupt" in state:
            self.pending_interrupt = bool(state["pending_interrupt"])
        if "_command" in state:
            self._command = [int(v) & 0xFF for v in state["_command"]]
        if "_expected_command_length" in state:
            self._expected_command_length = int(state["_expected_command_length"])
        if "_output" in state:
            self._output = deque(int(v) & 0xFF for v in state["_output"])
        if "disk_image" in state:
            if self.disk_image is None:
                self.disk_image = CPCDiskImage({})
            self.disk_image.write_state(state["disk_image"])
