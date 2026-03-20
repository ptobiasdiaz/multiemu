from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import time
from pathlib import Path

from machines.gameboy import DMG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile Game Boy frame execution on a local ROM")
    parser.add_argument("rom", help="path to a local .gb/.gbc ROM")
    parser.add_argument("--frames", type=int, default=120, help="number of frames to execute")
    parser.add_argument("--warmup", type=int, default=5, help="frames to execute before profiling")
    parser.add_argument("--limit", type=int, default=30, help="number of functions to show")
    parser.add_argument(
        "--sort",
        default="cumulative",
        choices=("cumulative", "tottime", "time", "calls"),
        help="pstats sort key",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rom_path = Path(args.rom)
    rom_data = rom_path.read_bytes()
    machine = DMG(rom_data)
    machine.reset()

    for _ in range(max(0, args.warmup)):
        machine.run_frame()

    profiler = cProfile.Profile()
    wall_start = time.perf_counter()
    profiler.enable()
    for _ in range(max(0, args.frames)):
        machine.run_frame()
    profiler.disable()
    wall_elapsed = time.perf_counter() - wall_start

    stats_stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stats_stream).strip_dirs().sort_stats(args.sort)
    stats.print_stats(args.limit)

    print(f"ROM: {rom_path}")
    print(f"Frames profiled: {args.frames}")
    print(f"Warmup frames: {args.warmup}")
    print(f"Wall time: {wall_elapsed:.6f}s")
    if args.frames > 0:
        print(f"Average wall/frame: {wall_elapsed / args.frames:.6f}s")
        print(f"Approx FPS (uncapped): {args.frames / wall_elapsed:.2f}")
    print()
    print(stats_stream.getvalue().rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
