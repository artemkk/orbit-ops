"""Fetch current TLEs from Celestrak for the constellation we'll simulate.

Day 2 chooses which catalog (e.g., Planet SkySat, Spire LEMUR) to base the
sim on. For now this fetches the Active Satellites set as a placeholder so
the script is exercised by `make tle`.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

CELESTRAK_ACTIVE = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"

OUT = Path(__file__).resolve().parent.parent / "data" / "tle" / "active.tle"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching TLEs from {CELESTRAK_ACTIVE}", file=sys.stderr)
    with urllib.request.urlopen(CELESTRAK_ACTIVE, timeout=30) as resp:
        data = resp.read()
    OUT.write_bytes(data)
    n_lines = data.decode().count("\n")
    print(f"Wrote {OUT} ({n_lines} lines, ~{n_lines // 3} satellites)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
