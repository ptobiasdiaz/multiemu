from __future__ import annotations

"""Runtime registry for CLI execution modes.

The CLI keeps frontend and transport selection declarative so future runtime
combinations can be added without rewriting command handlers.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    """Declarative binding between a CLI selector and a runtime factory."""

    runtime_id: str
    description: str
    factory: Callable[[], type]


def _load_pygame_frontend():
    from frontend.pygame_frontend import PygameFrontend

    return PygameFrontend


def _load_tcp_frontend():
    # TCP is currently the only remote server transport, but the CLI resolves
    # it through this registry so future protocols can plug in beside it.
    from frontend.tcp_frontend import TcpFrontend

    return TcpFrontend


def _load_tcp_pygame_client():
    from frontend.tcp_pygame_client import TcpPygameClient

    return TcpPygameClient


LOCAL_FRONTENDS: dict[str, RuntimeSpec] = {
    "pygame": RuntimeSpec(
        runtime_id="pygame",
        description="local pygame window and audio output",
        factory=_load_pygame_frontend,
    ),
}

SERVER_TRANSPORTS: dict[str, RuntimeSpec] = {
    "tcp": RuntimeSpec(
        runtime_id="tcp",
        description="TCP video/audio/input streaming server",
        factory=_load_tcp_frontend,
    ),
}

CONNECT_TRANSPORTS: dict[str, RuntimeSpec] = {
    "tcp": RuntimeSpec(
        runtime_id="tcp",
        description="TCP connection to a remote emulator session",
        factory=lambda: None,
    ),
}

CONNECT_FRONTENDS: dict[str, RuntimeSpec] = {
    "pygame": RuntimeSpec(
        runtime_id="pygame",
        description="pygame window and audio output for remote sessions",
        factory=lambda: None,
    ),
}


def list_runtime_ids(registry: dict[str, RuntimeSpec]) -> list[str]:
    """Return supported runtime ids in stable order for parser choices."""

    return sorted(registry)


def get_runtime_spec(registry: dict[str, RuntimeSpec], runtime_id: str) -> RuntimeSpec:
    """Resolve a runtime id or raise a user-facing error with valid choices."""

    try:
        return registry[runtime_id]
    except KeyError as exc:
        supported = ", ".join(sorted(registry))
        raise ValueError(f"runtime no soportado: {runtime_id!r}. Disponibles: {supported}") from exc


def get_connect_client_class(transport_id: str, frontend_id: str):
    """Resolve a connect transport/frontend pair to the current client class.

    The pair is kept explicit even though only one combination exists today, so
    new transports or presentation frontends can be added independently later.
    """

    get_runtime_spec(CONNECT_TRANSPORTS, transport_id)
    get_runtime_spec(CONNECT_FRONTENDS, frontend_id)

    if transport_id == "tcp" and frontend_id == "pygame":
        return _load_tcp_pygame_client()

    raise ValueError(
        f"combinación connect no soportada: transport={transport_id!r}, frontend={frontend_id!r}"
    )
