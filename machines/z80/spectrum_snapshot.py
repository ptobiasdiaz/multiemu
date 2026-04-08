from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Z80Snapshot:
    model: str
    border_color: int
    frame_tstates: int
    last_out_7ffd: int
    ay_register_index: int
    ay_registers: bytes
    cpu_state: dict
    ram_48k: bytes | None = None
    ram_banks_128k: dict[int, bytes] | None = None


def _u16(data: bytes, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8)


def _decompress_block(data: bytes, expected_length: int) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data) and len(out) < expected_length:
        if i + 3 < len(data) and data[i] == 0xED and data[i + 1] == 0xED:
            count = data[i + 2]
            value = data[i + 3]
            if count == 0:
                raise ValueError("snapshot .z80 inválido: repetición ED ED con contador cero")
            out.extend([value] * count)
            i += 4
            continue
        out.append(data[i])
        i += 1
    if len(out) != expected_length:
        raise ValueError(
            f"snapshot .z80 inválido: bloque RAM con tamaño {len(out)}; se esperaban {expected_length} bytes"
        )
    return bytes(out)


def _version1_ram(snapshot: bytes, compressed: bool) -> bytes:
    body = snapshot[30:]
    if compressed:
        return _decompress_block(body, 48 * 1024)
    if len(body) < 48 * 1024:
        raise ValueError("snapshot .z80 inválido: RAM truncada para snapshot v1")
    return body[: 48 * 1024]


def _decode_model(version: int, hardware_mode: int, modifier_flags: int) -> str:
    if version == 1:
        return "48k"

    modified = (modifier_flags & 0x80) != 0
    if version == 2:
        if hardware_mode in {3, 4}:
            return "plus2" if modified else "128k"
        return "48k"

    if hardware_mode == 12:
        return "plus2"
    if hardware_mode in {4, 5, 6}:
        return "plus2" if modified else "128k"
    return "48k"


def _decode_frame_tstates(snapshot: bytes, ext_len: int) -> int:
    if ext_len < 28 or len(snapshot) < 58:
        return 0
    low = _u16(snapshot, 55)
    hi = snapshot[57] & 0x03
    if low > 17472:
        low = 17472
    quarter = (hi + 1) & 0x03
    tstates = quarter * 17472 + (17472 - low)
    return tstates % 69888


def _parse_header(snapshot: bytes, version: int, ext_len: int = 0) -> tuple[dict, int]:
    flags1 = snapshot[12]
    r_value = (snapshot[11] & 0x7F) | ((flags1 & 0x01) << 7)
    if version == 1:
        pc = _u16(snapshot, 6)
        im = snapshot[29] & 0x03
    else:
        pc = _u16(snapshot, 32)
        im = snapshot[29] & 0x03

    cpu_state = {
        "A": snapshot[0],
        "F": snapshot[1],
        "C": snapshot[2],
        "B": snapshot[3],
        "L": snapshot[4],
        "H": snapshot[5],
        "PC": pc,
        "SP": _u16(snapshot, 8),
        "I": snapshot[10],
        "R": r_value,
        "E": snapshot[13],
        "D": snapshot[14],
        "C2": snapshot[15],
        "B2": snapshot[16],
        "E2": snapshot[17],
        "D2": snapshot[18],
        "L2": snapshot[19],
        "H2": snapshot[20],
        "A2": snapshot[21],
        "F2": snapshot[22],
        "IY": _u16(snapshot, 23),
        "IX": _u16(snapshot, 25),
        "iff1": snapshot[27] != 0,
        "iff2": snapshot[28] != 0,
        "im": im,
        "halted": False,
        "ei_pending": False,
    }
    return cpu_state, (flags1 >> 1) & 0x07


def parse_z80_snapshot(snapshot: bytes) -> Z80Snapshot:
    if len(snapshot) < 30:
        raise ValueError("snapshot .z80 inválido: cabecera demasiado corta")

    header_pc = _u16(snapshot, 6)
    cpu_state, border_color = _parse_header(snapshot, 1 if header_pc != 0 else 2)

    if header_pc != 0:
        compressed = (snapshot[12] & 0x20) != 0
        ram_48k = _version1_ram(snapshot, compressed)
        return Z80Snapshot(
            model="48k",
            border_color=border_color,
            frame_tstates=0,
            last_out_7ffd=0,
            ay_register_index=0,
            ay_registers=bytes(16),
            cpu_state=cpu_state,
            ram_48k=ram_48k,
        )

    ext_len = _u16(snapshot, 30)
    version = 2 if ext_len == 23 else 3
    if len(snapshot) < 32 + ext_len:
        raise ValueError("snapshot .z80 inválido: cabecera extendida truncada")

    cpu_state, border_color = _parse_header(snapshot, version, ext_len)
    hardware_mode = snapshot[34]
    out_7ffd = snapshot[35] if ext_len >= 3 else 0
    modifier_flags = snapshot[37] if ext_len >= 8 else 0
    ay_index = snapshot[38] if ext_len >= 9 else 0
    ay_regs = snapshot[39:55] if ext_len >= 25 else bytes(16)
    frame_tstates = _decode_frame_tstates(snapshot, ext_len)
    model = _decode_model(version, hardware_mode, modifier_flags)

    blocks_offset = 32 + ext_len
    pos = blocks_offset
    ram_48k_parts: dict[int, bytes] = {}
    ram_banks_128k: dict[int, bytes] = {}
    while pos < len(snapshot):
        if pos + 3 > len(snapshot):
            raise ValueError("snapshot .z80 inválido: bloque RAM truncado")
        block_len = _u16(snapshot, pos)
        page = snapshot[pos + 2]
        pos += 3
        if block_len == 0xFFFF:
            raw_len = 0x4000
            if pos + raw_len > len(snapshot):
                raise ValueError("snapshot .z80 inválido: bloque RAM raw truncado")
            block = snapshot[pos:pos + raw_len]
            pos += raw_len
        else:
            if pos + block_len > len(snapshot):
                raise ValueError("snapshot .z80 inválido: bloque RAM comprimido truncado")
            block = _decompress_block(snapshot[pos:pos + block_len], 0x4000)
            pos += block_len

        if model == "48k":
            if page in {4, 5, 8}:
                ram_48k_parts[page] = block
        else:
            if 3 <= page <= 10:
                ram_banks_128k[page - 3] = block

    if model == "48k":
        if set(ram_48k_parts) != {4, 5, 8}:
            raise ValueError("snapshot .z80 inválido: faltan páginas RAM de 48K")
        ram_48k = ram_48k_parts[8] + ram_48k_parts[4] + ram_48k_parts[5]
        return Z80Snapshot(
            model=model,
            border_color=border_color,
            frame_tstates=frame_tstates,
            last_out_7ffd=0,
            ay_register_index=ay_index,
            ay_registers=bytes(ay_regs).ljust(16, b"\x00")[:16],
            cpu_state=cpu_state,
            ram_48k=ram_48k,
        )

    if len(ram_banks_128k) != 8:
        raise ValueError("snapshot .z80 inválido: faltan bancos RAM de 128K/+2")
    return Z80Snapshot(
        model=model,
        border_color=border_color,
        frame_tstates=frame_tstates,
        last_out_7ffd=out_7ffd,
        ay_register_index=ay_index,
        ay_registers=bytes(ay_regs).ljust(16, b"\x00")[:16],
        cpu_state=cpu_state,
        ram_banks_128k=ram_banks_128k,
    )


def apply_z80_snapshot(machine, snapshot_data: bytes) -> None:
    snap = parse_z80_snapshot(snapshot_data)
    machine_type = getattr(machine, "machine_id", "")

    if snap.model == "48k":
        if machine_type not in {"spectrum16k", "spectrum48k", "spectrum128k", "spectrumplus2"}:
            raise ValueError(f"snapshot .z80 incompatible con máquina {machine_type!r}")
        if snap.ram_48k is None:
            raise ValueError("snapshot .z80 inválido: RAM 48K ausente")
        if hasattr(machine, "load_ram"):
            machine.load_ram(0x4000, snap.ram_48k[: machine.ram_top - 0x4000])
        if machine_type in {"spectrum128k", "spectrumplus2"} and hasattr(machine, "_write_7ffd"):
            # 48K snapshots restored on 128K/+2 hardware must run with the
            # 48 BASIC ROM selected, not the 128 editor/menu ROM.
            machine._write_7ffd(0x10)
    else:
        if machine_type not in {"spectrum128k", "spectrumplus2"}:
            raise ValueError(f"snapshot .z80 de 128K/+2 incompatible con máquina {machine_type!r}")
        assert snap.ram_banks_128k is not None
        for bank, block in snap.ram_banks_128k.items():
            machine.load_ram_bank(bank, 0, block)
        machine._write_7ffd(snap.last_out_7ffd)
        machine.paging_locked = bool(snap.last_out_7ffd & 0x20)
        machine.last_out_7ffd = snap.last_out_7ffd & 0xFF
        for index, value in enumerate(snap.ay_registers):
            machine.psg.select_register(index)
            machine.psg.write_selected(value)
        machine.psg.select_register(snap.ay_register_index & 0x0F)

    machine.cpu.write_state(snap.cpu_state)
    machine.border_color = snap.border_color & 0x07
    machine.last_out_fe = snap.border_color & 0x07
    machine.frame_tstates = snap.frame_tstates
    machine.tstates = snap.frame_tstates
    if hasattr(machine, "ula"):
        machine.ula.last_tstates = snap.frame_tstates
        if hasattr(machine.ula, "interrupt_fired"):
            machine.ula.interrupt_fired = snap.frame_tstates >= getattr(machine.ula, "INTERRUPT_TSTATE", 0)
