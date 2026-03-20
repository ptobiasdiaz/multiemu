from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

REGISTER_NAMES = {
    0xFF40: "LCDC",
    0xFF41: "STAT",
    0xFF42: "SCY",
    0xFF43: "SCX",
    0xFF44: "LY",
    0xFF45: "LYC",
    0xFF46: "DMA",
    0xFF47: "BGP",
    0xFF48: "OBP0",
    0xFF49: "OBP1",
    0xFF4A: "WY",
    0xFF4B: "WX",
}


def analyze_rom(data: bytes) -> dict:
    reads = Counter()
    writes = Counter()
    dynamic_ff00_reads = 0
    dynamic_ff00_writes = 0

    index = 0
    size = len(data)
    while index < size:
        opcode = data[index]

        if opcode in {0xE0, 0xF0} and index + 1 < size:
            addr = 0xFF00 | data[index + 1]
            name = REGISTER_NAMES.get(addr)
            if name is not None:
                if opcode == 0xE0:
                    writes[name] += 1
                else:
                    reads[name] += 1
            index += 2
            continue

        if opcode in {0xEA, 0xFA} and index + 2 < size:
            addr = data[index + 1] | (data[index + 2] << 8)
            name = REGISTER_NAMES.get(addr)
            if name is not None:
                if opcode == 0xEA:
                    writes[name] += 1
                else:
                    reads[name] += 1
            index += 3
            continue

        if opcode == 0xE2:
            dynamic_ff00_writes += 1
        elif opcode == 0xF2:
            dynamic_ff00_reads += 1

        index += 1

    tags = []
    if any(writes[name] for name in ("SCX", "SCY", "WX", "WY")):
        tags.append("scroll_window_writes")
    if writes["LCDC"] > 0:
        tags.append("lcdc_writes")
    if writes["DMA"] > 0:
        tags.append("dma_writes")
    if writes["STAT"] > 0 or reads["STAT"] > 0 or reads["LY"] > 0 or writes["LYC"] > 0:
        tags.append("stat_ly_timing")
    if any(writes[name] for name in ("BGP", "OBP0", "OBP1")):
        tags.append("palette_writes")
    if dynamic_ff00_reads or dynamic_ff00_writes:
        tags.append("dynamic_ff00_access")

    score = 0
    score += 2 * sum(writes[name] > 0 for name in ("SCX", "SCY", "WX", "WY"))
    score += 3 if writes["LCDC"] > 0 else 0
    score += 3 if writes["DMA"] > 0 else 0
    score += 2 if (writes["STAT"] > 0 or reads["STAT"] > 0 or reads["LY"] > 0 or writes["LYC"] > 0) else 0
    score += 1 if any(writes[name] > 0 for name in ("BGP", "OBP0", "OBP1")) else 0
    score += 1 if (dynamic_ff00_reads or dynamic_ff00_writes) else 0

    return {
        "register_reads": {name: reads[name] for name in REGISTER_NAMES.values() if reads[name] > 0},
        "register_writes": {name: writes[name] for name in REGISTER_NAMES.values() if writes[name] > 0},
        "dynamic_ff00_reads": dynamic_ff00_reads,
        "dynamic_ff00_writes": dynamic_ff00_writes,
        "timing_score": score,
        "tags": tags,
        "ppu_timing_candidate": score >= 4,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add static PPU-oriented analysis metadata to a Game Boy ROM catalog"
    )
    parser.add_argument("catalog", help="path to the input catalog JSON file")
    parser.add_argument(
        "--output",
        help="path to write the updated catalog; defaults to overwriting the input file",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    catalog_path = Path(args.catalog)
    output_path = Path(args.output) if args.output else catalog_path

    with catalog_path.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)

    entries = catalog.get("entries", [])
    tag_summary = Counter()
    candidate_count = 0
    analyzed_count = 0
    missing_count = 0

    for entry in entries:
        source_path = Path(entry["source_path"])
        if not source_path.exists():
            entry["ppu_static_analysis"] = {
                "missing_source": True,
                "register_reads": {},
                "register_writes": {},
                "dynamic_ff00_reads": 0,
                "dynamic_ff00_writes": 0,
                "timing_score": 0,
                "tags": [],
                "ppu_timing_candidate": False,
            }
            missing_count += 1
            continue

        analysis = analyze_rom(source_path.read_bytes())
        entry["ppu_static_analysis"] = analysis
        analyzed_count += 1
        if analysis["ppu_timing_candidate"]:
            candidate_count += 1
        tag_summary.update(analysis["tags"])

    catalog["ppu_static_analysis_generated_on"] = str(date.today())
    catalog["ppu_static_analysis_summary"] = {
        "analyzed_entries": analyzed_count,
        "missing_sources": missing_count,
        "ppu_timing_candidates": candidate_count,
        "tag_counts": dict(sorted(tag_summary.items())),
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(catalog, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
