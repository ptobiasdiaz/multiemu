from __future__ import annotations

import hashlib
import json

from frontend.input_events import InputEvent, JOYSTICK_FIRE, JOYSTICK_UP
import multiemu.romdb as romdb
from devices.msx_cas import MSXCassetteTape
from machines.z80 import MSX1


def _rom(fill: int) -> bytes:
    return bytes([fill & 0xFF]) * 0x4000


def _cas(*records: bytes) -> bytes:
    return b"".join(MSXCassetteTape.MAGIC + record for record in records)


def _cart_with_code(*code_fragments: bytes, banks: int = 8) -> bytes:
    data = bytearray(b"".join(bytes([bank]) * 0x2000 for bank in range(banks)))
    offset = 0x0100
    for fragment in code_fragments:
        data[offset:offset + len(fragment)] = fragment
        offset += len(fragment) + 0x10
    return bytes(data)


def _call_bios(machine: MSX1, pc: int, *, sp: int = 0xF000) -> None:
    machine.poke(sp, 0x34)
    machine.poke((sp + 1) & 0xFFFF, 0x12)
    machine.cpu.write_state({"PC": pc, "SP": sp, "F": 0xAA, "A": 0x00})


def test_msx_maps_bios_and_basic_pages():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))

    assert machine.peek(0x0000) == 0xC3
    assert machine.peek(0x4000) == 0x55
    assert machine.peek(0x8000) == 0x00
    assert machine.peek(0xC000) == 0x00


def test_msx_uses_short_frontend_tap_pulses():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))

    assert machine.input_tap_hold_frames == 1
    assert machine.input_quick_tap_max_frames == 1


def test_msx_cas_parser_splits_magic_records_into_stream():
    tape = MSXCassetteTape.from_bytes(_cas(b"HEADER", b"\x01\x02\x03"))

    assert tape.records == [b"HEADER", b"\x01\x02\x03"]
    assert tape.stream == b"HEADER\x01\x02\x03"


def test_msx_cas_tapion_opens_next_record_instead_of_concatenating():
    tape = MSXCassetteTape.from_bytes(_cas(b"AB", b"CD"))

    assert tape.open_for_read() is True
    assert tape.read_byte() == ord("A")
    assert tape.open_for_read() is True
    assert tape.read_byte() == ord("C")


def test_msx_bios_cassette_hooks_read_tape_bytes():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), tape_data=_cas(b"\xD0AB", b"\x00\xA0"))

    _call_bios(machine, machine.BIOS_TAPION)
    assert machine._step_cpu() == 11
    snap = machine.cpu.snapshot()
    assert snap["PC"] == 0x1234
    assert snap["SP"] == 0xF002
    assert snap["F"] & 0x01 == 0

    _call_bios(machine, machine.BIOS_TAPIN)
    machine._step_cpu()
    snap = machine.cpu.snapshot()
    assert snap["A"] == 0xD0
    assert snap["F"] & 0x01 == 0
    assert machine.cassette_status["active"] is True


def test_msx_bios_tapin_sets_carry_at_end_of_tape():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), tape_data=_cas(b"\x42"))

    _call_bios(machine, machine.BIOS_TAPIN)
    machine._step_cpu()
    _call_bios(machine, machine.BIOS_TAPIN)
    machine._step_cpu()

    snap = machine.cpu.snapshot()
    assert snap["F"] & 0x01 == 0x01


def test_msx_cart1_auto_maps_pages_1_and_2():
    cart = bytes([0x11]) * 0x4000 + bytes([0x22]) * 0x4000
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    assert machine.slot_register == machine.DEFAULT_SLOT_REGISTER_CART1
    assert machine._port_read(0xA8) == machine.DEFAULT_SLOT_REGISTER_CART1
    assert machine.peek(0x4000) == 0x11
    assert machine.peek(0x8000) == 0x22
    assert machine.peek(0x0000) == 0xC3


def test_msx_cart2_auto_maps_pages_1_and_2_when_no_cart1():
    cart = bytes([0x33]) * 0x4000 + bytes([0x44]) * 0x4000
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart2_data=cart)

    assert machine.slot_register == machine.DEFAULT_SLOT_REGISTER_CART2
    assert machine.peek(0x4000) == 0x33
    assert machine.peek(0x8000) == 0x44
    assert machine.peek(0x0000) == 0xC3


def test_msx_subslot_register_can_map_cart1_into_primary_slot0_page2():
    cart = bytes([0x11]) * 0x4000 + bytes([0x22]) * 0x4000
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    machine._port_write(0xA8, 0x03)
    machine.poke(0xFFFF, 0x10)

    assert machine.peek(0x8000) == 0x22


def test_msx_slot2_behaves_as_ram_when_cart2_is_absent():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))

    machine._port_write(0xA8, 0x8A)
    machine.poke(0x4000, 0xA5)
    machine.poke(0xC000, 0x5A)

    assert machine.peek(0x4000) == 0xA5
    assert machine.peek(0xC000) == 0x5A


def test_msx_megarom_cart1_switches_8k_segments_on_write():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    assert machine.cart1_mapper == machine.CART_MAPPER_UNKNOWN
    assert machine.peek(0x4000) == 0x00
    assert machine.peek(0x6000) == 0x01
    assert machine.peek(0x8000) == 0x02
    assert machine.peek(0xA000) == 0x03

    machine.poke(0x8000, 0x07)

    assert machine.cart1_mapper == machine.CART_MAPPER_KONAMI
    assert machine.peek(0x4000) == 0x00
    assert machine.peek(0x6000) == 0x01
    assert machine.peek(0x8000) == 0x07
    assert machine.peek(0xA000) == 0x03
    assert machine.cart1_bank_registers[2] == 0x07

    machine.poke(0xA000, 0x06)

    assert machine.peek(0xA000) == 0x06
    assert machine.cart1_bank_registers[3] == 0x06


def test_msx_ascii8_mapper_is_detected_from_6800_write():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    machine.poke(0x6800, 0x07)

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII8
    assert machine.peek(0x6000) == 0x07
    assert machine.cart1_bank_registers[1] == 0x07


def test_msx_ascii16_mapper_is_detected_from_7000_write():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    machine.poke(0x7000, 0x01)

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII16
    assert machine.peek(0x8000) == 0x02
    assert machine.peek(0xA000) == 0x03
    assert machine.cart1_bank_registers[1] == 0x01


def test_msx_ascii16_mapper_can_select_banks_past_initial_cart_window():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(12))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    machine.poke(0x6000, 0x02)
    machine.poke(0x7000, 0x05)

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII16
    assert machine.peek(0x4000) == 0x04
    assert machine.peek(0x6000) == 0x05
    assert machine.peek(0x8000) == 0x0A
    assert machine.peek(0xA000) == 0x0B


def test_msx_mapper_guess_detects_konami_before_runtime_writes():
    cart = _cart_with_code(
        b"\x32\x00\x80",
        b"\x32\x00\xA0",
    )
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    assert machine.cart1_mapper == machine.CART_MAPPER_KONAMI


def test_msx_mapper_guess_detects_konami_scc_before_runtime_writes():
    cart = _cart_with_code(
        b"\x32\x00\x50",
        b"\x32\x00\x90",
        b"\x32\x00\xB0",
    )
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    assert machine.cart1_mapper == machine.CART_MAPPER_KONAMI_SCC


def test_msx_mapper_guess_detects_ascii8_before_runtime_writes():
    cart = _cart_with_code(
        b"\x32\x00\x68",
        b"\x32\x00\x70",
        b"\x32\x00\x78",
    )
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII8


def test_msx_mapper_guess_detects_ascii16_before_runtime_writes():
    cart = _cart_with_code(
        b"\x32\x00\x60",
        b"\x32\x00\x70",
        b"\x32\xFF\x77",
    )
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII16


def test_msx_mapper_guess_keeps_unknown_when_no_mapper_writes_are_seen():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    assert machine.cart1_mapper == machine.CART_MAPPER_UNKNOWN


def test_msx_mapper_db_selects_mapper_by_sha1(tmp_path, monkeypatch):
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    keymaps_dir = tmp_path / "keymaps"
    romdb_dir = tmp_path / "romdb"
    keymaps_dir.mkdir()
    romdb_dir.mkdir()
    (romdb_dir / "msx_mappers.json").write_text(
        json.dumps({f"sha1:{hashlib.sha1(cart).hexdigest()}": "generic16"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(romdb, "KEYMAP_SEARCH_DIRS", (keymaps_dir,))
    romdb.load_msx_mapper_db.cache_clear()

    try:
        machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    finally:
        romdb.load_msx_mapper_db.cache_clear()

    assert machine.cart1_mapper == machine.CART_MAPPER_GENERIC16
    assert machine.peek(0x4000) == 0x00
    assert machine.peek(0x6000) == 0x01
    assert machine.peek(0x8000) == 0x02
    assert machine.peek(0xA000) == 0x03


def test_msx_mapper_db_accepts_openmsx_style_alias(tmp_path, monkeypatch):
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    keymaps_dir = tmp_path / "keymaps"
    romdb_dir = tmp_path / "romdb"
    keymaps_dir.mkdir()
    romdb_dir.mkdir()
    (romdb_dir / "msx_mappers.json").write_text(
        json.dumps({f"sha1:{hashlib.sha1(cart).hexdigest()}": "KonamiSCC"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(romdb, "KEYMAP_SEARCH_DIRS", (keymaps_dir,))
    romdb.load_msx_mapper_db.cache_clear()

    try:
        machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    finally:
        romdb.load_msx_mapper_db.cache_clear()

    assert machine.cart1_mapper == machine.CART_MAPPER_KONAMI_SCC


def test_msx_mapper_db_wins_over_mapper_guess(tmp_path, monkeypatch):
    cart = _cart_with_code(
        b"\x32\x00\x90",
        b"\x32\x00\xB0",
    )
    keymaps_dir = tmp_path / "keymaps"
    romdb_dir = tmp_path / "romdb"
    keymaps_dir.mkdir()
    romdb_dir.mkdir()
    (romdb_dir / "msx_mappers.json").write_text(
        json.dumps({f"sha1:{hashlib.sha1(cart).hexdigest()}": "ascii16"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(romdb, "KEYMAP_SEARCH_DIRS", (keymaps_dir,))
    romdb.load_msx_mapper_db.cache_clear()

    try:
        machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    finally:
        romdb.load_msx_mapper_db.cache_clear()

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII16


def test_msx_mapper_override_wins_over_mapper_guess():
    cart = _cart_with_code(
        b"\x32\x00\x90",
        b"\x32\x00\xB0",
    )
    machine = MSX1(
        _rom(0xC3),
        basic_data=_rom(0x55),
        cart1_data=cart,
        cart1_mapper="ascii8",
    )

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII8


def test_msx_generic16_mapper_switches_16k_banks():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_GENERIC16
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x4000, 0x01)

    assert machine.cart1_mapper == machine.CART_MAPPER_GENERIC16
    assert machine.peek(0x4000) == 0x02
    assert machine.peek(0x6000) == 0x03
    assert machine.peek(0x8000) == 0x02
    assert machine.peek(0xA000) == 0x03
    assert machine.cart1_bank_registers[0] == 0x01


def test_msx_generic8_mapper_switches_8k_banks():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_GENERIC8
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x4000, 0x04)
    machine.poke(0x6000, 0x05)
    machine.poke(0x8000, 0x06)
    machine.poke(0xA000, 0x07)

    assert machine.peek(0x4000) == 0x04
    assert machine.peek(0x6000) == 0x05
    assert machine.peek(0x8000) == 0x06
    assert machine.peek(0xA000) == 0x07


def test_msx_zemina8_mapper_switches_8k_banks():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_ZEMINA8
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x4000, 0x04)
    machine.poke(0x6000, 0x05)
    machine.poke(0x8000, 0x06)
    machine.poke(0xA000, 0x07)

    assert machine.peek(0x4000) == 0x04
    assert machine.peek(0x6000) == 0x05
    assert machine.peek(0x8000) == 0x06
    assert machine.peek(0xA000) == 0x07


def test_msx_zemina16_mapper_switches_16k_banks():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_ZEMINA16
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x8000, 0x03)

    assert machine.peek(0x4000) == 0x00
    assert machine.peek(0x6000) == 0x01
    assert machine.peek(0x8000) == 0x06
    assert machine.peek(0xA000) == 0x07
    assert machine.cart1_bank_registers[1] == 0x03


def test_msx_holy_quran_mapper_uses_5000_register_window():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_HOLY_QURAN
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x5000, 0x01)
    machine.poke(0x5400, 0x02)
    machine.poke(0x5800, 0x03)
    machine.poke(0x5C00, 0x04)

    assert machine.peek(0x4000) == 0x01
    assert machine.peek(0x6000) == 0x02
    assert machine.peek(0x8000) == 0x03
    assert machine.peek(0xA000) == 0x04


def test_msx_harry_fox_mapper_uses_ascii16_registers():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_HARRY_FOX
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x6000, 0x01)
    machine.poke(0x7000, 0x01)

    assert machine.peek(0x4000) == 0x04
    assert machine.peek(0x6000) == 0x05
    assert machine.peek(0x8000) == 0x06
    assert machine.peek(0xA000) == 0x07


def test_msx_cross_blaim_mapper_keeps_first_16k_fixed():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_CROSS_BLAIM
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x8000, 0x03)

    assert machine.peek(0x4000) == 0x00
    assert machine.peek(0x6000) == 0x01
    assert machine.peek(0x8000) == 0x06
    assert machine.peek(0xA000) == 0x07
    assert machine.cart1_bank_registers[1] == 0x03


def test_msx_rtype_mapper_keeps_first_16k_fixed_to_bank_17():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(48))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)
    machine.cart1_mapper = machine.CART_MAPPER_RTYPE
    machine.cart1_bank_registers = machine._default_cart_bank_registers(machine.cart1_mapper)

    machine.poke(0x7000, 0x12)

    assert machine.peek(0x4000) == 0x2E
    assert machine.peek(0x6000) == 0x2F
    assert machine.peek(0x8000) == 0x24
    assert machine.peek(0xA000) == 0x25
    assert machine.cart1_bank_registers[1] == 0x12


def test_msx_low_cart_write_does_not_prevent_later_ascii16_detection():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    machine.poke(0x4103, 0x00)
    machine.poke(0x5000, 0x00)
    machine.poke(0xBC02, 0x05)
    machine.poke(0x6000, 0x01)

    assert machine.cart1_mapper == machine.CART_MAPPER_ASCII16
    assert machine.peek(0x4000) == 0x02
    assert machine.peek(0x6000) == 0x03


def test_msx_konami_scc_mapper_is_detected_from_9000_write():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart)

    machine.poke(0x9000, 0x06)
    machine.poke(0x5000, 0x04)
    machine.poke(0x7000, 0x05)
    machine.poke(0xB000, 0x07)

    assert machine.cart1_mapper == machine.CART_MAPPER_KONAMI_SCC
    assert machine.peek(0x4000) == 0x04
    assert machine.peek(0x6000) == 0x05
    assert machine.peek(0x8000) == 0x06
    assert machine.peek(0xA000) == 0x07


def test_msx_konami_scc_mapper_mirrors_high_pages_into_outer_pages():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart, cart1_mapper="konami_scc")

    machine._port_write(0xA8, 0x55)

    assert machine.peek(0x0000) == 0x02
    assert machine.peek(0x2000) == 0x03
    assert machine.peek(0x4000) == 0x00
    assert machine.peek(0x6000) == 0x01
    assert machine.peek(0x8000) == 0x02
    assert machine.peek(0xA000) == 0x03
    assert machine.peek(0xC000) == 0x00
    assert machine.peek(0xE000) == 0x01


def test_msx_konami_mapper_mirrors_low_pages_into_outer_pages():
    cart = b"".join(bytes([bank]) * 0x2000 for bank in range(8))
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), cart1_data=cart, cart1_mapper="konami")

    machine._port_write(0xA8, 0x55)

    assert machine.peek(0x0000) == 0x00
    assert machine.peek(0x2000) == 0x01
    assert machine.peek(0xC000) == 0x02
    assert machine.peek(0xE000) == 0x03


def test_msx_slot_register_can_map_page0_to_ram():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))

    machine._port_write(0xA8, 0xF3)
    machine.poke(0x0001, 0xAA)

    assert machine.peek(0x0001) == 0xAA
    assert machine._port_read(0xA8) == 0xF3


def test_msx_keyboard_row_is_read_through_ppi_port_b():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))

    machine.handle_input_event(InputEvent("key_matrix", 8, 0, True))
    machine._port_write(0xAA, 0x08)

    assert machine._port_read(0xA9) & 0x01 == 0


def test_msx_psg_port_a_reads_joystick_bits():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))

    machine._port_write(0xA0, 14)
    assert machine._port_read(0xA2) == 0xFF
    machine.psg.registers[7] &= ~0x40
    assert machine._port_read(0xA2) == 0xFF

    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_UP, True))
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_FIRE, True))

    value = machine._port_read(0xA2)

    assert value & 0x01 == 0
    assert value & 0x10 == 0
    assert value & 0x40 == 0x40
    assert value & 0x80 == 0x80


def test_msx_psg_uses_internal_oversampled_audio_rate():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), audio_sample_rate=44_100)

    assert machine.psg.sample_rate == 44_100 * machine.PSG_OVERSAMPLE


def test_msx_psg_write_flushes_audio_before_midframe_register_change():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55), audio_sample_rate=44_100)
    machine._port_write(0xA0, 0)
    machine._port_write(0xA1, 2)
    machine._port_write(0xA0, 1)
    machine._port_write(0xA1, 0)
    machine._port_write(0xA0, 8)
    machine._port_write(0xA1, 0)

    machine._begin_frame()
    midpoint = machine.TSTATES_PER_FRAME // 2
    machine.frame_tstates = midpoint
    machine._port_write(0xA0, 8)
    machine._port_write(0xA1, 0x0F)
    machine._finish_frame()

    midpoint_sample = len(machine.audio_samples) // 2
    assert len(machine.audio_samples) == machine._current_frame_sample_target
    assert any(sample == 0 for sample in machine.audio_samples[:midpoint_sample])
    assert all(sample == 0 for sample in machine.audio_samples[:midpoint_sample - 4])
    assert any(sample != 0 for sample in machine.audio_samples[midpoint_sample + 4:])


def test_msx_state_roundtrip_restores_slot_ram_and_inputs():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))
    machine._port_write(0xA8, 0x03)
    machine.poke(0xFFFF, 0xA5)
    machine._port_write(0xA8, 0xF3)
    machine.poke(0x0002, 0x5A)
    machine.handle_input_event(InputEvent("key_matrix", 8, 0, True))
    machine.handle_input_event(InputEvent("joystick", 0, JOYSTICK_UP, True))

    state = machine.read_state()

    other = MSX1(_rom(0xC3), basic_data=_rom(0x55))
    other.write_state(state)

    assert other.slot_register == 0xF3
    assert other.subslot_register == 0xA5
    assert other.peek(0x0002) == 0x5A
    assert other.keyboard_matrix[8] & 0x01 == 0
    assert other.joystick_ports[0] & 0x01 == 0


def test_msx_ffff_is_ram_when_page3_uses_ram_slot():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))

    machine._port_write(0xA8, 0xF0)
    machine.poke(0xFFFF, 0xA5)

    assert machine.subslot_register == machine.DEFAULT_SUBSLOT_REGISTER
    assert machine.peek(0xFFFF) == 0xA5


def test_msx_delivers_vdp_interrupt_when_enabled():
    machine = MSX1(_rom(0xC3), basic_data=_rom(0x55))
    machine.vdp.registers[1] = 0x20
    machine.cpu.write_state({"iff1": True, "iff2": True, "im": 1, "SP": 0xFFFE})
    machine.poke(0x0038, 0xC9)  # RET

    machine.vdp.begin_frame()
    machine._run_devices_until(machine.vdp.VBLANK_TSTATE + 1)

    assert machine.cpu.snapshot()["PC"] == 0x0038
