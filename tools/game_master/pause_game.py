#!/usr/bin/env python3
"""Pause the HHBot game timer.

Calls `GET /game/pause`. Freezes `time_left` but leaves robot motion and
the field untouched — use `start_game` to resume. No-op unless the game is
currently running.

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
    p = argparse.ArgumentParser(description="Pause the HHBot game timer")
    p.add_argument("--url", default=sim_url())
    args = p.parse_args(argv)
    resp = get_json(f"{args.url}/game/pause")
    print(f"Game paused — state: {resp.get('state')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
