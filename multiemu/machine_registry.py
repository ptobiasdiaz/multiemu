from __future__ import annotations

"""Central machine registry used by the CLI and future orchestration layers.

The goal is to keep machine discovery and instantiation out of the argument
parser so new frontends or automation entry points can reuse the same factory.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable

from machines.z80 import Spectrum16K, Spectrum48K


@dataclass(frozen=True, slots=True)
class MachineSpec:
    """Declarative description for a machine entry exposed to the user."""

    machine_id: str
    display_name: str
    factory: Callable[[bytes | None], object]
    rom_filename: str | None = None


MACHINE_SPECS: dict[str, MachineSpec] = {
    "spectrum16k": MachineSpec(
        machine_id="spectrum16k",
        display_name="ZX Spectrum 16K",
        factory=Spectrum16K,
        rom_filename="spec16k.rom",
    ),
    "spectrum48k": MachineSpec(
        machine_id="spectrum48k",
        display_name="ZX Spectrum 48K",
        factory=Spectrum48K,
        rom_filename="spec48k.rom",
    ),
}


def get_default_rom_search_dirs() -> list[Path]:
    """Return ROM lookup directories ordered by user-facing priority.

    Search is intentionally outside the repository tree so installed builds and
    local development use the same lookup rules.
    """

    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
    return [
        Path.cwd(),
        home / ".local/share/multiemu",
        Path("/usr/local/share/multiemu/roms"),
        Path("/usr/share/multiemu"),
    ]


def list_machine_specs() -> list[MachineSpec]:
    """Return supported machines in a stable order for help and listings."""

    return [MACHINE_SPECS[key] for key in sorted(MACHINE_SPECS)]


def get_machine_spec(machine_id: str) -> MachineSpec:
    """Resolve a machine id or raise a user-facing error with valid choices."""

    try:
        return MACHINE_SPECS[machine_id]
    except KeyError as exc:
        supported = ", ".join(sorted(MACHINE_SPECS))
        raise ValueError(f"máquina no soportada: {machine_id!r}. Disponibles: {supported}") from exc


def resolve_default_rom_path(spec: MachineSpec) -> Path | None:
    """Locate the canonical ROM filename for a machine in the search path."""

    if spec.rom_filename is None:
        return None

    for directory in get_default_rom_search_dirs():
        candidate = directory / spec.rom_filename
        if candidate.is_file():
            return candidate

    return None


def instantiate_machine(machine_id: str, *, rom_path: str | Path | None = None):
    """Build and reset a machine instance, optionally loading a ROM from disk.

    The reset happens here so every CLI entry point starts from a clean machine
    state regardless of the concrete class constructor details.
    """

    spec = get_machine_spec(machine_id)
    rom_data = None

    if rom_path is None:
        rom_path = resolve_default_rom_path(spec)

        if rom_path is None and spec.rom_filename is not None:
            search_dirs = ", ".join(str(path) for path in get_default_rom_search_dirs())
            raise FileNotFoundError(
                f"no se encontró la ROM {spec.rom_filename!r} para {spec.machine_id!r} "
                f"en: {search_dirs}"
            )

    if rom_path is not None:
        rom_data = Path(rom_path).read_bytes()

    machine = spec.factory(rom_data)
    machine.reset()
    return machine
