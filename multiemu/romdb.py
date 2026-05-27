from __future__ import annotations

import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path

from frontend.keymap import KEYMAP_SEARCH_DIRS


ROMDB_DIR_NAME = "romdb"
MSX_MAPPER_DB_FILENAME = "msx_mappers.json"


def get_romdb_search_dirs() -> tuple[Path, ...]:
    """Return ROM database directories next to the known keymap directories."""

    candidates: list[Path] = []
    for keymap_dir in KEYMAP_SEARCH_DIRS:
        candidates.append(keymap_dir.parent / ROMDB_DIR_NAME)

    candidates.extend(
        [
            Path(sys.prefix) / "share/multiemu" / ROMDB_DIR_NAME,
            Path("/usr/local/share/multiemu") / ROMDB_DIR_NAME,
            Path("/usr/share/multiemu") / ROMDB_DIR_NAME,
        ]
    )

    result: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            key = candidate.resolve()
        except OSError:
            key = candidate.absolute()
        if key not in seen:
            result.append(candidate)
            seen.add(key)
    return tuple(result)


@lru_cache(maxsize=None)
def _normalize_hash_key(raw_hash: object, *, source: Path) -> str:
    text = str(raw_hash).strip().lower()
    if ":" not in text:
        raise ValueError(f"ROM DB inválida: clave de hash sin algoritmo {raw_hash!r} en {source}")
    algorithm, digest = text.split(":", 1)
    algorithm = algorithm.strip()
    digest = digest.strip()
    if algorithm != "sha1":
        raise ValueError(f"ROM DB inválida: algoritmo de hash no soportado {algorithm!r} en {source}")
    if len(digest) != 40 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"ROM DB inválida: SHA1 no válido {raw_hash!r} en {source}")
    return f"{algorithm}:{digest}"


@lru_cache(maxsize=None)
def load_msx_mapper_db() -> dict[str, str]:
    """Load the built-in MSX mapper database as a hash-key->mapper-id mapping."""

    merged: dict[str, str] = {}
    for directory in get_romdb_search_dirs():
        path = directory / MSX_MAPPER_DB_FILENAME
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"ROM DB inválida: {path} debe ser un objeto JSON")
        for raw_hash, raw_mapper in payload.items():
            hash_key = _normalize_hash_key(raw_hash, source=path)
            mapper = str(raw_mapper).strip()
            if not mapper:
                raise ValueError(f"ROM DB inválida: mapper vacío para {hash_key} en {path}")
            merged[hash_key] = mapper
    return merged


def lookup_msx_mapper(cart_blob: bytes) -> str | None:
    if not cart_blob:
        return None
    sha1 = hashlib.sha1(cart_blob).hexdigest()
    return load_msx_mapper_db().get(f"sha1:{sha1}")
