from __future__ import annotations

from pathlib import Path

import pytest

from chipsets.m6530 import M6530
from frontend.input_events import InputEvent
from machines import KIM1
from multiemu.machine_registry import get_machine_spec, instantiate_machine, parse_cli_rom_specs


def _make_monitor_rom() -> bytes:
    rom = bytearray([0xEA] * 0x0800)
    program = bytes(
        [
            0xA9, 0x7F,        # LDA #7F
            0x8D, 0x41, 0x17,  # STA $1741 (DDRA)
            0xA9, 0xFF,        # LDA #FF
            0x8D, 0x43, 0x17,  # STA $1743 (DDRB)
            0xA9, 0x3F,        # LDA #3F
            0x8D, 0x40, 0x17,  # STA $1740 (segments)
            0xA9, 0x09,        # LDA #09
            0x8D, 0x42, 0x17,  # STA $1742 (digit 0)
            0x00,              # BRK
        ]
    )
    rom[0x0000:0x0000 + len(program)] = program
    for offset in (0x03FA, 0x03FC, 0x03FE):
        rom[offset] = 0x00
        rom[offset + 1] = 0x1C
    return bytes(rom)


ROOT = Path(__file__).resolve().parents[1]
KIM1_LOWER_ROM = ROOT / "roms" / "kim1" / "6530-002.bin"
KIM1_UPPER_ROM = ROOT / "roms" / "kim1" / "6530-003.bin"
KIM1_REAL_ROM_REASON = "requiere las ROMs reales del KIM-1 en roms/kim1"


def _boot_real_kim1() -> KIM1:
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    for _ in range(5):
        machine.run_frame()
    return machine


def _press_kim1_keycode(machine: KIM1, code: int, *, frames: int = 2) -> None:
    row = code // 7
    bit = 6 - (code % 7)
    machine.handle_input_event(InputEvent("key_matrix", row, bit, True))
    for _ in range(frames):
        machine.run_frame()
    machine.handle_input_event(InputEvent("key_matrix", row, bit, False))
    for _ in range(frames):
        machine.run_frame()


def _point_value(machine: KIM1) -> int:
    return machine.ram.peek(0xFA) | (machine.ram.peek(0xFB) << 8)


def _step_kim1(machine: KIM1, steps: int) -> None:
    for _ in range(steps):
        used = machine.cpu.step()
        machine.tstates += used
        machine.riot.run_cycles(used)


def _step_until_pc(machine: KIM1, targets: set[int], limit: int) -> int | None:
    for _ in range(limit):
        if machine.cpu.PC in targets:
            return machine.cpu.PC
        used = machine.cpu.step()
        machine.tstates += used
        machine.riot.run_cycles(used)
    if machine.cpu.PC in targets:
        return machine.cpu.PC
    return None


def _step_until(machine: KIM1, predicate, limit: int) -> bool:
    for _ in range(limit):
        if predicate(machine):
            return True
        used = machine.cpu.step()
        machine.tstates += used
        machine.riot.run_cycles(used)
    return predicate(machine)


def test_kim1_machine_exposes_expected_geometry_and_id():
    machine = KIM1()

    assert machine.machine_id == "kim1"
    assert machine.display_name == "MOS KIM-1 (early scaffold)"
    assert machine.frame_width == 192
    assert machine.frame_height == 64
    assert len(machine.framebuffer_rgb24) == machine.frame_width * machine.frame_height * 3


def test_kim1_monitor_rom_can_write_to_display_device():
    machine = KIM1(monitor_rom_data=_make_monitor_rom())

    machine.run_frame()

    snap = machine.snapshot()
    assert snap["display_digits"][0] == 0x3F
    assert machine.riot.display_digits[0] == 0x3F


def test_kim1_can_build_monitor_from_split_lower_and_upper_roms():
    full_rom = _make_monitor_rom()

    machine = KIM1(full_rom[:0x0400], full_rom[0x0400:])

    machine.run_frame()

    assert machine.riot.display_digits[0] == 0x3F


def test_kim1_riot_exposes_display_registers_at_real_addresses():
    machine = KIM1(monitor_rom_data=_make_monitor_rom())

    machine.bus.write8(0x1741, 0x7F)
    machine.bus.write8(0x1743, 0xFF)
    machine.bus.write8(0x1740, 0x3F)
    machine.bus.write8(0x1742, 0x09)

    assert machine.riot.display_digits[0] == 0x3F


def test_kim6530_decodes_real_monitor_display_scan_codes():
    riot = M6530()
    riot.write(0x01, 0x7F)
    riot.write(0x03, 0x3F)

    for index, scan_code in enumerate((0x09, 0x0B, 0x0D, 0x0F, 0x11, 0x13)):
        riot.write(0x02, scan_code)
        riot.write(0x00, 0x01 << (index % 7))

    assert riot.display_digits == [0x01, 0x02, 0x04, 0x08, 0x10, 0x20]


def test_kim6530_blank_scan_does_not_clear_latched_digit():
    riot = M6530()
    riot.write(0x01, 0x7F)
    riot.write(0x03, 0x3F)
    riot.write(0x02, 0x09)
    riot.write(0x00, 0x3F)
    riot.write(0x00, 0x00)

    assert riot.display_digits[0] == 0x3F


def test_kim6530_reads_keypad_rows_through_monitor_scan_codes():
    riot = M6530()
    riot.set_keypad_matrix([0xFE, 0xFD, 0xFB])

    riot.write(0x02, 0x01)
    assert riot.read(0x00) == 0xFE

    riot.write(0x02, 0x23)
    assert riot.read(0x00) == 0xFD

    riot.write(0x02, 0x25)
    assert riot.read(0x00) == 0xFB


def test_kim6530_preserves_external_port_a_lines_while_scanning_keypad():
    riot = M6530()
    riot.set_port_a_input(0x80)
    riot.set_keypad_matrix([0x7E, 0x7D, 0x7B])

    riot.write(0x02, 0x01)
    assert riot.read(0x00) == 0xFE


def test_kim6530_keyboard_mode_switch_controls_sad_bit0():
    riot = M6530()

    riot.set_keyboard_mode(True)
    assert (riot.read(0x00) & 0x01) == 0x01

    riot.set_keyboard_mode(False)
    assert (riot.read(0x00) & 0x01) == 0x00


def test_kim1_reset_defaults_to_keyboard_mode_and_idle_serial_line():
    machine = KIM1()

    assert (machine.riot.read(0x00) & 0x01) == 0x01
    assert (machine.riot.read(0x00) & 0x80) == 0x80


def test_kim1_run_frame_advances_6530_timer():
    machine = KIM1()
    machine.riot.write(0x04, 4)
    machine._begin_frame()
    machine._run_devices_until(2)
    machine._run_devices_until(4)
    machine._run_devices_until(6)

    assert machine.riot.timer_timeout is True


def test_kim1_run_frame_advances_6530_devices():
    machine = KIM1(monitor_rom_data=_make_monitor_rom())
    machine.riot.write(0x04, 1)

    machine.run_frame()

    assert machine.riot.clock > 0
    assert machine.riot.timer_timeout is True


def test_kim6530_timer_timeout_raises_irq_and_reading_timer_clears_it():
    irq_events: list[str] = []
    riot = M6530()
    riot.connect_irq(lambda: irq_events.append("raise"), lambda: irq_events.append("clear"))

    riot.write(0x04, 1)
    riot.run_cycles(2)

    assert riot.timer_timeout is True
    assert irq_events == ["clear", "raise"]

    assert riot.read(0x06) == 0x00
    assert riot.timer_timeout is False
    assert irq_events == ["clear", "raise", "clear"]


def test_kim6530_queue_tty_input_drives_serial_line_on_sad_bit7():
    riot = M6530()
    riot.set_keyboard_mode(False)
    riot.queue_tty_input(b"A")

    assert (riot.read(0x00) & 0x80) == 0x80

    riot.run_cycles(1000)
    assert (riot.read(0x00) & 0x80) == 0x00

    riot.run_cycles(750)
    assert (riot.read(0x00) & 0x80) == 0x80


def test_kim6530_drain_tty_output_decodes_serial_waveform():
    riot = M6530()
    riot.tty_bit_cycles = 10
    riot.write(0x02, 0x01)
    riot.write(0x02, 0x00)
    riot.run_cycles(90)
    riot.write(0x02, 0x01)
    riot.run_cycles(10)

    assert riot.drain_tty_output() == b"\x00"


def test_kim6530_drain_tty_output_ascii_strips_high_bit_and_nuls():
    riot = M6530()
    riot._tty_tx_edges = [(0, 1), (10, 0), (20, 1)]
    riot.clock = 30
    riot.drain_tty_output = lambda: b"\x00\xc1\r\n"

    assert riot.drain_tty_output_ascii() == b"A\r\n"


def test_kim6530_calibration_input_uses_shorter_bit_width_than_regular_tty_data():
    riot = M6530()
    riot.tty_bit_cycles = 2000
    riot.queue_tty_calibration(b"X")
    first_transition = riot._tty_rx_schedule[0][0]
    riot._tty_rx_schedule.clear()
    riot._tty_rx_next_cycle = 0
    riot.queue_tty_input(b"X")
    second_transition = riot._tty_rx_schedule[0][0]

    assert first_transition < second_transition


def test_kim1_can_connect_6530_irq_line_to_the_bus_when_needed():
    machine = KIM1()
    machine.riot.connect_irq(machine.bus.request_irq, machine.bus.clear_irq)

    machine.riot.write(0x04, 1)
    machine._begin_frame()
    machine._run_devices_until(2)

    assert machine.riot.timer_timeout is True
    assert machine.bus.irq_pending is True

    assert machine.bus.read8(0x1746) == 0x00
    assert machine.bus.irq_pending is False


def test_machine_registry_exposes_kim1_as_optional_monitor_rom_machine(tmp_path):
    spec = get_machine_spec("kim1")
    assert spec.display_name == "MOS KIM-1 (early scaffold)"

    roms = parse_cli_rom_specs("kim1", ["lower=6530-002.bin", "upper=6530-003.bin"])
    assert roms["lower"].name == "6530-002.bin"
    assert roms["upper"].name == "6530-003.bin"

    full_rom = _make_monitor_rom()
    lower_path = tmp_path / "6530-002.bin"
    upper_path = tmp_path / "6530-003.bin"
    lower_path.write_bytes(full_rom[:0x0400])
    upper_path.write_bytes(full_rom[0x0400:])
    machine = instantiate_machine("kim1", roms={"lower": lower_path, "upper": upper_path})

    assert machine.machine_id == "kim1"


def test_kim1_requires_explicit_split_rom_slots():
    spec = get_machine_spec("kim1")

    assert spec.rom_slots[0].required is True
    assert spec.rom_slots[1].required is True
    assert spec.rom_slots[0].filenames == ()
    assert spec.rom_slots[1].filenames == ()


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_addr_command_shifts_open_cell_and_inserts_hex_digit():
    machine = _boot_real_kim1()
    machine.ram.write(0xFA, 0x34)
    machine.ram.write(0xFB, 0x12)
    machine.ram.write(0xFF, 0x01)

    _press_kim1_keycode(machine, 0x0A)  # key value A

    assert _point_value(machine) == 0x234A
    assert machine.ram.peek(0xFF) == 0x01


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_data_command_edits_open_cell_nibble():
    machine = _boot_real_kim1()
    machine.ram.write(0xFA, 0x10)
    machine.ram.write(0xFB, 0x00)
    machine.ram.write(0xFF, 0x00)
    machine.ram.write(0x10, 0xAB)

    _press_kim1_keycode(machine, 0x05)  # key value 5

    assert machine.ram.peek(0x10) == 0xB5
    assert _point_value(machine) == 0x0010
    assert machine.ram.peek(0xFF) == 0x00


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_step_command_increments_open_cell():
    machine = _boot_real_kim1()
    machine.ram.write(0xFA, 0xFF)
    machine.ram.write(0xFB, 0x12)
    machine.ram.write(0xFF, 0x01)

    _press_kim1_keycode(machine, 0x12)  # STEP

    assert _point_value(machine) == 0x1300
    assert machine.ram.peek(0xFF) == 0x01


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_pc_command_copies_saved_program_counter_to_open_cell():
    machine = _boot_real_kim1()
    machine.ram.write(0xEF, 0x78)
    machine.ram.write(0xF0, 0x56)

    _press_kim1_keycode(machine, 0x14)  # PC

    assert _point_value(machine) == 0x5678
    assert machine.ram.peek(0xFF) == 0x01


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_run_command_executes_user_code_and_returns_to_monitor():
    machine = _boot_real_kim1()
    machine.ram.write(0x0200, 0xE8)  # INX
    machine.ram.write(0x0201, 0xE8)  # INX
    machine.ram.write(0x0202, 0x00)  # BRK
    machine.ram.write(0xFA, 0x00)
    machine.ram.write(0xFB, 0x02)
    machine.ram.write(0xFF, 0x01)
    machine.ram.write(0xEF, 0x00)
    machine.ram.write(0xF0, 0x02)
    machine.ram.write(0xF1, 0x20)
    machine.ram.write(0xF2, 0xFF)
    machine.ram.write(0xF3, 0x00)
    machine.ram.write(0xF4, 0x00)
    machine.ram.write(0xF5, 0x00)

    _press_kim1_keycode(machine, 0x13)  # RUN
    for _ in range(10):
        machine.run_frame()

    assert _point_value(machine) == 0x0204
    assert machine.ram.peek(0xEF) == 0x04
    assert machine.ram.peek(0xF0) == 0x02
    assert machine.ram.peek(0xF5) == 0x02
    assert machine.ram.peek(0xF1) == 0x30
    assert machine.ram.peek(0xF2) == 0xFF
    assert machine.cpu.PC in {0x1F5B, 0x1F5C}


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_tty_reset_calibrates_delay_registers_and_reaches_getch():
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    machine.riot.set_keyboard_mode(False)
    machine.riot.tty_bit_cycles = 500
    machine.riot.queue_tty_input(b"X")
    machine.cpu.reset()

    pc = _step_until_pc(machine, {0x1E5A}, 300_000)

    assert pc == 0x1E5A
    assert machine.bus.read8(0x17F2) != 0x00
    assert machine.bus.read8(0x17F3) == 0x00


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_tty_getch_detects_start_bit_and_enters_delay_path():
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    machine.riot.set_keyboard_mode(False)
    machine.riot.tty_bit_cycles = 500
    machine.riot.queue_tty_input(b"X")
    machine.cpu.reset()

    assert _step_until_pc(machine, {0x1E5A}, 300_000) == 0x1E5A

    machine.riot.queue_tty_input(b"G")
    pc = _step_until_pc(machine, {0x1ED4, 0x1EEB}, 2_000)

    assert pc in {0x1ED4, 0x1EEB}


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_tty_goexec_runs_user_program_after_calibration_byte():
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    machine.set_tty_mode(True)
    machine.riot.tty_bit_cycles = 2000
    machine.queue_tty_input(b"X", calibration=True)
    machine.cpu.reset()

    for addr, value in (
        (0x0200, 0xE8),
        (0x0201, 0xE8),
        (0x0202, 0x00),
        (0xFA, 0x00),
        (0xFB, 0x02),
        (0xEF, 0x00),
        (0xF0, 0x02),
        (0xF1, 0x20),
        (0xF2, 0xFF),
        (0xF3, 0x00),
        (0xF4, 0x00),
        (0xF5, 0x00),
    ):
        machine.ram.write(addr, value)

    assert _step_until_pc(machine, {0x1E5A}, 300_000) == 0x1E5A

    machine.queue_tty_input(b"G")
    ok = _step_until(
        machine,
        lambda mm: (mm.ram.peek(0xFA) | (mm.ram.peek(0xFB) << 8)) == 0x0204,
        2_000_000,
    )

    assert ok is True
    assert machine.ram.peek(0xEF) == 0x04
    assert machine.ram.peek(0xF0) == 0x02


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_tty_open_command_updates_open_cell_and_echoes_state():
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    machine.set_tty_mode(True)
    machine.riot.tty_bit_cycles = 2000
    machine.queue_tty_input(b"X", calibration=True)
    machine.cpu.reset()
    machine.ram.write(0xFA, 0x00)
    machine.ram.write(0xFB, 0x00)
    machine.ram.write(0x10, 0xAB)

    assert _step_until_pc(machine, {0x1E5A}, 300_000) == 0x1E5A

    machine.queue_tty_input(b"0010 ")
    _step_kim1(machine, 1_200_000)

    assert _point_value(machine) == 0x0010
    assert machine.drain_tty_output_ascii().endswith(b"0010 AB ")


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_tty_modify_command_updates_memory_and_advances_open_cell():
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    machine.set_tty_mode(True)
    machine.riot.tty_bit_cycles = 2000
    machine.queue_tty_input(b"X", calibration=True)
    machine.cpu.reset()
    machine.ram.write(0xFA, 0x00)
    machine.ram.write(0xFB, 0x00)
    machine.ram.write(0x10, 0xAB)

    assert _step_until_pc(machine, {0x1E5A}, 300_000) == 0x1E5A

    machine.queue_tty_input(b"0010 ")
    _step_kim1(machine, 1_200_000)
    assert _point_value(machine) == 0x0010
    machine.drain_tty_output_ascii()

    machine.queue_tty_input(b"CD.")
    _step_kim1(machine, 1_200_000)

    assert machine.ram.peek(0x10) == 0xCD
    assert _point_value(machine) == 0x0011
    assert machine.drain_tty_output_ascii().endswith(b"0011 00 ")


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_tty_dump_command_outputs_intel_style_record_stream():
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    machine.set_tty_mode(True)
    machine.riot.tty_bit_cycles = 2000
    machine.queue_tty_input(b"X", calibration=True)
    machine.cpu.reset()

    for index in range(0x18):
        machine.ram.write(0x0200 + index, (index * 3 + 1) & 0xFF)
    machine.ram.write(0xFA, 0x00)
    machine.ram.write(0xFB, 0x02)
    machine.bus.write8(0x17F7, 0x18)
    machine.bus.write8(0x17F8, 0x02)

    assert _step_until_pc(machine, {0x1E5A}, 300_000) == 0x1E5A

    machine.queue_tty_input(b"Q")
    _step_kim1(machine, 8_000_000)

    output = machine.drain_tty_output_ascii()

    assert output.startswith(b"\r\nKIM\r\n0200 01 ")
    assert b";1802000104070A0D101316191C1F2225282B2E3134373A3D404346036E\r\n" in output
    assert output.endswith(b";0000010001")


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_real_monitor_tty_load_command_restores_dumped_record_stream():
    source = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    source.set_tty_mode(True)
    source.riot.tty_bit_cycles = 2000
    source.queue_tty_input(b"X", calibration=True)
    source.cpu.reset()

    expected = bytes((index * 3 + 1) & 0xFF for index in range(0x18))
    for index, value in enumerate(expected):
        source.ram.write(0x0200 + index, value)
    source.ram.write(0xFA, 0x00)
    source.ram.write(0xFB, 0x02)
    source.bus.write8(0x17F7, 0x18)
    source.bus.write8(0x17F8, 0x02)

    assert _step_until_pc(source, {0x1E5A}, 300_000) == 0x1E5A

    source.queue_tty_input(b"Q")
    _step_kim1(source, 8_000_000)
    dump_output = source.drain_tty_output_ascii()
    record_stream = dump_output[dump_output.find(b";"):]

    target = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    target.set_tty_mode(True)
    target.riot.tty_bit_cycles = 2000
    target.queue_tty_input(b"X", calibration=True)
    target.cpu.reset()
    for index in range(0x18):
        target.ram.write(0x0200 + index, 0x00)

    assert _step_until_pc(target, {0x1E5A}, 300_000) == 0x1E5A

    target.queue_tty_input(b"L" + record_stream)
    _step_kim1(target, 12_000_000)

    restored = bytes(target.ram.read(0x0200 + index) for index in range(0x18))

    assert restored == expected
    assert target.drain_tty_output_ascii().endswith(b"0001 00 ")


@pytest.mark.skipif(
    not (KIM1_LOWER_ROM.exists() and KIM1_UPPER_ROM.exists()),
    reason=KIM1_REAL_ROM_REASON,
)
def test_kim1_monitor_outch_emits_tty_character():
    machine = KIM1(KIM1_LOWER_ROM.read_bytes(), KIM1_UPPER_ROM.read_bytes())
    for _ in range(5):
        machine.run_frame()
    machine.riot.tty_bit_cycles = 2000
    machine.drain_tty_output()
    machine.bus.write8(0x17F2, 0x36)
    machine.bus.write8(0x17F3, 0x02)

    for index, opcode in enumerate((0xA9, 0x41, 0x20, 0xA0, 0x1E, 0xEA)):
        machine.ram.write(0x0200 + index, opcode)

    machine.cpu.PC = 0x0200
    _step_until(machine, lambda mm: mm.cpu.PC == 0x0205, 500_000)

    assert machine.drain_tty_output() == b"A"
