from __future__ import annotations

"""Smoke coverage for the CLI parser and machine registry wiring."""

from pathlib import Path

from multiemu.cli import build_parser
from multiemu.machine_registry import get_default_rom_search_dirs, get_machine_spec, resolve_default_rom_path


def test_machine_registry_exposes_known_machine():
    spec = get_machine_spec("spectrum48k")
    assert spec.display_name == "ZX Spectrum 48K"
    assert spec.rom_filename == "spec48k.rom"


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


def test_resolve_default_rom_path_uses_first_matching_directory(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    cwd_rom = tmp_path / "spec48k.rom"
    home_rom_dir = fake_home / ".local/share/multiemu"
    home_rom_dir.mkdir(parents=True)
    cwd_rom.write_bytes(b"cwd")
    (home_rom_dir / "spec48k.rom").write_bytes(b"home")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(tmp_path)

    path = resolve_default_rom_path(get_machine_spec("spectrum48k"))

    assert path == cwd_rom


def test_parser_builds_run_command():
    parser = build_parser()
    args = parser.parse_args(
        ["run", "spectrum16k", "--rom", "custom.rom", "--scale", "3", "--frontend", "pygame"]
    )

    assert args.command == "run"
    assert args.machine == "spectrum16k"
    assert args.rom == "custom.rom"
    assert args.scale == 3
    assert args.frontend == "pygame"


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
