from __future__ import annotations

"""Command line entry point for MultiEmu.

The CLI stays intentionally thin: it parses user input and delegates machine
construction to ``machine_registry`` and runtime selection to
``runtime_registry``.
"""

import argparse
import sys

from multiemu.machine_registry import (
    get_default_rom_search_dirs,
    instantiate_machine,
    list_machine_specs,
)
from multiemu.runtime_registry import (
    CONNECT_FRONTENDS,
    CONNECT_TRANSPORTS,
    LOCAL_FRONTENDS,
    SERVER_TRANSPORTS,
    get_connect_client_class,
    get_runtime_spec,
    list_runtime_ids,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level parser and register all supported subcommands."""

    parser = argparse.ArgumentParser(prog="multiemu", description="MultiEmu command line interface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-machines", help="list supported machine definitions")
    list_parser.set_defaults(handler=_handle_list_machines)

    run_parser = subparsers.add_parser("run", help="run a machine locally with a selected frontend")
    _add_machine_argument(run_parser)
    _add_common_machine_options(run_parser)
    run_parser.add_argument(
        "--frontend",
        choices=list_runtime_ids(LOCAL_FRONTENDS),
        default="pygame",
        help="local frontend implementation",
    )
    run_parser.add_argument("--scale", type=int, default=2, help="window scale factor")
    run_parser.add_argument("--title", default=None, help="window title override")
    run_parser.set_defaults(handler=_handle_run)

    serve_parser = subparsers.add_parser("serve", help="serve a machine over a selected transport")
    _add_machine_argument(serve_parser)
    _add_common_machine_options(serve_parser)
    serve_parser.add_argument(
        "--transport",
        choices=list_runtime_ids(SERVER_TRANSPORTS),
        default="tcp",
        help="remote transport/server implementation",
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="bind host")
    serve_parser.add_argument("--port", type=int, default=8765, help="bind port")
    serve_parser.set_defaults(handler=_handle_serve)

    connect_parser = subparsers.add_parser("connect", help="connect to a remote session")
    connect_parser.add_argument(
        "--transport",
        choices=list_runtime_ids(CONNECT_TRANSPORTS),
        default="tcp",
        help="remote transport implementation",
    )
    connect_parser.add_argument(
        "--frontend",
        choices=list_runtime_ids(CONNECT_FRONTENDS),
        default="pygame",
        help="local presentation frontend",
    )
    connect_parser.add_argument("--host", default="127.0.0.1", help="server host")
    connect_parser.add_argument("--port", type=int, default=8765, help="server port")
    connect_parser.add_argument("--scale", type=int, default=2, help="window scale factor")
    connect_parser.add_argument("--title", default="MultiEmu TCP Client", help="window title")
    connect_parser.set_defaults(handler=_handle_connect)

    client_parser = subparsers.add_parser("client", help="alias for connect")
    for action in connect_parser._actions:
        if action.dest in {"help", "command"}:
            continue
        kwargs = {
            "dest": action.dest,
            "default": action.default,
            "help": action.help,
        }
        if getattr(action, "option_strings", None):
            if getattr(action, "type", None) is not None:
                kwargs["type"] = action.type
            if getattr(action, "choices", None) is not None:
                kwargs["choices"] = action.choices
            client_parser.add_argument(*action.option_strings, **kwargs)
    client_parser.set_defaults(handler=_handle_connect)
    return parser


def _add_machine_argument(parser: argparse.ArgumentParser) -> None:
    """Register the positional machine selector shared by local/server runs."""

    parser.add_argument("machine", help="machine id, e.g. spectrum48k")


def _add_common_machine_options(parser: argparse.ArgumentParser) -> None:
    """Register runtime options shared by local and TCP-backed execution."""

    parser.add_argument("--rom", default=None, help="path to ROM file")
    parser.add_argument("--fps", type=int, default=50, help="frame rate limit")
    parser.add_argument(
        "--audio-sample-rate",
        type=int,
        default=44100,
        help="audio sample rate",
    )
    parser.add_argument(
        "--audio-chunk-size",
        type=int,
        default=512,
        help="audio chunk size in samples",
    )


def _handle_list_machines(args) -> int:
    """Print supported machines in a script-friendly tab-separated format."""

    del args
    for spec in list_machine_specs():
        rom = spec.rom_filename or "-"
        print(f"{spec.machine_id}\t{spec.display_name}\trom: {rom}")
    return 0


def _handle_run(args) -> int:
    """Run a machine locally using the selected frontend implementation."""

    machine = instantiate_machine(
        args.machine,
        rom_path=args.rom,
    )
    title = args.title or f"MultiEmu - {args.machine}"
    frontend_cls = get_runtime_spec(LOCAL_FRONTENDS, args.frontend).factory()
    app = frontend_cls(
        machine,
        scale=args.scale,
        window_title=title,
        fps_limit=args.fps,
        audio_sample_rate=args.audio_sample_rate,
        audio_chunk_size=args.audio_chunk_size,
    )
    app.run()
    return 0


def _handle_serve(args) -> int:
    """Expose a machine over the selected remote transport implementation."""

    machine = instantiate_machine(
        args.machine,
        rom_path=args.rom,
    )
    transport_cls = get_runtime_spec(SERVER_TRANSPORTS, args.transport).factory()
    app = transport_cls(
        machine,
        host=args.host,
        port=args.port,
        fps_limit=args.fps,
        audio_sample_rate=args.audio_sample_rate,
        audio_chunk_size=args.audio_chunk_size,
    )
    try:
        app.run()
    except KeyboardInterrupt:
        # Keep Ctrl-C as a clean operational shutdown for long-running servers
        # instead of surfacing a traceback to the user.
        print("multiemu: servidor detenido por el usuario (Ctrl-C)", file=sys.stderr)
        return 130
    return 0


def _handle_connect(args) -> int:
    """Connect using a transport/frontend pair selected by the user."""

    client_cls = get_connect_client_class(args.transport, args.frontend)
    app = client_cls(
        host=args.host,
        port=args.port,
        scale=args.scale,
        window_title=args.title,
    )
    app.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the selected subcommand."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return args.handler(args)
    except FileNotFoundError as exc:
        search_dirs = ", ".join(str(path) for path in get_default_rom_search_dirs())
        parser.exit(
            2,
            f"multiemu: error: {exc}\n"
            f"multiemu: ROM search path: {search_dirs}\n",
        )
    except ValueError as exc:
        parser.exit(2, f"multiemu: error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
