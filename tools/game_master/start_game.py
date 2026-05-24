#!/usr/bin/env python3
"""Start the HHBot game timer (or resume if paused).

Calls `GET /game/start` on the simulator. Fresh start from idle/ended
resets `time_left`; from paused it resumes without resetting the clock.

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
    p = argparse.ArgumentParser(description="Start the HHBot game timer")
    p.add_argument("--url", default=sim_url(),
                   help="Simulator URL (default: from .nilsson/run_local.json)")
    args = p.parse_args(argv)
    resp = get_json(f"{args.url}/game/start")
    print(f"Game started — state: {resp.get('state')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
