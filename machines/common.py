from __future__ import annotations

"""Cold-path helpers shared across machine families.

Keep this module limited to setup, validation and state/debug packaging
helpers. Anything that runs per CPU step, per scanline or per audio sample
stays in the machine or chip implementation so refactors here remain
performance-safe.
"""

from hashlib import sha256


def rom_sha256(data: bytes) -> str | None:
    if not data:
        return None
    return sha256(data).hexdigest()


def pad_rom(data: bytes, size: int, *, fill_byte: int = 0xFF) -> bytes:
    if len(data) >= size:
        return data[:size]
    return data + bytes([fill_byte & 0xFF]) * (size - len(data))


def split_rom_banks(rom_data: bytes, page_size: int, *, fill_byte: int = 0xFF) -> list[bytes]:
    if page_size <= 0:
        raise ValueError("page_size fuera de rango")
    if not rom_data:
        return [bytes([fill_byte & 0xFF]) * page_size]

    banks: list[bytes] = []
    for offset in range(0, len(rom_data), page_size):
        bank = rom_data[offset:offset + page_size]
        if len(bank) < page_size:
            bank = bank + bytes([fill_byte & 0xFF]) * (page_size - len(bank))
        banks.append(bank)
    return banks or [bytes([fill_byte & 0xFF]) * page_size]


class ByteArrayMemoryDebugDevice:
    """Generic writable memory view for debug/state tooling."""

    def __init__(self, machine, *, attr_name: str, size: int, meta_type: str):
        self.machine = machine
        self.attr_name = attr_name
        self.size = int(size)
        self.meta_type = meta_type

    @property
    def _data(self):
        return getattr(self.machine, self.attr_name)

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": self.meta_type, "size": self.size},
            "data": list(self._data),
        }

    def write_state(self, state: dict) -> None:
        if "data" not in state:
            return
        values = bytes(int(v) & 0xFF for v in state["data"])
        if len(values) != self.size:
            raise ValueError(f"{self.meta_type} debe medir {self.size} bytes")
        self._data[:] = values


class ReadOnlyBlobDebugDevice:
    """Generic read-only ROM/blob descriptor for debug tooling."""

    def __init__(self, machine, *, attr_name: str, meta_type: str):
        self.machine = machine
        self.attr_name = attr_name
        self.meta_type = meta_type

    @property
    def _data(self) -> bytes:
        return getattr(self.machine, self.attr_name)

    def read_state(self) -> dict:
        return {
            "__meta__": {"type": self.meta_type, "writable": False},
            "size": len(self._data),
            "sha256": rom_sha256(self._data),
        }


def validate_state_blobs(state: dict, *, context: str, blobs: dict[str, bytes]) -> None:
    for prefix, data in blobs.items():
        size_key = f"{prefix}_size"
        hash_key = f"{prefix}_sha256"
        actual_size = len(data)
        actual_hash = rom_sha256(data)
        if size_key in state and int(state[size_key]) != actual_size:
            raise ValueError(f"snapshot {context} incompatible: {prefix} size distinto")
        if hash_key in state and state[hash_key] != actual_hash:
            raise ValueError(f"snapshot {context} incompatible: {prefix} SHA256 distinto")


def blob_state_fields(blobs: dict[str, bytes]) -> dict[str, int | str | None]:
    fields: dict[str, int | str | None] = {}
    for prefix, data in blobs.items():
        fields[f"{prefix}_size"] = len(data)
        fields[f"{prefix}_sha256"] = rom_sha256(data)
    return fields


def restore_byte_array_state(target: bytearray, values, *, label: str) -> None:
    payload = bytes(int(v) & 0xFF for v in values)
    if len(payload) != len(target):
        raise ValueError(f"{label} debe medir {len(target)} bytes")
    target[:] = payload


def restore_fixed_length_list(
    values,
    *,
    length: int,
    mask: int,
    fill: int,
) -> list[int]:
    restored = [int(v) & mask for v in values[:length]]
    if len(restored) < length:
        restored += [fill] * (length - len(restored))
    return restored


def build_debug_devices(
    machine,
    base_devices: list[dict],
    entries: list[tuple[str, object, str, str, bool | None]],
) -> list[dict]:
    devices = list(base_devices)
    for device_id, device, category, label, writable in entries:
        kwargs = {"label": label}
        if writable is not None:
            kwargs["writable"] = writable
        devices.append(machine._debug_device(device_id, device, category, **kwargs))
    return devices
