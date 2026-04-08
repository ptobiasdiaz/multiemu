from __future__ import annotations

"""Smoke coverage for the CLI parser and machine registry wiring."""

from pathlib import Path

from multiemu.cli import build_parser
from multiemu.machine_registry import (
    get_default_rom_search_dirs,
    get_machine_spec,
    instantiate_machine,
    parse_cli_rom_specs,
    resolve_machine_rom_paths,
)


def test_machine_registry_exposes_known_machine():
    spec = get_machine_spec("spectrum48k")
    assert spec.display_name == "ZX Spectrum 48K"


def test_machine_registry_exposes_spectrum128k():
    spec = get_machine_spec("spectrum128k")

    assert spec.machine_id == "spectrum128k"
    assert spec.display_name == "ZX Spectrum 128K"
    assert spec.rom_slots[0].slot_id == "main"
    assert "spec128k.rom" in spec.rom_slots[0].filenames
    assert "program.tap" in spec.rom_slots[1].filenames
    assert spec.rom_slots[2].slot_id == "snapshot"


def test_machine_registry_exposes_spectrumplus2():
    spec = get_machine_spec("spectrumplus2")

    assert spec.machine_id == "spectrumplus2"
    assert spec.display_name == "ZX Spectrum +2"
    assert spec.rom_slots[0].slot_id == "main"
    assert "plus2.rom" in spec.rom_slots[0].filenames
    assert "zx128k_2plus_es.rom" in spec.rom_slots[0].filenames
    assert "program.tap" in spec.rom_slots[1].filenames
    assert spec.rom_slots[2].slot_id == "snapshot"


def test_resolve_machine_rom_paths_prefers_default_main_rom_when_snapshot_is_explicit(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    snapshot = tmp_path / "bombjack.z80"
    main = tmp_path / "zx128k_2plus_es.rom"
    snapshot.write_bytes(b"z80")
    main.write_bytes(b"rom")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(tmp_path)

    roms = resolve_machine_rom_paths("spectrumplus2", roms={"snapshot": snapshot})

    assert roms["snapshot"] == snapshot
    assert roms["main"] == main


def test_machine_registry_exposes_gameboy():
    spec = get_machine_spec("gameboy")
    assert spec.display_name == "Nintendo Game Boy (early scaffold)"
    assert spec.rom_slots[0].slot_id == "main"


def test_machine_registry_exposes_gameboycolor():
    spec = get_machine_spec("gameboycolor")
    assert spec.display_name == "Nintendo Game Boy Color (early scaffold)"
    assert spec.rom_slots[0].slot_id == "main"
    assert "cart.gbc" in spec.rom_slots[0].filenames


def test_machine_registry_exposes_vic20ntsc():
    spec = get_machine_spec("vic20ntsc")
    assert spec.display_name == "Commodore VIC-20 NTSC (experimental)"
    assert spec.rom_slots[0].slot_id == "basic"


def test_machine_registry_exposes_cpc664():
    spec = get_machine_spec("cpc664")
    assert spec.display_name == "Amstrad CPC 664 (experimental)"
    assert spec.rom_slots[0].slot_id == "os"


def test_machine_registry_exposes_cpc6128():
    spec = get_machine_spec("cpc6128")
    assert spec.display_name == "Amstrad CPC 6128 (experimental)"
    assert spec.rom_slots[0].slot_id == "os"


def test_machine_registry_exposes_vic20pal():
    spec = get_machine_spec("vic20pal")
    assert spec.display_name == "Commodore VIC-20 PAL (experimental)"
    assert spec.rom_slots[0].slot_id == "basic"


def test_machine_registry_keeps_vic20_as_compatibility_alias():
    spec = get_machine_spec("vic20")
    assert spec.display_name == "Commodore VIC-20 (alias de vic20ntsc)"
    assert spec.rom_slots[0].slot_id == "basic"


def test_default_rom_search_dirs_follow_priority(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(tmp_path)

    search_dirs = get_default_rom_search_dirs()

    assert search_dirs[0] == tmp_path
    assert search_dirs[1] == fake_home / ".local/share/multiemu"
    assert search_dirs[2] == Path("/usr/local/share/multiemu/roms")
    assert search_dirs[3] == Path("/usr/share/multiemu")


def test_resolve_machine_rom_paths_uses_first_matching_directory(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    cwd_rom = tmp_path / "spec48k.rom"
    home_rom_dir = fake_home / ".local/share/multiemu"
    home_rom_dir.mkdir(parents=True)
    cwd_rom.write_bytes(b"cwd")
    (home_rom_dir / "spec48k.rom").write_bytes(b"home")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(tmp_path)

    roms = resolve_machine_rom_paths("spectrum48k")

    assert roms["main"] == cwd_rom


def test_resolve_machine_rom_paths_accepts_default_spectrum_tap(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    cwd_rom = tmp_path / "spec48k.rom"
    cwd_tape = tmp_path / "program.tap"
    cwd_rom.write_bytes(b"rom")
    cwd_tape.write_bytes(b"tap")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(tmp_path)

    roms = resolve_machine_rom_paths("spectrum48k")

    assert roms["main"] == cwd_rom
    assert roms["tape"] == cwd_tape


def test_parse_cli_rom_specs_accepts_short_form_for_single_slot_machine():
    roms = parse_cli_rom_specs("spectrum48k", ["custom.rom"])

    assert roms == {"main": Path("custom.rom")}


def test_parse_cli_rom_specs_accepts_short_form_for_gameboy():
    roms = parse_cli_rom_specs("gameboy", ["gameboy.gb"])

    assert roms == {"main": Path("gameboy.gb")}


def test_cli_run_accepts_custom_keymap_file():
    parser = build_parser()

    args = parser.parse_args(["run", "spectrum48k", "--rom", "spec48k.rom", "--keymap", "custom.json"])

    assert args.machine == "spectrum48k"
    assert args.keymap == "custom.json"


def test_cli_connect_accepts_custom_keymap_file():
    parser = build_parser()

    args = parser.parse_args(["connect", "--keymap", "custom.json"])

    assert args.keymap == "custom.json"


def test_parse_cli_rom_specs_requires_slot_names_for_multi_rom_machine():
    try:
        parse_cli_rom_specs("cpc464", ["OS_464.ROM"])
    except ValueError as exc:
        assert "varios slots" in str(exc)
    else:
        raise AssertionError("expected ValueError for multi-ROM machine without slot id")


def test_parse_cli_rom_specs_accepts_named_slots_for_multi_rom_machine():
    roms = parse_cli_rom_specs("cpc464", ["os=OS_464.ROM", "basic=BASIC_1.0.ROM", "expansion=cart.rom", "tape=demo.cdt"])

    assert roms == {
        "os": Path("OS_464.ROM"),
        "basic": Path("BASIC_1.0.ROM"),
        "expansion": Path("cart.rom"),
        "tape": Path("demo.cdt"),
    }


def test_parse_cli_rom_specs_accepts_named_slots_for_cpc664():
    roms = parse_cli_rom_specs("cpc664", ["os=OS_664.ROM", "basic=BASIC_1.1.ROM", "expansion=cart.rom", "disk=demo.dsk"])

    assert roms == {
        "os": Path("OS_664.ROM"),
        "basic": Path("BASIC_1.1.ROM"),
        "expansion": Path("cart.rom"),
        "disk": Path("demo.dsk"),
    }


def test_parse_cli_rom_specs_accepts_named_slots_for_cpc6128():
    roms = parse_cli_rom_specs("cpc6128", ["os=OS_6128.ROM", "basic=BASIC_1.1.ROM", "amsdos=AMSDOS.ROM", "expansion=cart.rom"])

    assert roms == {
        "os": Path("OS_6128.ROM"),
        "basic": Path("BASIC_1.1.ROM"),
        "amsdos": Path("AMSDOS.ROM"),
        "expansion": Path("cart.rom"),
    }


def test_instantiate_cpc664_accepts_combined_32k_system_rom(tmp_path):
    rom_path = tmp_path / "cpc664.rom"
    rom_path.write_bytes(bytes([0xAA]) * 0x4000 + bytes([0xCC]) * 0x4000)

    machine = instantiate_machine("cpc664", roms={"os": rom_path})

    assert machine.peek(0x0000) == 0xAA
    assert machine.upper_rom_banks[0].peek(0) == 0xCC


def test_instantiate_cpc664_rejects_combined_os_plus_explicit_basic(tmp_path):
    os_path = tmp_path / "cpc664.rom"
    basic_path = tmp_path / "basic.rom"
    os_path.write_bytes(bytes([0xAA]) * 0x8000)
    basic_path.write_bytes(bytes([0xCC]) * 0x4000)

    try:
        instantiate_machine("cpc664", roms={"os": os_path, "basic": basic_path})
    except ValueError as exc:
        assert "32K" in str(exc)
    else:
        raise AssertionError("expected ValueError for combined 32K CPC ROM plus explicit basic")


def test_parse_cli_rom_specs_accepts_vic20ntsc_cart_slot():
    roms = parse_cli_rom_specs("vic20ntsc", ["cart=Videomania.prg"])

    assert roms == {"cart": Path("Videomania.prg")}


def test_parse_cli_rom_specs_accepts_vic20pal_cart_slot():
    roms = parse_cli_rom_specs("vic20pal", ["cart=Videomania.prg"])

    assert roms == {"cart": Path("Videomania.prg")}


def test_resolve_machine_rom_paths_searches_missing_slots_next_to_explicit_rom(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    (rom_dir / "OS_464.ROM").write_bytes(b"os")
    (rom_dir / "BASIC_1.0.ROM").write_bytes(b"basic")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(tmp_path)

    roms = resolve_machine_rom_paths("cpc464", roms={"os": rom_dir / "OS_464.ROM"})

    assert roms["os"] == rom_dir / "OS_464.ROM"
    assert roms["basic"] == rom_dir / "BASIC_1.0.ROM"


def test_parser_builds_run_command():
    parser = build_parser()
    args = parser.parse_args(
        [
            "run",
            "spectrum16k",
            "--rom",
            "custom.rom",
            "--scale",
            "3",
            "--frontend",
            "pygame",
            "--display-profile",
            "full-border",
        ]
    )

    assert args.command == "run"
    assert args.machine == "spectrum16k"
    assert args.rom == ["custom.rom"]
    assert args.scale == 3
    assert args.frontend == "pygame"
    assert args.display_profile == "full-border"


def test_parser_builds_connect_command_with_defaults():
    parser = build_parser()
    args = parser.parse_args(["connect"])

    assert args.command == "connect"
    assert args.transport == "tcp"
    assert args.frontend == "pygame"
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.joystick_player == 1


def test_parser_builds_connect_command_with_joystick_player_override():
    parser = build_parser()
    args = parser.parse_args(["connect", "--joystick-player", "2"])

    assert args.command == "connect"
    assert args.joystick_player == 2


def test_parser_builds_debug_command():
    parser = build_parser()
    args = parser.parse_args(["debug", "vic20ntsc", "--host", "0.0.0.0", "--port", "9001"])

    assert args.command == "debug"
    assert args.machine == "vic20ntsc"
    assert args.host == "0.0.0.0"
    assert args.port == 9001


def test_parser_builds_client_alias_command():
    parser = build_parser()
    args = parser.parse_args(
        ["client", "--host", "192.168.1.10", "--port", "9000", "--transport", "tcp", "--frontend", "pygame"]
    )

    assert args.command == "client"
    assert args.host == "192.168.1.10"
    assert args.port == 9000
    assert args.transport == "tcp"
    assert args.frontend == "pygame"


def test_parser_builds_list_display_profiles_command():
    parser = build_parser()
    args = parser.parse_args(["list-display-profiles"])

    assert args.command == "list-display-profiles"


def test_instantiate_machine_accepts_display_profile(tmp_path):
    rom_path = tmp_path / "spectrum48k_test.rom"
    rom_path.write_bytes(b"\x00" * 0x4000)

    machine = instantiate_machine(
        "spectrum48k",
        roms={"main": rom_path},
        display_profile="full-border",
    )

    assert machine.display_profile_name == "full-border"


def test_instantiate_gameboy_machine(tmp_path):
    rom = bytearray(0x8000)
    rom[0x0134:0x013A] = b"SMTEST"
    rom[0x0147] = 0x00
    rom_path = tmp_path / "gameboy.gb"
    rom_path.write_bytes(rom)

    machine = instantiate_machine("gameboy", roms={"main": rom_path})

    assert machine.machine_id == "gameboy"
    assert machine.display_name == "Nintendo Game Boy (early scaffold)"
    assert machine.frame_width == 160


def test_instantiate_gameboycolor_machine(tmp_path):
    rom = bytearray(0x8000)
    rom[0x0134:0x013A] = b"GBCROM"
    rom[0x0143] = 0x80
    rom_path = tmp_path / "gameboycolor.gbc"
    rom_path.write_bytes(rom)

    machine = instantiate_machine("gameboycolor", roms={"main": rom_path})

    assert machine.machine_id == "gameboycolor"
    assert machine.display_name == "Nintendo Game Boy Color (early scaffold)"
    assert machine.frame_width == 160
    assert machine.bus.read8(0xFF4D) == 0x7E
    assert machine.bus.read8(0xFF4F) == 0xFE
    assert machine.bus.read8(0xFF70) == 0xF9


def test_instantiate_vic20_machine_accepts_4k_cartridge_prg(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    cart = tmp_path / "videomania.prg"
    basic.write_bytes(b"\xEA" * 0x2000)
    kernal_data = bytearray(b"\xEA" * 0x2000)
    kernal_data[-4] = 0x00
    kernal_data[-3] = 0xE0
    kernal.write_bytes(kernal_data)
    char.write_bytes(b"\x00" * 0x1000)
    cart.write_bytes(b"\x00\xA0" + (b"\x5A" * 0x1000))

    machine = instantiate_machine(
        "vic20ntsc",
        roms={"basic": basic, "kernal": kernal, "char": char, "cart": cart},
    )

    assert machine.bus.read8(0xA000) == 0x5A
    assert machine.bus.read8(0xAFFF) == 0x5A
    assert machine.bus.read8(0xB000) == 0xFF


def test_instantiate_vic20_machine_accepts_8k_cartridge_prg_in_blk3(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    cart = tmp_path / "ae-6000.prg"
    basic.write_bytes(b"\xEA" * 0x2000)
    kernal_data = bytearray(b"\xEA" * 0x2000)
    kernal_data[-4] = 0x00
    kernal_data[-3] = 0xE0
    kernal.write_bytes(kernal_data)
    char.write_bytes(b"\x00" * 0x1000)
    cart.write_bytes(b"\x00\x60" + (b"\x33" * 0x2000))

    machine = instantiate_machine(
        "vic20ntsc",
        roms={"basic": basic, "kernal": kernal, "char": char, "cart": cart},
    )

    assert machine.bus.read8(0x6000) == 0x33
    assert machine.bus.read8(0x7FFF) == 0x33


def test_instantiate_vic20_machine_rejects_cart_slot_conflict(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    cart = tmp_path / "ae-a000.prg"
    blk5 = tmp_path / "blk5.bin"
    basic.write_bytes(b"\xEA" * 0x2000)
    kernal_data = bytearray(b"\xEA" * 0x2000)
    kernal_data[-4] = 0x00
    kernal_data[-3] = 0xE0
    kernal.write_bytes(kernal_data)
    char.write_bytes(b"\x00" * 0x1000)
    cart.write_bytes(b"\x00\xA0" + (b"\x77" * 0x2000))
    blk5.write_bytes(b"\x55" * 0x2000)

    try:
        instantiate_machine(
            "vic20",
            roms={"basic": basic, "kernal": kernal, "char": char, "cart": cart, "blk5": blk5},
        )
    except ValueError as exc:
        assert "ya se proporcionó explícitamente" in str(exc)
    else:
        raise AssertionError("expected ValueError for cart/blk5 conflict")


def test_instantiate_vic20_machine_autoloads_companion_16k_cartridge_half(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    cart_lo = tmp_path / "AE-6000.prg"
    cart_hi = tmp_path / "AE-a000.prg"
    basic.write_bytes(b"\xEA" * 0x2000)
    kernal_data = bytearray(b"\xEA" * 0x2000)
    kernal_data[-4] = 0x00
    kernal_data[-3] = 0xE0
    kernal.write_bytes(kernal_data)
    char.write_bytes(b"\x00" * 0x1000)
    cart_lo.write_bytes(b"\x00\x60" + (b"\x33" * 0x2000))
    cart_hi.write_bytes(b"\x00\xA0" + (b"\x55" * 0x2000))

    machine = instantiate_machine(
        "vic20",
        roms={"basic": basic, "kernal": kernal, "char": char, "cart": cart_lo},
    )

    assert machine.bus.read8(0x6000) == 0x33
    assert machine.bus.read8(0xA000) == 0x55


def test_instantiate_vic20_machine_accepts_raw_blk5_autostart_rom_in_cart_slot(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    cart = tmp_path / "diag-vic20.bin"
    basic.write_bytes(b"\xEA" * 0x2000)
    kernal_data = bytearray(b"\xEA" * 0x2000)
    kernal_data[-4] = 0x00
    kernal_data[-3] = 0xE0
    kernal.write_bytes(kernal_data)
    char.write_bytes(b"\x00" * 0x1000)
    cart.write_bytes(
        bytes(
            [
                0x19,
                0xA0,
                0x19,
                0xA0,
                0x41,
                0x30,
                0xC3,
                0xC2,
                0xCD,
            ]
        )
        + (b"\x5A" * (0x1000 - 9))
    )

    machine = instantiate_machine(
        "vic20ntsc",
        roms={"basic": basic, "kernal": kernal, "char": char, "cart": cart},
    )

    assert machine.bus.read8(0xA000) == 0x19
    assert machine.bus.read8(0xA004) == 0x41
    assert machine.bus.read8(0xAFFF) == 0x5A


def test_instantiate_vic20_machine_accepts_raw_16k_20_cartridge_image(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    cart = tmp_path / "Donkey Kong (Japan, USA).20"
    basic.write_bytes(b"\xEA" * 0x2000)
    kernal_data = bytearray(b"\xEA" * 0x2000)
    kernal_data[-4] = 0x00
    kernal_data[-3] = 0xE0
    kernal.write_bytes(kernal_data)
    char.write_bytes(b"\x00" * 0x1000)
    cart.write_bytes((b"\x11" * 0x2000) + (b"\x22" * 0x2000))

    machine = instantiate_machine(
        "vic20ntsc",
        roms={"basic": basic, "kernal": kernal, "char": char, "cart": cart},
    )

    assert machine.bus.read8(0x2000) == 0x11
    assert machine.bus.read8(0x3FFF) == 0x11
    assert machine.bus.read8(0x4000) == 0x22
    assert machine.bus.read8(0x5FFF) == 0x22


def test_instantiate_vic20_diag_cart_enables_io2_and_io3_ram(tmp_path):
    basic = tmp_path / "basic.bin"
    kernal = tmp_path / "kernal.bin"
    char = tmp_path / "char.bin"
    cart = tmp_path / "diag-vic20.bin"
    basic.write_bytes(b"\xEA" * 0x2000)
    kernal_data = bytearray(b"\xEA" * 0x2000)
    kernal_data[-4] = 0x00
    kernal_data[-3] = 0xE0
    kernal.write_bytes(kernal_data)
    char.write_bytes(b"\x00" * 0x1000)
    cart.write_bytes(
        bytes([0x19, 0xA0, 0x19, 0xA0, 0x41, 0x30, 0xC3, 0xC2, 0xCD]) + (b"\x00" * (0x1000 - 9))
    )

    machine = instantiate_machine(
        "vic20ntsc",
        roms={"basic": basic, "kernal": kernal, "char": char, "cart": cart},
    )

    machine.bus.write8(0x9800, 0x12)
    machine.bus.write8(0x9C00, 0x34)

    assert machine.bus.read8(0x9800) == 0x12
    assert machine.bus.read8(0x9C00) == 0x34
