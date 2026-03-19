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
    assert spec.rom_slots[0].slot_id == "main"
    assert spec.rom_slots[0].filenames == ("spec48k.rom",)


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


def test_parse_cli_rom_specs_accepts_short_form_for_single_slot_machine():
    roms = parse_cli_rom_specs("spectrum48k", ["custom.rom"])

    assert roms == {"main": Path("custom.rom")}


def test_parse_cli_rom_specs_requires_slot_names_for_multi_rom_machine():
    try:
        parse_cli_rom_specs("cpc464", ["OS_464.ROM"])
    except ValueError as exc:
        assert "varios slots" in str(exc)
    else:
        raise AssertionError("expected ValueError for multi-ROM machine without slot id")


def test_parse_cli_rom_specs_accepts_named_slots_for_multi_rom_machine():
    roms = parse_cli_rom_specs("cpc464", ["os=OS_464.ROM", "basic=BASIC_1.0.ROM"])

    assert roms == {
        "os": Path("OS_464.ROM"),
        "basic": Path("BASIC_1.0.ROM"),
    }


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


def test_instantiate_machine_accepts_display_profile():
    machine = instantiate_machine(
        "spectrum48k",
        roms={"main": "48.rom"},
        display_profile="full-border",
    )

    assert machine.display_profile_name == "full-border"
