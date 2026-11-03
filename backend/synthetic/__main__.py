"""CLI generator data sintetis.

Contoh (dari folder backend):
    python -m synthetic --out synthetic-output --seed 42 --as-of 2026-11-06
"""

import argparse
import json
from datetime import date
from pathlib import Path

from synthetic.final_sources import write_final_sources
from synthetic.raw_sources import write_raw_sources
from synthetic.world import build_world


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m synthetic", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("synthetic-output"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 6))
    args = parser.parse_args(argv)

    world = build_world(args.seed, args.as_of)
    counts = write_final_sources(world, args.out / "final_sources")
    raw = write_raw_sources(world, args.out / "raw")
    manifest = {
        "seed": args.seed,
        "as_of": args.as_of.isoformat(),
        "final_sources": counts,
        "raw": raw,
        "scenario_notes": world.scenario_notes,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
