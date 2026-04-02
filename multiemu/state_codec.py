from __future__ import annotations

from array import array


def read_state_fields(
    obj,
    *,
    scalar_fields: tuple[str, ...] = (),
    byte_fields: tuple[str, ...] = (),
    array_fields: tuple[str, ...] = (),
    meta: dict | None = None,
) -> dict:
    state: dict = {}
    if meta:
        state["__meta__"] = dict(meta)
    for field in scalar_fields:
        state[field] = getattr(obj, field)
    for field in byte_fields:
        state[field] = list(getattr(obj, field))
    for field in array_fields:
        state[field] = list(getattr(obj, field))
    return state


def write_state_fields(
    obj,
    state: dict,
    *,
    scalar_fields: tuple[str, ...] = (),
    byte_fields: tuple[str, ...] = (),
    array_fields: tuple[str, ...] = (),
) -> None:
    for field in scalar_fields:
        if field in state:
            setattr(obj, field, state[field])
    for field in byte_fields:
        if field in state:
            getattr(obj, field)[:] = bytes(int(v) & 0xFF for v in state[field])
    for field in array_fields:
        if field in state:
            current = getattr(obj, field)
            current[:] = array(current.typecode, (int(v) for v in state[field]))
