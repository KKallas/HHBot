#!/usr/bin/env python3
"""End the current HHBot round.

Calls `GET /game/end`. Stops the timer but leaves the field, tag positions,
and receptacle scores intact so they can be screenshotted / archived before
`/game/reset` clears them.

Type: tool
Inputs: --url (default: from .nilsson/run_local.json)
Output: prints the new game state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _http import get_json, sim_url  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="End the current HHBot round")
    p.add_argument("--url", default=sim_url())
    args = p.parse_args(argv)
    resp = get_json(f"{args.url}/game/end")
    print(f"Game ended — state: {resp.get('state')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
