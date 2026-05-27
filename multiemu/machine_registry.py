from __future__ import annotations

"""Central machine registry used by the CLI and future orchestration layers.

The goal is to keep machine discovery and instantiation out of the argument
parser so new frontends or automation entry points can reuse the same factory.
"""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable
import warnings

from machines.gameboy import CGB, DMG
from machines.m6502 import KIM1, VIC20NTSC, VIC20PAL
from machines.z80 import ColecoVision, CPC464, CPC6128, CPC664, GameGear, MasterSystem2, MSX1, Spectrum128K, Spectrum16K, Spectrum48K, SpectrumPlus2
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


SPECTRUM_TAPE_SLOT = RomSlotSpec(
    slot_id="tape",
    description="Imagen de cinta TZX/TAP para Spectrum",
    filenames=("program.tzx", "tape.tzx", "program.tap", "tape.tap"),
    required=False,
)

SPECTRUM_TAPE_PLUS2_SLOT = RomSlotSpec(
    slot_id="tape",
    description="Imagen de cinta TZX/TAP para Spectrum +2",
    filenames=("program.tzx", "tape.tzx", "program.tap", "tape.tap"),
    required=False,
)

CPC_EXPANSION_SLOT = RomSlotSpec(
    slot_id="expansion",
    description="ROM alta de expansión/cartucho CPC",
    filenames=(),
    required=False,
)

VIC20_BLK_SLOT_FILENAMES = {
    "blk1": ("vic20_blk1.bin", "vic20-blk1.bin"),
    "blk2": ("vic20_blk2.bin", "vic20-blk2.bin"),
    "blk3": ("vic20_blk3.bin", "vic20-blk3.bin"),
    "blk5": ("vic20_blk5.bin", "vic20-blk5.bin"),
}


def _split_cpc_system_roms(roms: dict[str, bytes]) -> tuple[bytes, bytes | None]:
    """Accept CPC OS ROMs as either 16K OS or combined 32K OS+BASIC images."""

    os_rom = roms["os"]
    basic_rom = roms.get("basic")
    if len(os_rom) == 0x8000:
        split_basic_rom = os_rom[0x4000:]
        if basic_rom is not None and basic_rom != split_basic_rom:
            raise ValueError("no se puede combinar una ROM CPC de 32K en 'os' con un slot 'basic' explícito")
        return os_rom[:0x4000], split_basic_rom
    return os_rom, basic_rom


def _build_cpc_machine(machine_type: type[CPC464] | type[CPC664] | type[CPC6128], roms: dict[str, bytes], display_profile: str) -> object:
    os_rom, basic_rom = _split_cpc_system_roms(roms)
    return machine_type(
        os_rom,
        basic_rom_data=basic_rom,
        amsdos_rom_data=roms.get("amsdos"),
        expansion_rom_data=roms.get("expansion"),
        disk_data=roms.get("disk"),
        display_profile=display_profile,
        tape_data=roms.get("tape"),
    )


def _build_spectrum_machine(
    machine_type: type[Spectrum16K] | type[Spectrum48K] | type[Spectrum128K] | type[SpectrumPlus2],
    roms: dict[str, bytes],
    display_profile: str,
    *,
    default_rom_size: int,
) -> object:
    return machine_type(
        roms.get("main", bytes([0x00]) * default_rom_size),
        tape_data=roms.get("tape"),
        snapshot_data=roms.get("snapshot"),
        display_profile=display_profile,
    )


def _build_cpc464(roms: dict[str, bytes], display_profile: str) -> CPC464:
    return _build_cpc_machine(CPC464, roms, display_profile)


def _build_cpc664(roms: dict[str, bytes], display_profile: str) -> CPC664:
    return _build_cpc_machine(CPC664, roms, display_profile)


def _build_cpc6128(roms: dict[str, bytes], display_profile: str) -> CPC6128:
    return _build_cpc_machine(CPC6128, roms, display_profile)


def _build_spectrum16k(roms: dict[str, bytes], display_profile: str) -> Spectrum16K:
    return _build_spectrum_machine(Spectrum16K, roms, display_profile, default_rom_size=0x4000)


def _build_spectrum48k(roms: dict[str, bytes], display_profile: str) -> Spectrum48K:
    return _build_spectrum_machine(Spectrum48K, roms, display_profile, default_rom_size=0x4000)


def _build_spectrum128k(roms: dict[str, bytes], display_profile: str) -> Spectrum128K:
    return _build_spectrum_machine(Spectrum128K, roms, display_profile, default_rom_size=0x8000)


def _build_spectrumplus2(roms: dict[str, bytes], display_profile: str) -> SpectrumPlus2:
    return _build_spectrum_machine(SpectrumPlus2, roms, display_profile, default_rom_size=0x8000)


def _build_mastersystem2(roms: dict[str, bytes], display_profile: str) -> MasterSystem2:
    if "main" not in roms and "bios" not in roms:
        raise FileNotFoundError("mastersystem2 requiere `main` o `bios`")
    return MasterSystem2(
        roms.get("main"),
        bios_data=roms.get("bios"),
        display_profile=display_profile,
    )


def _build_gamegear(roms: dict[str, bytes], display_profile: str) -> GameGear:
    if "main" not in roms and "bios" not in roms:
        raise FileNotFoundError("gamegear requiere `main` o `bios`")
    return GameGear(
        roms.get("main"),
        bios_data=roms.get("bios"),
        display_profile=display_profile,
    )


def _build_colecovision(roms: dict[str, bytes], display_profile: str) -> ColecoVision:
    if "bios" not in roms:
        raise FileNotFoundError("colecovision requiere `bios`")
    return ColecoVision(
        roms.get("main"),
        bios_data=roms["bios"],
        display_profile=display_profile,
    )


def _build_msx(roms: dict[str, bytes], display_profile: str, machine_options: dict[str, str] | None = None) -> MSX1:
    if "bios" not in roms:
        raise FileNotFoundError("msx requiere `bios`")
    options = machine_options or {}
    return MSX1(
        roms["bios"],
        basic_data=roms.get("basic"),
        cart1_data=roms.get("cart1"),
        cart2_data=roms.get("cart2"),
        cart1_mapper=options.get("cart1_mapper"),
        cart2_mapper=options.get("cart2_mapper"),
        tape_data=roms.get("tape"),
        display_profile=display_profile,
    )


def _build_dmg(roms: dict[str, bytes], display_profile: str) -> DMG:
    del display_profile
    return DMG(roms["main"])


def _build_cgb(roms: dict[str, bytes], display_profile: str) -> CGB:
    del display_profile
    return CGB(roms["main"])


def _build_kim1(roms: dict[str, bytes], display_profile: str) -> KIM1:
    del display_profile
    return KIM1(roms["lower"], roms["upper"])


def _build_vic20(
    machine_type: type[VIC20NTSC] | type[VIC20PAL],
    roms: dict[str, bytes],
    display_profile: str,
) -> object:
    del display_profile
    return machine_type(
        roms["basic"],
        roms["kernal"],
        roms["char"],
        blk1_rom_data=roms.get("blk1"),
        blk2_rom_data=roms.get("blk2"),
        blk3_rom_data=roms.get("blk3"),
        blk5_rom_data=roms.get("blk5"),
        io2_ram_enabled="__io2ram__" in roms,
        io3_ram_enabled="__io2ram__" in roms,
    )


def _build_vic20ntsc(roms: dict[str, bytes], display_profile: str) -> VIC20NTSC:
    return _build_vic20(VIC20NTSC, roms, display_profile)


def _build_vic20pal(roms: dict[str, bytes], display_profile: str) -> VIC20PAL:
    return _build_vic20(VIC20PAL, roms, display_profile)


def _make_spectrum_slots(main_description: str, main_filenames: tuple[str, ...], snapshot_description: str, *, plus2_tape: bool = False) -> tuple[RomSlotSpec, ...]:
    return (
        RomSlotSpec(
            slot_id="main",
            description=main_description,
            filenames=main_filenames,
        ),
        SPECTRUM_TAPE_PLUS2_SLOT if plus2_tape else SPECTRUM_TAPE_SLOT,
        RomSlotSpec(
            slot_id="snapshot",
            description=snapshot_description,
            filenames=(),
            required=False,
        ),
    )


def _make_cpc_slots(
    *,
    model: str,
    os_description: str,
    os_filenames: tuple[str, ...],
    basic_description: str,
    basic_filenames: tuple[str, ...],
    amsdos_description: str,
    amsdos_filenames: tuple[str, ...],
) -> tuple[RomSlotSpec, ...]:
    return (
        RomSlotSpec(
            slot_id="os",
            description=os_description,
            filenames=os_filenames,
        ),
        RomSlotSpec(
            slot_id="basic",
            description=basic_description,
            filenames=basic_filenames,
            required=False,
        ),
        RomSlotSpec(
            slot_id="amsdos",
            description=amsdos_description,
            filenames=amsdos_filenames,
            required=False,
        ),
        CPC_EXPANSION_SLOT,
        RomSlotSpec(
            slot_id="tape",
            description=f"Imagen de cassette CDT/TZX para {model}",
            filenames=("program.cdt", "tape.cdt"),
            required=False,
        ),
        RomSlotSpec(
            slot_id="disk",
            description=f"Imagen DSK para {model}",
            filenames=("disk.dsk", "program.dsk"),
            required=False,
        ),
    )


def _make_vic20_slots(*, variant_label: str = "") -> tuple[RomSlotSpec, ...]:
    label = f" {variant_label}" if variant_label else ""
    return (
        RomSlotSpec(
            slot_id="basic",
            description=f"ROM BASIC del VIC-20{label}",
            filenames=("BASIC.901486-01.bin", "basic.901486-01.bin", "vic20_basic.bin", "vic20-basic.bin"),
        ),
        RomSlotSpec(
            slot_id="kernal",
            description=f"ROM KERNAL del VIC-20{label}",
            filenames=("KERNAL.901486-07.bin", "kernal.901486-07.bin", "vic20_kernal.bin", "vic20-kernal.bin"),
        ),
        RomSlotSpec(
            slot_id="char",
            description=f"ROM de caracteres del VIC-20{label}",
            filenames=("CHAR.901460-03.bin", "characters.901460-03.bin", "vic20_char.bin", "vic20-char.bin"),
        ),
        RomSlotSpec(
            slot_id="blk1",
            description=f"ROM opcional de expansión BLK1 del VIC-20{label}",
            filenames=VIC20_BLK_SLOT_FILENAMES["blk1"],
            required=False,
        ),
        RomSlotSpec(
            slot_id="blk2",
            description=f"ROM opcional de expansión BLK2 del VIC-20{label}",
            filenames=VIC20_BLK_SLOT_FILENAMES["blk2"],
            required=False,
        ),
        RomSlotSpec(
            slot_id="blk3",
            description=f"ROM opcional de expansión BLK3 del VIC-20{label}",
            filenames=VIC20_BLK_SLOT_FILENAMES["blk3"],
            required=False,
        ),
        RomSlotSpec(
            slot_id="blk5",
            description=f"ROM opcional de expansión BLK5 del VIC-20{label}",
            filenames=VIC20_BLK_SLOT_FILENAMES["blk5"],
            required=False,
        ),
        RomSlotSpec(
            slot_id="cart",
            description=f"Cartucho VIC-20{label} en formato PRG para un único bloque",
            filenames=(),
            required=False,
        ),
    )


MACHINE_SPECS: dict[str, MachineSpec] = {
    "spectrum16k": MachineSpec(
        machine_id="spectrum16k",
        display_name="ZX Spectrum 16K",
        factory=_build_spectrum16k,
        rom_slots=_make_spectrum_slots(
            "ROM principal del Spectrum 16K",
            ("spec16k.rom",),
            "Snapshot .z80 para Spectrum",
        ),
    ),
    "spectrum48k": MachineSpec(
        machine_id="spectrum48k",
        display_name="ZX Spectrum 48K",
        factory=_build_spectrum48k,
        rom_slots=_make_spectrum_slots(
            "ROM principal del Spectrum 48K",
            ("spec48k.rom",),
            "Snapshot .z80 para Spectrum",
        ),
    ),
    "spectrum128k": MachineSpec(
        machine_id="spectrum128k",
        display_name="ZX Spectrum 128K",
        factory=_build_spectrum128k,
        rom_slots=_make_spectrum_slots(
            "ROM principal del Spectrum 128K",
            ("spec128k.rom", "spectrum128k.rom"),
            "Snapshot .z80 para Spectrum 128K",
        ),
    ),
    "spectrumplus2": MachineSpec(
        machine_id="spectrumplus2",
        display_name="ZX Spectrum +2",
        factory=_build_spectrumplus2,
        rom_slots=_make_spectrum_slots(
            "ROM principal del Spectrum +2",
            ("plus2.rom", "specplus2.rom", "spectrumplus2.rom", "zx128k_2plus_es.rom"),
            "Snapshot .z80 para Spectrum +2",
            plus2_tape=True,
        ),
    ),
    "mastersystem2": MachineSpec(
        machine_id="mastersystem2",
        display_name="Sega Master System II (early scaffold)",
        factory=_build_mastersystem2,
        rom_slots=(
            RomSlotSpec(
                slot_id="bios",
                description="BIOS interna de Master System II",
                filenames=("bios.sms", "akbios.sms", "mastersystem2_bios.sms"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="main",
                description="Cartucho principal de Master System II",
                filenames=("mastersystem2.sms", "mastersystem.sms", "game.sms", "cart.sms"),
                required=False,
            ),
        ),
    ),
    "gamegear": MachineSpec(
        machine_id="gamegear",
        display_name="Sega Game Gear",
        factory=_build_gamegear,
        rom_slots=(
            RomSlotSpec(
                slot_id="bios",
                description="BIOS interna de Game Gear",
                filenames=("gamegear_bios.gg", "bios.gg", "gg_bios.gg"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="main",
                description="Cartucho principal de Game Gear",
                filenames=("gamegear.gg", "game.gg", "cart.gg"),
                required=False,
            ),
        ),
    ),
    "colecovision": MachineSpec(
        machine_id="colecovision",
        display_name="ColecoVision",
        factory=_build_colecovision,
        rom_slots=(
            RomSlotSpec(
                slot_id="bios",
                description="BIOS interna de ColecoVision",
                filenames=("coleco.rom", "bios.col", "colecovision.rom"),
            ),
            RomSlotSpec(
                slot_id="main",
                description="Cartucho principal de ColecoVision",
                filenames=("game.col", "cart.col", "colecovision.col"),
                required=False,
            ),
        ),
    ),
    "msx": MachineSpec(
        machine_id="msx",
        display_name="MSX1 (experimental)",
        factory=_build_msx,
        rom_slots=(
            RomSlotSpec(
                slot_id="bios",
                description="BIOS principal de MSX1",
                filenames=("msx.rom", "bios.rom", "hitbit_msx1.rom"),
            ),
            RomSlotSpec(
                slot_id="basic",
                description="ROM MSX BASIC",
                filenames=("basic.rom", "basic_msx1.rom", "msxbasic.rom"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="cart1",
                description="Cartucho ROM principal MSX",
                filenames=("cart.rom", "game.rom", "main.rom"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="cart2",
                description="Segundo cartucho ROM MSX",
                filenames=("cart2.rom", "sub.rom"),
                required=False,
            ),
            RomSlotSpec(
                slot_id="tape",
                description="Imagen de cassette CAS para MSX",
                filenames=("program.cas", "tape.cas"),
                required=False,
            ),
        ),
    ),
    "cpc464": MachineSpec(
        machine_id="cpc464",
        display_name="Amstrad CPC 464 (experimental)",
        factory=_build_cpc464,
        rom_slots=_make_cpc_slots(
            model="CPC464",
            os_description="ROM baja del sistema CPC464",
            os_filenames=("OS_464.ROM", "OS_464_BASIC_1.0.ROM", "OS_464_BASIC_1.1.ROM", "cpc464.rom"),
            basic_description="ROM alta de BASIC del CPC464",
            basic_filenames=("BASIC_1.0.ROM", "BASIC_1.1.ROM", "BASIC_464.ROM", "BASIC.ROM", "cpc464.rom"),
            amsdos_description="ROM AMSDOS/expansión de disco para CPC",
            amsdos_filenames=("AMSDOS.ROM", "amsdos.rom"),
        ),
    ),
    "cpc664": MachineSpec(
        machine_id="cpc664",
        display_name="Amstrad CPC 664 (experimental)",
        factory=_build_cpc664,
        rom_slots=_make_cpc_slots(
            model="CPC664",
            os_description="ROM baja del sistema CPC664",
            os_filenames=("OS_664.ROM", "OS_664_BASIC_1.1.ROM", "cpc664_os.rom", "cpc664.rom"),
            basic_description="ROM alta de BASIC del CPC664",
            basic_filenames=("BASIC_1.1.ROM", "BASIC_664.ROM", "BASIC.ROM", "cpc664_basic.rom"),
            amsdos_description="ROM AMSDOS del CPC664",
            amsdos_filenames=("AMSDOS.ROM", "amsdos.rom"),
        ),
    ),
    "cpc6128": MachineSpec(
        machine_id="cpc6128",
        display_name="Amstrad CPC 6128 (experimental)",
        factory=_build_cpc6128,
        rom_slots=_make_cpc_slots(
            model="CPC6128",
            os_description="ROM baja del sistema CPC6128",
            os_filenames=("OS_6128.ROM", "OS_6128_BASIC_1.1.ROM", "cpc6128_os.rom", "cpc6128.rom"),
            basic_description="ROM alta de BASIC del CPC6128",
            basic_filenames=("BASIC_1.1.ROM", "BASIC_6128.ROM", "BASIC.ROM", "cpc6128_basic.rom"),
            amsdos_description="ROM AMSDOS del CPC6128",
            amsdos_filenames=("AMSDOS.ROM", "amsdos.rom", "cpc6128_amsdos.rom"),
        ),
    ),
    "gameboy": MachineSpec(
        machine_id="gameboy",
        display_name="Nintendo Game Boy (early scaffold)",
        factory=_build_dmg,
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
        factory=_build_cgb,
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
        factory=_build_cgb,
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
        factory=_build_kim1,
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
        factory=_build_vic20ntsc,
        rom_slots=_make_vic20_slots(),
    ),
    "vic20pal": MachineSpec(
        machine_id="vic20pal",
        display_name="Commodore VIC-20 PAL (experimental)",
        factory=_build_vic20pal,
        rom_slots=_make_vic20_slots(),
    ),
    "vic20": MachineSpec(
        machine_id="vic20",
        display_name="Commodore VIC-20 (alias de vic20ntsc)",
        factory=_build_vic20ntsc,
        rom_slots=_make_vic20_slots(variant_label="NTSC"),
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
        and all(slot.slot_id in {"tape", "snapshot"} for slot in optional_slots)
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

        if machine_id in {"mastersystem2", "gamegear", "colecovision", "msx"}:
            path = Path(raw_spec)
            lower_name = path.name.lower()
            if machine_id == "msx":
                if path.suffix.lower() == ".cas":
                    rom_map["tape"] = path
                elif "basic" in lower_name:
                    rom_map["basic"] = path
                elif "bios" in lower_name or "msx1" in lower_name:
                    rom_map["bios"] = path
                else:
                    rom_map["cart1"] = path
            else:
                rom_map["bios" if "bios" in lower_name else "main"] = path
            continue

        if not has_single_rom_slot(spec):
            raise ValueError(
                f"{machine_id!r} usa varios slots de ROM; especifica `slot=fichero`, por ejemplo "
                f"`--rom {spec.rom_slots[0].slot_id}=...`"
            )

        rom_map[spec.rom_slots[0].slot_id] = Path(raw_spec)

    return rom_map


def parse_cli_machine_options(option_specs: list[str] | None) -> dict[str, str]:
    """Parse machine-specific CLI options from repeated key=value strings."""

    options: dict[str, str] = {}
    for raw_spec in option_specs or []:
        if "=" not in raw_spec:
            raise ValueError(f"opción de emulación inválida: {raw_spec!r}; se espera clave=valor")
        key, value = raw_spec.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"opción de emulación inválida: {raw_spec!r}; se espera clave=valor")
        options[key] = value
    return options


def _normalize_machine_options(machine_id: str, machine_options: dict[str, str] | None) -> dict[str, str]:
    options = dict(machine_options or {})
    if not options:
        return {}
    if machine_id == "msx":
        if "mapper" in options:
            if "cart1_mapper" in options and options["cart1_mapper"] != options["mapper"]:
                raise ValueError("opciones MSX incompatibles: `mapper` y `cart1_mapper` tienen valores distintos")
            options["cart1_mapper"] = options.pop("mapper")
        supported = {"cart1_mapper", "cart2_mapper"}
        unsupported = sorted(set(options) - supported)
        if unsupported:
            raise ValueError(
                f"opciones de emulación no soportadas para 'msx': {', '.join(unsupported)}. "
                f"Soportadas: {', '.join(sorted(supported | {'mapper'}))}"
            )
        return options

    unsupported = ", ".join(sorted(options))
    raise ValueError(f"opciones de emulación no soportadas para {machine_id!r}: {unsupported}")


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

        if machine_id == "mastersystem2" and explicit_roms:
            continue

        candidate = resolve_rom_slot_path(slot, search_dirs)
        if candidate is not None:
            rom_paths[slot.slot_id] = candidate
            continue

        if (
            slot.slot_id == "main"
            and "snapshot" in explicit_roms
            and any(candidate.slot_id == "snapshot" for candidate in spec.rom_slots)
        ):
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


def load_state_dump(path: str | Path) -> dict:
    dump_path = Path(path)
    payload = json.loads(dump_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"dump de estado inválido: {dump_path}")
    if "machine_id" not in payload or "state" not in payload:
        raise ValueError(f"dump de estado incompleto: {dump_path}")
    if not isinstance(payload["state"], dict):
        raise ValueError(f"dump de estado inválido: campo 'state' no es un objeto en {dump_path}")
    rom_paths = payload.get("rom_paths", {})
    if rom_paths is not None and not isinstance(rom_paths, dict):
        raise ValueError(f"dump de estado inválido: campo 'rom_paths' no es un objeto en {dump_path}")
    return payload


def instantiate_machine(
    machine_id: str,
    *,
    roms: dict[str, str | Path] | None = None,
    machine_options: dict[str, str] | None = None,
    display_profile: str = "default",
    state_dump: dict | None = None,
):
    """Build and reset a machine instance, resolving any needed ROM slots first.

    The reset happens here so every CLI entry point starts from a clean machine
    state regardless of the concrete class constructor details.
    """

    spec = get_machine_spec(machine_id)
    normalized_machine_options = _normalize_machine_options(spec.machine_id, machine_options)
    if state_dump is not None:
        dump_machine_id = str(state_dump.get("machine_id", ""))
        if dump_machine_id and dump_machine_id != spec.machine_id:
            raise ValueError(
                f"el dump de estado es para {dump_machine_id!r}, no para {spec.machine_id!r}"
            )
    explicit_rom_slots = set((roms or {}).keys())
    # Resolve early so the CLI fails with a user-facing error before reading
    # ROMs or constructing a machine with an unsupported monitor profile.
    get_display_profile(display_profile)
    dump_roms = {
        slot_id: Path(path)
        for slot_id, path in (state_dump.get("rom_paths", {}) if state_dump else {}).items()
    }
    combined_roms = dump_roms | {slot_id: Path(path) for slot_id, path in (roms or {}).items()}

    rom_paths = resolve_machine_rom_paths(machine_id, roms=combined_roms)
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

    if spec.machine_id in {"cpc464", "cpc664", "cpc6128"} and "os" in rom_bytes and len(rom_bytes["os"]) == 0x8000:
        if "basic" in explicit_rom_slots:
            raise ValueError("no se puede combinar una ROM CPC de 32K en 'os' con un slot 'basic' explícito")
        combined = rom_bytes.pop("os")
        rom_bytes["os"] = combined[:0x4000]
        rom_bytes["basic"] = combined[0x4000:]

    if spec.machine_id == "cpc464" and "basic" not in rom_bytes:
        warnings.warn(
            "CPC464 sin ROM alta de BASIC: el arranque puede acabar ejecutando RAM "
            "y mostrar pantalla corrupta. Proporciona una ROM combinada de 32 KB "
            "o una ROM BASIC compatible.",
            stacklevel=2,
        )

    if spec.machine_id == "msx":
        machine = _build_msx(rom_bytes, display_profile, normalized_machine_options)
    elif spec.machine_id in {"vic20", "vic20ntsc", "vic20pal"}:
        if vic20_diag_io_ram:
            rom_bytes = rom_bytes | {"__io2ram__": b"\x01"}
        machine = spec.factory(rom_bytes, display_profile)
    else:
        machine = spec.factory(rom_bytes, display_profile)
    # Expose the registry identity on the concrete instance so transport and
    # frontend layers can describe the machine without hardcoding families.
    machine.machine_id = spec.machine_id
    machine.display_name = spec.display_name
    machine.resolved_rom_paths = dict(rom_paths)
    machine.reset()
    if state_dump is not None:
        machine.write_state(state_dump["state"])
    return machine
