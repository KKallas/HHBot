#!/usr/bin/env python3
"""Add a single tag to the HHBot field.

Calls `GET /tag/add?x=&y=&value=`. Coordinates are in mm in the simulator's
world frame. The tag is auto-assigned the next free ArUco id from `DICT_4X4_50`.

Type: tool
Inputs: x (mm), y (mm), --value (default 1), --url
Output: prints the new tag id."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _http import get_json, sim_url  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Add a tag at (x, y) in mm")
    p.add_argument("x", type=float, help="X in mm")
    p.add_argument("y", type=float, help="Y in mm")
    p.add_argument("--value", type=int, default=1, help="Point value (default 1)")
    p.add_argument("--url", default=sim_url())
    args = p.parse_args(argv)
    resp = get_json(
        f"{args.url}/tag/add?x={args.x}&y={args.y}&value={args.value}"
    )
    print(f"Added tag id={resp.get('tag_id')} at ({args.x}, {args.y}) "
          f"value={args.value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
