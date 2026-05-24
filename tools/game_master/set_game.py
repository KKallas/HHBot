#!/usr/bin/env python3
"""Set up a fresh HHBot match.

Calls `/game/reset` to clear the field (tags, receptacle scores, robot
positions), then places a balanced starting layout: 6 regular 1-point tags
across the overlap zone plus 1 featured 10-point tag in the centre. All
positions are within both robots' reach.

Type: tool
Inputs: --url, --no-reset (skip the clear if you only want to re-place tags)
Output: prints the placed tag count."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _http import get_json, sim_url  # noqa: E402


# Positions chosen to sit in the overlap zone (both robots reach each point),
# clear of the two receptacle footprints. Field is 700 × 394 mm; bases at
# (100, 197) and (600, 197), reach 400 mm.
LAYOUT = [
    # (x, y, value)
    (250, 100, 1),
    (350, 150, 1),
    (450, 200, 1),
    (300, 280, 1),
    (400, 300, 1),
    (500, 100, 1),
    (350, 197, 10),     # featured 10-pt in the geometric centre
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Reset + place a starting tag layout")
    p.add_argument("--url", default=sim_url())
    p.add_argument("--no-reset", action="store_true",
                   help="Skip /game/reset; add tags on top of the current state")
    args = p.parse_args(argv)

    if not args.no_reset:
        get_json(f"{args.url}/game/reset")
        print("Field reset.")

    for x, y, v in LAYOUT:
        resp = get_json(f"{args.url}/tag/add?x={x}&y={y}&value={v}")
        print(f"  tag id={resp.get('tag_id')} at ({x}, {y}) value={v}")

    print(f"Placed {len(LAYOUT)} tags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
