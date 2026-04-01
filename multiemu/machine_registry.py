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

from machines.gameboy import CGB, DMG
from machines.m6502 import KIM1, VIC20NTSC, VIC20PAL
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
                description="Imagen de cinta TZX/TAP para Spectrum",
                filenames=("program.tzx", "tape.tzx", "program.tap", "tape.tap"),
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
                description="Imagen de cinta TZX/TAP para Spectrum",
                filenames=("program.tzx", "tape.tzx", "program.tap", "tape.tap"),
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
            amsdos_rom_data=roms.get("amsdos"),
            tape_data=roms.get("tape"),
            disk_data=roms.get("disk"),
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
                slot_id="amsdos",
                description="ROM AMSDOS/expansión de disco para CPC",
                filenames=("AMSDOS.ROM", "amsdos.rom"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="tape",
                description="Imagen de cassette CDT/TZX para CPC464",
                filenames=("program.cdt", "tape.cdt"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="disk",
                description="Imagen DSK para CPC",
                filenames=("disk.dsk", "program.dsk"),
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
    "gameboycolor": MachineSpec(
        machine_id="gameboycolor",
        display_name="Nintendo Game Boy Color (early scaffold)",
        factory=lambda roms, display_profile: CGB(roms["main"]),
        rom_slots=(
            RomSlotSpec(
                slot_id="main",
                description="ROM principal/cartucho de Game Boy Color",
                filenames=("gameboycolor.gbc", "gameboy.gbc", "cart.gbc", "cart.gb"),
            ),
        ),
    ),
    "gbc": MachineSpec(
        machine_id="gbc",
        display_name="Nintendo Game Boy Color (alias de gameboycolor)",
        factory=lambda roms, display_profile: CGB(roms["main"]),
        rom_slots=(
            RomSlotSpec(
                slot_id="main",
                description="ROM principal/cartucho de Game Boy Color",
                filenames=("gameboycolor.gbc", "gameboy.gbc", "cart.gbc", "cart.gb"),
            ),
        ),
    ),
    "kim1": MachineSpec(
        machine_id="kim1",
        display_name="MOS KIM-1 (early scaffold)",
        factory=lambda roms, display_profile: KIM1(
            roms["lower"],
            roms["upper"],
        ),
        rom_slots=(
            RomSlotSpec(
                slot_id="lower",
                description="ROM baja 6530-002 del KIM-1",
                filenames=(),
            ),
            RomSlotSpec(
                slot_id="upper",
                description="ROM alta 6530-003 del KIM-1",
                filenames=(),
            ),
        ),
    ),
    "vic20ntsc": MachineSpec(
        machine_id="vic20ntsc",
        display_name="Commodore VIC-20 NTSC (experimental)",
        factory=lambda roms, display_profile: VIC20NTSC(
            roms["basic"],
            roms["kernal"],
            roms["char"],
            blk1_rom_data=roms.get("blk1"),
            blk2_rom_data=roms.get("blk2"),
            blk3_rom_data=roms.get("blk3"),
            blk5_rom_data=roms.get("blk5"),
            io2_ram_enabled="__io2ram__" in roms,
            io3_ram_enabled="__io2ram__" in roms,
        ),
        rom_slots=(
            RomSlotSpec(
                slot_id="basic",
                description="ROM BASIC del VIC-20",
                filenames=("BASIC.901486-01.bin", "basic.901486-01.bin", "vic20_basic.bin", "vic20-basic.bin"),
            ),
            RomSlotSpec(
                slot_id="kernal",
                description="ROM KERNAL del VIC-20",
                filenames=("KERNAL.901486-07.bin", "kernal.901486-07.bin", "vic20_kernal.bin", "vic20-kernal.bin"),
            ),
            RomSlotSpec(
                slot_id="char",
                description="ROM de caracteres del VIC-20",
                filenames=("CHAR.901460-03.bin", "characters.901460-03.bin", "vic20_char.bin", "vic20-char.bin"),
            ),
            RomSlotSpec(
                slot_id="blk1",
                description="ROM opcional de expansión BLK1 del VIC-20",
                filenames=("vic20_blk1.bin", "vic20-blk1.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk2",
                description="ROM opcional de expansión BLK2 del VIC-20",
                filenames=("vic20_blk2.bin", "vic20-blk2.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk3",
                description="ROM opcional de expansión BLK3 del VIC-20",
                filenames=("vic20_blk3.bin", "vic20-blk3.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk5",
                description="ROM opcional de expansión BLK5 del VIC-20",
                filenames=("vic20_blk5.bin", "vic20-blk5.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="cart",
                description="Cartucho VIC-20 en formato PRG para un único bloque",
                filenames=(),
                required=False,
            ),
        ),
    ),
    "vic20pal": MachineSpec(
        machine_id="vic20pal",
        display_name="Commodore VIC-20 PAL (experimental)",
        factory=lambda roms, display_profile: VIC20PAL(
            roms["basic"],
            roms["kernal"],
            roms["char"],
            blk1_rom_data=roms.get("blk1"),
            blk2_rom_data=roms.get("blk2"),
            blk3_rom_data=roms.get("blk3"),
            blk5_rom_data=roms.get("blk5"),
            io2_ram_enabled="__io2ram__" in roms,
            io3_ram_enabled="__io2ram__" in roms,
        ),
        rom_slots=(
            RomSlotSpec(
                slot_id="basic",
                description="ROM BASIC del VIC-20",
                filenames=("BASIC.901486-01.bin", "basic.901486-01.bin", "vic20_basic.bin", "vic20-basic.bin"),
            ),
            RomSlotSpec(
                slot_id="kernal",
                description="ROM KERNAL del VIC-20",
                filenames=("KERNAL.901486-07.bin", "kernal.901486-07.bin", "vic20_kernal.bin", "vic20-kernal.bin"),
            ),
            RomSlotSpec(
                slot_id="char",
                description="ROM de caracteres del VIC-20",
                filenames=("CHAR.901460-03.bin", "characters.901460-03.bin", "vic20_char.bin", "vic20-char.bin"),
            ),
            RomSlotSpec(
                slot_id="blk1",
                description="ROM opcional de expansión BLK1 del VIC-20",
                filenames=("vic20_blk1.bin", "vic20-blk1.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk2",
                description="ROM opcional de expansión BLK2 del VIC-20",
                filenames=("vic20_blk2.bin", "vic20-blk2.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk3",
                description="ROM opcional de expansión BLK3 del VIC-20",
                filenames=("vic20_blk3.bin", "vic20-blk3.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk5",
                description="ROM opcional de expansión BLK5 del VIC-20",
                filenames=("vic20_blk5.bin", "vic20-blk5.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="cart",
                description="Cartucho VIC-20 en formato PRG para un único bloque",
                filenames=(),
                required=False,
            ),
        ),
    ),
    "vic20": MachineSpec(
        machine_id="vic20",
        display_name="Commodore VIC-20 (alias de vic20ntsc)",
        factory=lambda roms, display_profile: VIC20NTSC(
            roms["basic"],
            roms["kernal"],
            roms["char"],
            blk1_rom_data=roms.get("blk1"),
            blk2_rom_data=roms.get("blk2"),
            blk3_rom_data=roms.get("blk3"),
            blk5_rom_data=roms.get("blk5"),
            io2_ram_enabled="__io2ram__" in roms,
            io3_ram_enabled="__io2ram__" in roms,
        ),
        rom_slots=(
            RomSlotSpec(
                slot_id="basic",
                description="ROM BASIC del VIC-20 NTSC",
                filenames=("BASIC.901486-01.bin", "basic.901486-01.bin", "vic20_basic.bin", "vic20-basic.bin"),
            ),
            RomSlotSpec(
                slot_id="kernal",
                description="ROM KERNAL del VIC-20 NTSC",
                filenames=("KERNAL.901486-07.bin", "kernal.901486-07.bin", "vic20_kernal.bin", "vic20-kernal.bin"),
            ),
            RomSlotSpec(
                slot_id="char",
                description="ROM de caracteres del VIC-20 NTSC",
                filenames=("CHAR.901460-03.bin", "characters.901460-03.bin", "vic20_char.bin", "vic20-char.bin"),
            ),
            RomSlotSpec(
                slot_id="blk1",
                description="ROM opcional de expansión BLK1 del VIC-20 NTSC",
                filenames=("vic20_blk1.bin", "vic20-blk1.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk2",
                description="ROM opcional de expansión BLK2 del VIC-20 NTSC",
                filenames=("vic20_blk2.bin", "vic20-blk2.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk3",
                description="ROM opcional de expansión BLK3 del VIC-20 NTSC",
                filenames=("vic20_blk3.bin", "vic20-blk3.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="blk5",
                description="ROM opcional de expansión BLK5 del VIC-20 NTSC",
                filenames=("vic20_blk5.bin", "vic20-blk5.bin"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="cart",
                description="Cartucho VIC-20 NTSC en formato PRG para un único bloque",
                filenames=(),
                required=False,
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


def _decode_vic20_cartridge_image(path: Path, cart_bytes: bytes) -> list[tuple[str, bytes]]:
    """Convert a VIC-20 cartridge image into one or more concrete slots."""

    if len(cart_bytes) < 3:
        raise ValueError("la imagen de cartucho VIC-20 es demasiado pequeña")

    lower_suffix = path.suffix.lower()

    # Raw BLK5 cartridge ROMs store the autostart header in-place at A000:
    # cold/warm vectors followed by the PETSCII "A0CBM" signature.
    if (
        0 < len(cart_bytes) <= 0x2000
        and len(cart_bytes) >= 9
        and cart_bytes[4:9] == bytes((0x41, 0x30, 0xC3, 0xC2, 0xCD))
    ):
        return [("blk5", cart_bytes)]

    if lower_suffix in {".20", ".40", ".60", ".a0"}:
        raw_slot_by_suffix = {
            ".20": ("blk1", "blk2"),
            ".40": ("blk2", "blk3"),
            ".60": ("blk3", "blk5"),
            ".a0": ("blk5",),
        }
        raw_slots = raw_slot_by_suffix[lower_suffix]
        if len(cart_bytes) == 0x2000:
            return [(raw_slots[0], cart_bytes)]
        if len(cart_bytes) == 0x4000 and len(raw_slots) >= 2:
            return [
                (raw_slots[0], cart_bytes[:0x2000]),
                (raw_slots[1], cart_bytes[0x2000:]),
            ]
        raise ValueError(
            f"cartucho VIC-20 crudo {path.name!r} con tamaño no soportado: {len(cart_bytes)} bytes"
        )

    load_addr = cart_bytes[0] | (cart_bytes[1] << 8)
    payload = cart_bytes[2:]
    slot_by_addr = {
        0x2000: "blk1",
        0x4000: "blk2",
        0x6000: "blk3",
        0xA000: "blk5",
    }
    slot_id = slot_by_addr.get(load_addr)
    if slot_id is None:
        raise ValueError(
            f"cartucho VIC-20 con dirección de carga no soportada: 0x{load_addr:04X}. "
            "Se esperan PRG para 0x2000, 0x4000, 0x6000 o 0xA000, o dumps crudos .20/.40/.60/.a0."
        )
    if len(payload) == 0 or len(payload) > 0x2000:
        raise ValueError(
            f"cartucho VIC-20 en 0x{load_addr:04X} con tamaño no soportado: {len(payload)} bytes"
        )
    return [(slot_id, payload)]


def _find_vic20_companion_cartridge_path(path: Path) -> Path | None:
    """Return the sibling PRG that complements a 16K VIC-20 cartridge pair."""

    lower_name = path.name.lower()
    if "6000" in lower_name:
        candidate = path.with_name(path.name.replace("6000", "a000").replace("6000", "a000"))
        if candidate.is_file():
            return candidate
        candidate = path.with_name(lower_name.replace("6000", "a000"))
        if candidate.is_file():
            return candidate
        return None
    if "a000" in lower_name:
        candidate = path.with_name(path.name.replace("a000", "6000").replace("A000", "6000"))
        if candidate.is_file():
            return candidate
        candidate = path.with_name(lower_name.replace("a000", "6000"))
        if candidate.is_file():
            return candidate
        return None
    return None


def _is_vic20_diag_cart(path: Path, cart_bytes: bytes) -> bool:
    lower_name = path.name.lower()
    if "diag-vic20" in lower_name or "324173-01" in lower_name:
        return True
    return len(cart_bytes) == 0x1000 and cart_bytes[:9] == bytes((0x19, 0xA0, 0x19, 0xA0, 0x41, 0x30, 0xC3, 0xC2, 0xCD))


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
            filenames = ", ".join(slot.filenames) if slot.filenames else "sin nombres por defecto"
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
    vic20_diag_io_ram = False

    if machine_id in {"vic20", "vic20ntsc", "vic20pal"} and "cart" in rom_bytes:
        cart_path = rom_paths["cart"]
        cart_image = rom_bytes.pop("cart")
        vic20_diag_io_ram = _is_vic20_diag_cart(cart_path, cart_image)
        cart_images = [(cart_path, cart_image)]
        companion_path = _find_vic20_companion_cartridge_path(cart_path)
        if companion_path is not None:
            cart_images.append((companion_path, companion_path.read_bytes()))

        seen_slots: set[str] = set()
        for image_path, image_bytes in cart_images:
            decoded_slots = _decode_vic20_cartridge_image(image_path, image_bytes)
            for slot_id, payload in decoded_slots:
                if slot_id in rom_bytes:
                    raise ValueError(
                        f"cartucho VIC-20 mapeado a {slot_id!r}, pero ese slot ya se proporcionó explícitamente"
                    )
                if slot_id in seen_slots:
                    raise ValueError(
                        f"se detectaron dos imágenes de cartucho VIC-20 para el mismo slot {slot_id!r}"
                    )
                rom_bytes[slot_id] = payload
                seen_slots.add(slot_id)

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

    if spec.machine_id in {"vic20", "vic20ntsc", "vic20pal"}:
        if vic20_diag_io_ram:
            rom_bytes = rom_bytes | {"__io2ram__": b"\x01"}
        machine = spec.factory(rom_bytes, display_profile)
    else:
        machine = spec.factory(rom_bytes, display_profile)
    # Expose the registry identity on the concrete instance so transport and
    # frontend layers can describe the machine without hardcoding families.
    machine.machine_id = spec.machine_id
    machine.display_name = spec.display_name
    machine.reset()
    return machine
