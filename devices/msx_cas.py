from __future__ import annotations


class MSXCassetteTape:
    """Byte-oriented MSX CAS reader for BIOS cassette input hooks."""

    MAGIC = b"\x1F\xA6\xDE\xBA\xCC\x13\x7D\x74"

    def __init__(self, records: list[bytes] | None = None):
        self.records = [bytes(record) for record in (records or [])]
        self.stream = b"".join(self.records)
        self.record_index = 0
        self.active_record_index = -1
        self.position = 0
        self.opened = False

    @classmethod
    def from_bytes(cls, data: bytes) -> "MSXCassetteTape":
        records: list[bytes] = []
        cursor = 0
        while cursor < len(data):
            marker = data.find(cls.MAGIC, cursor)
            if marker < 0:
                break
            payload_start = marker + len(cls.MAGIC)
            next_marker = data.find(cls.MAGIC, payload_start)
            payload_end = len(data) if next_marker < 0 else next_marker
            records.append(data[payload_start:payload_end])
            cursor = payload_end
        if not records and data:
            records.append(bytes(data))
        return cls(records)

    def reset(self) -> None:
        self.record_index = 0
        self.active_record_index = -1
        self.position = 0
        self.opened = False

    def open_for_read(self) -> bool:
        if self.record_index >= len(self.records):
            self.active_record_index = -1
            self.position = 0
            self.opened = False
            return False
        self.active_record_index = self.record_index
        self.record_index += 1
        self.position = 0
        self.opened = True
        return self.opened

    def close(self) -> None:
        self.opened = False

    def read_byte(self) -> int | None:
        if not self.opened or not (0 <= self.active_record_index < len(self.records)):
            return None
        record = self.records[self.active_record_index]
        if self.position >= len(record):
            self.opened = False
            return None
        value = record[self.position]
        self.position += 1
        return value

    @property
    def bytes_read(self) -> int:
        total = 0
        if self.active_record_index > 0:
            total += sum(len(record) for record in self.records[:self.active_record_index])
        if self.active_record_index >= 0:
            total += min(self.position, len(self.records[self.active_record_index]))
        return total

    @property
    def total_bytes(self) -> int:
        return len(self.stream)

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": "MSXCassetteTape"},
            "records": [list(record) for record in self.records],
            "record_index": self.record_index,
            "active_record_index": self.active_record_index,
            "position": self.position,
            "opened": self.opened,
        }

    def write_state(self, state: dict) -> None:
        if "records" in state:
            self.records = [bytes(int(value) & 0xFF for value in record) for record in state["records"]]
            self.stream = b"".join(self.records)
        if "record_index" in state:
            self.record_index = max(0, min(int(state["record_index"]), len(self.records)))
        if "active_record_index" in state:
            self.active_record_index = max(-1, min(int(state["active_record_index"]), len(self.records) - 1))
        if "position" in state:
            max_position = 0
            if 0 <= self.active_record_index < len(self.records):
                max_position = len(self.records[self.active_record_index])
            self.position = max(0, min(int(state["position"]), max_position))
        if "opened" in state:
            self.opened = bool(state["opened"])
