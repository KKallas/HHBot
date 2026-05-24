"""Shared HTTP helpers for the game_master tool group.

Leading-underscore filename keeps it invisible to Nilsson's tool scanner —
it's a helper, not a runnable tool. Mirrors `tools/nilsson/_project_server.py`
in the Nilsson reference layout.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SESSION_FILE = Path(".nilsson/run_local.json")
DEFAULT_URL = "http://127.0.0.1:7700"


def sim_url() -> str:
    """Read the simulator URL from Nilsson's run_local marker; fall back to
    loopback if the marker is missing or malformed."""
    try:
        sess = json.loads(SESSION_FILE.read_text())
        url = sess.get("url")
        if isinstance(url, str) and url:
            return url
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_URL


def get_json(url: str, timeout: float = 3.0) -> dict:
    """GET a URL, decode JSON. Exit 1 with a clear stderr if the sim's down."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        print(f"sim unreachable at {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"sim returned non-JSON from {url}: {e}", file=sys.stderr)
        sys.exit(1)
