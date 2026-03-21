from __future__ import annotations

"""Central machine registry used by the CLI and future orchestration layers.

The goal is to keep machine discovery and instantiation out of the argument
parser so new frontends or automation entry points can reuse the same factory.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable
import warnings

from machines.gameboy import DMG
from machines.z80 import CPC464, Spectrum16K, Spectrum48K
from video import get_display_profile


@dataclass(frozen=True, slots=True)
class RomSlotSpec:
    """Declarative ROM slot exposed by a machine definition."""

    slot_id: str
    description: str
    filenames: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True, slots=True)
class MachineSpec:
    """Declarative description for a machine entry exposed to the user."""

    machine_id: str
    display_name: str
    factory: Callable[[dict[str, bytes], str], object]
    rom_slots: tuple[RomSlotSpec, ...] = ()


MACHINE_SPECS: dict[str, MachineSpec] = {
    "spectrum16k": MachineSpec(
        machine_id="spectrum16k",
        display_name="ZX Spectrum 16K",
        factory=lambda roms, display_profile: Spectrum16K(
            roms["main"],
            tape_data=roms.get("tape"),
            display_profile=display_profile,
        ),
        rom_slots=(
            RomSlotSpec(
                slot_id="main",
                description="ROM principal del Spectrum 16K",
                filenames=("spec16k.rom",),
            ),
            RomSlotSpec(
                slot_id="tape",
                description="Imagen de cinta TZX para Spectrum",
                filenames=("program.tzx", "tape.tzx"),
                required=False,
            ),
        ),
    ),
    "spectrum48k": MachineSpec(
        machine_id="spectrum48k",
        display_name="ZX Spectrum 48K",
        factory=lambda roms, display_profile: Spectrum48K(
            roms["main"],
            tape_data=roms.get("tape"),
            display_profile=display_profile,
        ),
        rom_slots=(
            RomSlotSpec(
                slot_id="main",
                description="ROM principal del Spectrum 48K",
                filenames=("spec48k.rom",),
            ),
            RomSlotSpec(
                slot_id="tape",
                description="Imagen de cinta TZX para Spectrum",
                filenames=("program.tzx", "tape.tzx"),
                required=False,
            ),
        ),
    ),
    "cpc464": MachineSpec(
        machine_id="cpc464",
        display_name="Amstrad CPC 464 (experimental)",
        factory=lambda roms, display_profile: CPC464(
            roms["os"],
            basic_rom_data=roms.get("basic"),
            tape_data=roms.get("tape"),
            display_profile=display_profile,
        ),
        rom_slots=(
            RomSlotSpec(
                slot_id="os",
                description="ROM baja del sistema CPC464",
                filenames=("OS_464.ROM",),
            ),
            RomSlotSpec(
                slot_id="basic",
                description="ROM alta de BASIC del CPC464",
                filenames=(
                    "BASIC_1.0.ROM",
                    "BASIC_1.1.ROM",
                    "BASIC_464.ROM",
                    "BASIC.ROM",
                    "cpc464.rom",
                ),
                required=False,
            ),
            RomSlotSpec(
                slot_id="tape",
                description="Imagen de cassette CDT/TZX para CPC464",
                filenames=("program.cdt", "tape.cdt"),
                required=False,
            ),
        ),
    ),
    "gameboy": MachineSpec(
        machine_id="gameboy",
        display_name="Nintendo Game Boy (early scaffold)",
        factory=lambda roms, display_profile: DMG(roms["main"]),
        rom_slots=(
            RomSlotSpec(
                slot_id="main",
                description="ROM principal/cartucho de Game Boy",
                filenames=("gameboy.gb", "cart.gb"),
            ),
        ),
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


def get_rom_slot(spec: MachineSpec, slot_id: str) -> RomSlotSpec:
    """Resolve a ROM slot id for a given machine specification."""

    for slot in spec.rom_slots:
        if slot.slot_id == slot_id:
            return slot
    supported = ", ".join(slot.slot_id for slot in spec.rom_slots)
    raise ValueError(f"slot de ROM no soportado: {slot_id!r}. Disponibles: {supported}")


def has_single_rom_slot(spec: MachineSpec) -> bool:
    """Return whether the machine exposes exactly one ROM slot."""

    if len(spec.rom_slots) == 1:
        return True

    required_slots = [slot for slot in spec.rom_slots if slot.required]
    optional_slots = [slot for slot in spec.rom_slots if not slot.required]
    return (
        len(required_slots) == 1
        and len(optional_slots) == 1
        and optional_slots[0].slot_id == "tape"
    )


def parse_cli_rom_specs(machine_id: str, rom_specs: list[str] | None) -> dict[str, Path]:
    """Parse CLI ROM assignments into a slot->path mapping.

    Accepted forms:
    - `slot=path` for any machine
    - `path` only for machines that expose exactly one ROM slot
    """

    spec = get_machine_spec(machine_id)
    rom_map: dict[str, Path] = {}

    for raw_spec in rom_specs or []:
        if "=" in raw_spec:
            slot_id, path_str = raw_spec.split("=", 1)
            slot_id = slot_id.strip()
            path_str = path_str.strip()
            if not slot_id or not path_str:
                raise ValueError(f"asignación de ROM inválida: {raw_spec!r}")
            get_rom_slot(spec, slot_id)
            rom_map[slot_id] = Path(path_str)
            continue

        if not has_single_rom_slot(spec):
            raise ValueError(
                f"{machine_id!r} usa varios slots de ROM; especifica `slot=fichero`, por ejemplo "
                f"`--rom {spec.rom_slots[0].slot_id}=...`"
            )

        rom_map[spec.rom_slots[0].slot_id] = Path(raw_spec)

    return rom_map


def resolve_rom_slot_path(slot: RomSlotSpec, search_dirs: list[Path]) -> Path | None:
    """Locate the first ROM image for a slot that exists in ``search_dirs``."""

    for directory in search_dirs:
        for filename in slot.filenames:
            candidate = directory / filename
            if candidate.is_file():
                return candidate

    return None


def resolve_machine_rom_paths(
    machine_id: str,
    *,
    roms: dict[str, str | Path] | None = None,
) -> dict[str, Path]:
    """Resolve explicit/default ROM assignments for a machine."""

    spec = get_machine_spec(machine_id)
    rom_paths: dict[str, Path] = {}
    explicit_roms = {slot_id: Path(path) for slot_id, path in (roms or {}).items()}

    for slot_id in explicit_roms:
        get_rom_slot(spec, slot_id)

    search_dirs = []
    seen_dirs: set[Path] = set()
    for path in explicit_roms.values():
        parent = path.parent
        if parent not in seen_dirs:
            search_dirs.append(parent)
            seen_dirs.add(parent)
    for directory in get_default_rom_search_dirs():
        if directory not in seen_dirs:
            search_dirs.append(directory)
            seen_dirs.add(directory)

    for slot in spec.rom_slots:
        explicit_path = explicit_roms.get(slot.slot_id)
        if explicit_path is not None:
            rom_paths[slot.slot_id] = explicit_path
            continue

        candidate = resolve_rom_slot_path(slot, search_dirs)
        if candidate is not None:
            rom_paths[slot.slot_id] = candidate
            continue

        if slot.required:
            search_dirs_str = ", ".join(str(path) for path in search_dirs)
            filenames = ", ".join(slot.filenames)
            raise FileNotFoundError(
                f"no se encontró la ROM del slot {slot.slot_id!r} para {spec.machine_id!r} "
                f"(nombres buscados: {filenames}) en: {search_dirs_str}"
            )

    return rom_paths


def instantiate_machine(
    machine_id: str,
    *,
    roms: dict[str, str | Path] | None = None,
    display_profile: str = "default",
):
    """Build and reset a machine instance, resolving any needed ROM slots first.

    The reset happens here so every CLI entry point starts from a clean machine
    state regardless of the concrete class constructor details.
    """

    spec = get_machine_spec(machine_id)
    # Resolve early so the CLI fails with a user-facing error before reading
    # ROMs or constructing a machine with an unsupported monitor profile.
    get_display_profile(display_profile)
    rom_paths = resolve_machine_rom_paths(machine_id, roms=roms)
    rom_bytes = {slot_id: path.read_bytes() for slot_id, path in rom_paths.items()}

    if spec.machine_id == "cpc464" and "os" in rom_bytes and len(rom_bytes["os"]) == 0x8000:
        combined = rom_bytes.pop("os")
        rom_bytes["os"] = combined[:0x4000]
        rom_bytes.setdefault("basic", combined[0x4000:])

    if spec.machine_id == "cpc464" and "basic" not in rom_bytes:
        warnings.warn(
            "CPC464 sin ROM alta de BASIC: el arranque puede acabar ejecutando RAM "
            "y mostrar pantalla corrupta. Proporciona una ROM combinada de 32 KB "
            "o una ROM BASIC compatible.",
            stacklevel=2,
        )

    machine = spec.factory(rom_bytes, display_profile)
    # Expose the registry identity on the concrete instance so transport and
    # frontend layers can describe the machine without hardcoding families.
    machine.machine_id = spec.machine_id
    machine.display_name = spec.display_name
    machine.reset()
    return machine
