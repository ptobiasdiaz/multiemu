from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pygame

from frontend.input_events import (
    JOYSTICK_DOWN,
    JOYSTICK_FIRE,
    JOYSTICK_FIRE_2,
    JOYSTICK_LEFT,
    JOYSTICK_RIGHT,
    JOYSTICK_START,
    JOYSTICK_UP,
)


KEYMAP_SEARCH_DIRS = (
    Path.cwd() / "keymaps",
    Path(__file__).resolve().parent.parent / "keymaps",
)
ALTGR_MOD_MASK = pygame.KMOD_MODE | pygame.KMOD_RALT

_JOYSTICK_NAME_TO_VALUE = {
    "JOYSTICK_UP": JOYSTICK_UP,
    "JOYSTICK_RIGHT": JOYSTICK_RIGHT,
    "JOYSTICK_DOWN": JOYSTICK_DOWN,
    "JOYSTICK_LEFT": JOYSTICK_LEFT,
    "JOYSTICK_FIRE": JOYSTICK_FIRE,
    "JOYSTICK_FIRE_2": JOYSTICK_FIRE_2,
    "JOYSTICK_START": JOYSTICK_START,
}
_JOYSTICK_VALUE_TO_NAME = {value: name for name, value in _JOYSTICK_NAME_TO_VALUE.items()}

_PYGAME_KEY_NAME_TO_VALUE = {
    name: getattr(pygame, name)
    for name in dir(pygame)
    if name.startswith("K_") and isinstance(getattr(pygame, name), int)
}
_PYGAME_KEY_VALUE_TO_NAME = {}
for _name, _value in _PYGAME_KEY_NAME_TO_VALUE.items():
    _PYGAME_KEY_VALUE_TO_NAME.setdefault(_value, _name)

_PYGAME_MOD_NAME_TO_VALUE = {
    name: getattr(pygame, name)
    for name in dir(pygame)
    if name.startswith("KMOD_") and isinstance(getattr(pygame, name), int)
}
_PYGAME_MOD_VALUE_TO_NAME = {}
for _name, _value in _PYGAME_MOD_NAME_TO_VALUE.items():
    _PYGAME_MOD_VALUE_TO_NAME.setdefault(_value, _name)


@dataclass(frozen=True)
class PygameInputMaps:
    keymap_name: str | None
    keymap: dict[int, tuple[int, int]]
    joystick_keymap: dict[int, tuple[int, int]]
    combo_keymap: dict[tuple[int, int], tuple[tuple[int, int], ...]]
    unicode_combo_keymap: dict[str, tuple[tuple[int, int], ...]]
    gamepad_map: dict[str, object]
    keymap_spec: dict | None = None


def _resolve_key_constant(value) -> int:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise ValueError(f"constante de tecla inválida: {value!r}")
    try:
        return int(_PYGAME_KEY_NAME_TO_VALUE[value])
    except KeyError as exc:
        raise ValueError(f"tecla pygame desconocida: {value!r}") from exc


def _resolve_mod_constant(value) -> int:
    if isinstance(value, int):
        return value
    if value in (None, ""):
        return 0
    if not isinstance(value, str):
        raise ValueError(f"constante de modificador inválida: {value!r}")
    try:
        return int(_PYGAME_MOD_NAME_TO_VALUE[value])
    except KeyError as exc:
        raise ValueError(f"modificador pygame desconocido: {value!r}") from exc


def _resolve_gamepad_value(value):
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(_JOYSTICK_NAME_TO_VALUE[value])
        except KeyError as exc:
            raise ValueError(f"control de gamepad desconocido: {value!r}") from exc
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (int(value[0]), int(value[1]))
    raise ValueError(f"valor de gamepad inválido: {value!r}")


def _parse_control(control) -> tuple[int, int]:
    if not isinstance(control, (list, tuple)) or len(control) != 2:
        raise ValueError(f"control inválido: {control!r}")
    return (int(control[0]), int(control[1]))


def _parse_controls(controls) -> tuple[tuple[int, int], ...]:
    return tuple(_parse_control(control) for control in controls)


def _merge_payloads(base: dict, overlay: dict) -> dict:
    merged = {
        "id": overlay.get("id", base.get("id")),
        "keys": dict(base.get("keys", {})),
        "joystick_keys": dict(base.get("joystick_keys", {})),
        "combos": list(base.get("combos", [])),
        "unicode_combos": dict(base.get("unicode_combos", {})),
        "gamepad": dict(base.get("gamepad", {})),
    }
    merged["keys"].update(overlay.get("keys", {}))
    merged["joystick_keys"].update(overlay.get("joystick_keys", {}))
    merged["unicode_combos"].update(overlay.get("unicode_combos", {}))
    merged["gamepad"].update(overlay.get("gamepad", {}))

    combo_map = {
        (item["key"], str(item.get("mod", 0))): dict(item)
        for item in merged["combos"]
    }
    for item in overlay.get("combos", []):
        combo_map[(item["key"], str(item.get("mod", 0)))] = dict(item)
    merged["combos"] = list(combo_map.values())
    return merged


def _resolve_spec_base(payload: dict, *, implicit_base: str | None, source_path: Path | None) -> dict | None:
    base_ref = payload.get("base")
    if base_ref is None:
        base_ref = implicit_base
    if base_ref is None:
        return None
    if source_path is not None:
        candidate = (source_path.parent / str(base_ref)).expanduser()
        if candidate.exists():
            return _load_keymap_payload_from_path(candidate)
    return _load_builtin_keymap_payload(str(base_ref))


def _load_keymap_payload_from_path(path: str | Path, *, implicit_base: str | None = None) -> dict:
    resolved_path = Path(path).expanduser().resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    base = _resolve_spec_base(payload, implicit_base=implicit_base, source_path=resolved_path)
    if base is None:
        payload.pop("base", None)
        return payload
    overlay = dict(payload)
    overlay.pop("base", None)
    return _merge_payloads(base, overlay)


@lru_cache(maxsize=None)
def _load_builtin_keymap_payload(keymap_id: str) -> dict:
    filename = f"{keymap_id}.json"
    for directory in KEYMAP_SEARCH_DIRS:
        path = directory / filename
        if path.is_file():
            return _load_keymap_payload_from_path(path)
    raise ValueError(f"keymap no soportado: {keymap_id}")


def _payload_to_maps(payload: dict) -> PygameInputMaps:
    keymap = {
        _resolve_key_constant(key): _parse_control(control)
        for key, control in payload.get("keys", {}).items()
    }
    joystick_keymap = {
        _resolve_key_constant(key): (int(control[0]), int(_resolve_gamepad_value(control[1])))
        for key, control in payload.get("joystick_keys", {}).items()
    }
    combo_keymap = {
        (
            _resolve_key_constant(item["key"]),
            _resolve_mod_constant(item.get("mod", 0)),
        ): _parse_controls(item.get("controls", ()))
        for item in payload.get("combos", [])
    }
    unicode_combo_keymap = {
        str(text): _parse_controls(controls)
        for text, controls in payload.get("unicode_combos", {}).items()
    }
    gamepad_map = {
        str(name): _resolve_gamepad_value(value)
        for name, value in payload.get("gamepad", {}).items()
    }
    return PygameInputMaps(
        keymap_name=payload.get("id"),
        keymap=keymap,
        joystick_keymap=joystick_keymap,
        combo_keymap=combo_keymap,
        unicode_combo_keymap=unicode_combo_keymap,
        gamepad_map=gamepad_map,
        keymap_spec=_serialize_maps(
            payload.get("id"),
            keymap,
            joystick_keymap,
            combo_keymap,
            unicode_combo_keymap,
            gamepad_map,
        ),
    )


@lru_cache(maxsize=None)
def _load_builtin_maps(keymap_id: str) -> PygameInputMaps:
    return _payload_to_maps(_load_builtin_keymap_payload(keymap_id))


def _serialize_maps(
    keymap_name: str | None,
    keymap: dict[int, tuple[int, int]],
    joystick_keymap: dict[int, tuple[int, int]],
    combo_keymap: dict[tuple[int, int], tuple[tuple[int, int], ...]],
    unicode_combo_keymap: dict[str, tuple[tuple[int, int], ...]],
    gamepad_map: dict[str, object],
) -> dict:
    return {
        "id": keymap_name,
        "keys": {
            _PYGAME_KEY_VALUE_TO_NAME.get(key, str(key)): [control[0], control[1]]
            for key, control in sorted(keymap.items())
        },
        "joystick_keys": {
            _PYGAME_KEY_VALUE_TO_NAME.get(key, str(key)): [
                control[0],
                _JOYSTICK_VALUE_TO_NAME.get(control[1], str(control[1])),
            ]
            for key, control in sorted(joystick_keymap.items())
        },
        "combos": [
            {
                "key": _PYGAME_KEY_VALUE_TO_NAME.get(key, str(key)),
                "mod": _PYGAME_MOD_VALUE_TO_NAME.get(mod, str(mod)),
                "controls": [[row, bit] for row, bit in controls],
            }
            for (key, mod), controls in sorted(combo_keymap.items())
        ],
        "unicode_combos": {
            text: [[row, bit] for row, bit in controls]
            for text, controls in sorted(unicode_combo_keymap.items())
        },
        "gamepad": {
            name: (
                _JOYSTICK_VALUE_TO_NAME[value]
                if isinstance(value, int) and value in _JOYSTICK_VALUE_TO_NAME
                else [int(value[0]), int(value[1])]
            )
            for name, value in sorted(gamepad_map.items())
        },
    }


def load_pygame_input_maps(
    keymap_name: str | None,
    *,
    gamepad_name: str | None = None,
    keymap_file: str | None = None,
    keymap_spec: dict | None = None,
) -> PygameInputMaps:
    if keymap_spec is not None:
        payload = dict(keymap_spec)
        if payload.get("base") is None and keymap_name:
            payload["base"] = keymap_name
        maps = _payload_to_maps(
            _merge_payloads(
                _resolve_spec_base(payload, implicit_base=None, source_path=None) or {},
                {k: v for k, v in payload.items() if k != "base"},
            )
        )
    elif keymap_file is not None:
        maps = _payload_to_maps(
            _load_keymap_payload_from_path(keymap_file, implicit_base=keymap_name)
        )
    else:
        effective_name = keymap_name or "spectrum"
        maps = _load_builtin_maps(effective_name)

    if keymap_name is None and keymap_spec is None and keymap_file is None:
        maps = PygameInputMaps(
            keymap_name=maps.keymap_name,
            keymap=maps.keymap,
            joystick_keymap=maps.joystick_keymap,
            combo_keymap=maps.combo_keymap,
            unicode_combo_keymap=maps.unicode_combo_keymap,
            gamepad_map={},
            keymap_spec=None,
        )

    if maps.gamepad_map:
        return maps
    if gamepad_name:
        gamepad_maps = _load_builtin_maps(gamepad_name).gamepad_map
        return PygameInputMaps(
            keymap_name=maps.keymap_name,
            keymap=maps.keymap,
            joystick_keymap=maps.joystick_keymap,
            combo_keymap=maps.combo_keymap,
            unicode_combo_keymap=maps.unicode_combo_keymap,
            gamepad_map=gamepad_maps,
            keymap_spec=_serialize_maps(
                maps.keymap_name,
                maps.keymap,
                maps.joystick_keymap,
                maps.combo_keymap,
                maps.unicode_combo_keymap,
                gamepad_maps,
            ) if maps.keymap_spec is not None else None,
        )
    return maps


def get_pygame_keymap(name: str | None):
    """Return the requested pygame keymap or the Spectrum default."""

    return load_pygame_input_maps(name).keymap


def get_pygame_combo_keymap(name: str | None):
    """Return host key+modifier combinations for the active machine."""

    return load_pygame_input_maps(name).combo_keymap


def get_pygame_unicode_combo_map(name: str | None):
    """Return text-driven combos for layouts needing symbol translation."""

    return load_pygame_input_maps(name).unicode_combo_keymap


def get_pygame_gamepad_map(name: str | None):
    """Return the requested pygame gamepad map or an empty mapping."""

    return load_pygame_input_maps(None, gamepad_name=name).gamepad_map


def resolve_pygame_key_controls(keymap, combo_keymap, unicode_combo_map, event):
    """Resolve one host keyboard event to one or more emulated key controls."""

    text = getattr(event, "unicode", "") or ""
    if text and text in unicode_combo_map:
        return tuple(unicode_combo_map[text])
    mod = int(getattr(event, "mod", 0))
    for (combo_key, required_mod), combo_controls in combo_keymap.items():
        if combo_key != event.key:
            continue
        if required_mod == 0:
            return tuple(combo_controls)
        if required_mod == pygame.KMOD_MODE and (mod & ALTGR_MOD_MASK):
            return tuple(combo_controls)
        if (mod & required_mod) == required_mod:
            return tuple(combo_controls)
    control = keymap.get(event.key)
    if control is None:
        return ()
    return (control,)


_SPECTRUM_MAPS = load_pygame_input_maps("spectrum", gamepad_name="spectrum")
SPECTRUM_PYGAME_KEYMAP = _SPECTRUM_MAPS.keymap
SPECTRUM_PYGAME_COMBO_KEYMAP = _SPECTRUM_MAPS.combo_keymap
SPECTRUM_PYGAME_UNICODE_COMBO_MAP = _SPECTRUM_MAPS.unicode_combo_keymap
SPECTRUM_PYGAME_GAMEPAD_MAP = _SPECTRUM_MAPS.gamepad_map

_SPECTRUM48K_MAPS = load_pygame_input_maps("spectrum48k", gamepad_name="spectrum")
_SPECTRUM128K_MAPS = load_pygame_input_maps("spectrum128k", gamepad_name="spectrum")

_CPC_MAPS = load_pygame_input_maps("cpc", gamepad_name="cpc")
CPC_PYGAME_KEYMAP = _CPC_MAPS.keymap
CPC_PYGAME_COMBO_KEYMAP = _CPC_MAPS.combo_keymap
CPC_PYGAME_GAMEPAD_MAP = _CPC_MAPS.gamepad_map

_GAMEBOY_MAPS = load_pygame_input_maps("gameboy", gamepad_name="gameboy")
GAMEBOY_PYGAME_KEYMAP = _GAMEBOY_MAPS.keymap
GAMEBOY_PYGAME_GAMEPAD_MAP = _GAMEBOY_MAPS.gamepad_map

_KIM1_MAPS = load_pygame_input_maps("kim1")
KIM1_PYGAME_KEYMAP = _KIM1_MAPS.keymap

_VIC20_MAPS = load_pygame_input_maps("vic20", gamepad_name="vic20")
VIC20_PYGAME_KEYMAP = _VIC20_MAPS.keymap
VIC20_PYGAME_GAMEPAD_MAP = _VIC20_MAPS.gamepad_map

PYGAME_KEYMAPS = {
    "spectrum": SPECTRUM_PYGAME_KEYMAP,
    "spectrum48k": _SPECTRUM48K_MAPS.keymap,
    "spectrum128k": _SPECTRUM128K_MAPS.keymap,
    "cpc": CPC_PYGAME_KEYMAP,
    "gameboy": GAMEBOY_PYGAME_KEYMAP,
    "kim1": KIM1_PYGAME_KEYMAP,
    "vic20": VIC20_PYGAME_KEYMAP,
}
