from __future__ import annotations

from pathlib import Path

import pytest

from multiemu.machine_registry import instantiate_machine


def _write(path: Path, data: bytes) -> str:
    path.write_bytes(data)
    return str(path)


def _gb_rom() -> bytes:
    rom = bytearray(0x8000)
    rom[0x0134:0x013B] = b"STATEGB"
    rom[0x0147] = 0x00
    rom[0x0148] = 0x00
    rom[0x0149] = 0x00
    return bytes(rom)


def _roms_for(machine_id: str, tmp_path: Path) -> dict[str, str]:
    if machine_id.startswith("spectrum"):
        size = 0x8000 if machine_id in {"spectrum128k", "spectrumplus2"} else 0x4000
        return {"main": _write(tmp_path / f"{machine_id}.rom", bytes([0x00]) * size)}
    if machine_id == "mastersystem2":
        return {"main": _write(tmp_path / "cart.sms", bytes([0x00]) * 0x8000)}
    if machine_id == "gamegear":
        return {"main": _write(tmp_path / "cart.gg", bytes([0x00]) * 0x8000)}
    if machine_id == "colecovision":
        return {
            "bios": _write(tmp_path / "coleco.rom", bytes([0x00]) * 0x2000),
            "main": _write(tmp_path / "cart.col", bytes([0x00]) * 0x8000),
        }
    if machine_id == "msx":
        return {
            "bios": _write(tmp_path / "msx_bios.rom", bytes([0xC3]) * 0x4000),
            "basic": _write(tmp_path / "msx_basic.rom", bytes([0x55]) * 0x4000),
        }
    if machine_id.startswith("cpc"):
        return {
            "os": _write(tmp_path / f"{machine_id}_os.rom", bytes([0x00]) * 0x4000),
            "basic": _write(tmp_path / f"{machine_id}_basic.rom", bytes([0xC9]) * 0x4000),
        }
    if machine_id in {"gameboy", "gameboycolor", "gbc"}:
        return {"main": _write(tmp_path / f"{machine_id}.gb", _gb_rom())}
    if machine_id == "kim1":
        return {
            "lower": _write(tmp_path / "kim_lower.bin", bytes([0xEA]) * 0x0400),
            "upper": _write(tmp_path / "kim_upper.bin", bytes([0xEA]) * 0x0400),
        }
    if machine_id in {"vic20", "vic20ntsc", "vic20pal"}:
        basic = bytes([0xEA]) * 0x2000
        kernal = bytearray([0xEA] * 0x2000)
        kernal[-4] = 0x00
        kernal[-3] = 0xE0
        return {
            "basic": _write(tmp_path / f"{machine_id}_basic.bin", basic),
            "kernal": _write(tmp_path / f"{machine_id}_kernal.bin", bytes(kernal)),
            "char": _write(tmp_path / f"{machine_id}_char.bin", bytes([0x00]) * 0x1000),
        }
    raise AssertionError(f"missing test ROM setup for {machine_id}")


def _mutate(machine) -> None:
    machine.cpu.write_state({"PC": 0x1234})
    if hasattr(machine, "poke") and machine.machine_id.startswith("spectrum"):
        machine.poke(0x4000, 0x5A)
        machine.keyboard_rows[0] = 0x1E
        machine.border_color = 3
    elif machine.machine_id == "mastersystem2":
        machine.poke(0xC000, 0x5A)
        machine._set_pad_control(1, 0, True)
    elif machine.machine_id == "gamegear":
        machine.poke(0xC000, 0x5A)
        machine._set_pad_control(1, 0, True)
        machine._set_pad_control(1, 2, True)
    elif machine.machine_id == "colecovision":
        machine.poke(0x6000, 0x5A)
        machine._set_pad_control(1, 0, True)
        machine._set_pad_control(1, 6, True)
    elif machine.machine_id == "msx":
        machine._port_write(0xA8, 0xF3)
        machine.poke(0x0002, 0x5A)
        machine.keyboard_matrix[8] = 0xFE
        machine.joystick_ports[0] = 0x3E
    elif machine.machine_id.startswith("cpc"):
        machine.poke(0x1234, 0x5A)
        machine.lower_rom_enabled = False
        machine.keyboard_lines[2] = 0x7F
        machine.joystick_state = 0x12
    elif machine.machine_id in {"gameboy", "gameboycolor", "gbc"}:
        machine.bus.write8(0xC000, 0x5A)
        machine.joypad.press(0, 0)
        if hasattr(machine, "write_vbk"):
            machine.write_vbk(1)
            machine.write_svbk(3)
    elif machine.machine_id == "kim1":
        machine.ram.load(0x10, bytes([0x5A]))
        machine.monitor_ram.load(0x02, bytes([0xA5]))
        machine.riot.set_keypad_matrix([0xFE, 0xFF, 0xFF])
    elif machine.machine_id in {"vic20", "vic20ntsc", "vic20pal"}:
        machine.bus.write8(0x0002, 0x5A)
        machine.bus.write8(0x1002, 0xA5)
        machine.bus.write8(0x9402, 0x0B)
        machine.joystick_state = 0x12


def _assert_restored(machine) -> None:
    assert machine.cpu.snapshot()["PC"] == 0x1234
    if machine.machine_id.startswith("spectrum"):
        assert machine.peek(0x4000) == 0x5A
        assert machine.keyboard_rows[0] == 0x1E
        assert machine.border_color == 3
    elif machine.machine_id == "mastersystem2":
        assert machine.peek(0xC000) == 0x5A
        assert machine._pad1_state & 0x10 == 0
    elif machine.machine_id == "gamegear":
        assert machine.peek(0xC000) == 0x5A
        assert machine._pad1_state & 0x10 == 0
        assert machine._port_read(0x00) & 0x80 == 0
    elif machine.machine_id == "colecovision":
        assert machine.peek(0x6000) == 0x5A
        assert machine._pad1_state & 0x01 == 0
        assert machine._pad1_state & 0x40 == 0
    elif machine.machine_id == "msx":
        assert machine.slot_register == 0xF3
        assert machine.peek(0x0002) == 0x5A
        assert machine.keyboard_matrix[8] == 0xFE
        assert machine.joystick_ports[0] == 0x3E
    elif machine.machine_id.startswith("cpc"):
        assert machine.ram.peek(0x1234) == 0x5A
        assert machine.lower_rom_enabled is False
        assert machine.keyboard_lines[2] == 0x7F
        assert machine.joystick_state == 0x12
    elif machine.machine_id in {"gameboy", "gameboycolor", "gbc"}:
        assert machine.bus.read8(0xC000) == 0x5A
        assert machine.joypad.read_state()["direction_state"] & 0x01 == 0
        if hasattr(machine, "read_vbk"):
            assert machine.vbk == 1
            assert machine.svbk == 3
    elif machine.machine_id == "kim1":
        assert machine.ram.peek(0x10) == 0x5A
        assert machine.monitor_ram.peek(0x02) == 0xA5
        assert machine.riot.key_rows[0] == 0xFE
    elif machine.machine_id in {"vic20", "vic20ntsc", "vic20pal"}:
        assert machine.bus.read8(0x0002) == 0x5A
        assert machine.bus.read8(0x1002) == 0xA5
        assert machine.bus.read8(0x9402) & 0x0F == 0x0B
        assert machine.joystick_state == 0x12


@pytest.mark.parametrize(
    "machine_id",
    [
        "spectrum16k",
        "spectrum48k",
        "spectrum128k",
        "spectrumplus2",
        "mastersystem2",
        "gamegear",
        "colecovision",
        "msx",
        "cpc464",
        "cpc664",
        "cpc6128",
        "gameboy",
        "gameboycolor",
        "gbc",
        "kim1",
        "vic20",
        "vic20ntsc",
        "vic20pal",
    ],
)
def test_machine_state_dump_roundtrips_through_registry(machine_id: str, tmp_path: Path):
    roms = _roms_for(machine_id, tmp_path)
    machine = instantiate_machine(machine_id, roms=roms)
    _mutate(machine)

    state_dump = {
        "machine_id": machine_id,
        "rom_paths": roms,
        "state": machine.read_state(),
    }

    restored = instantiate_machine(machine_id, state_dump=state_dump)

    _assert_restored(restored)
