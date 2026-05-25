"""Fetch current TLEs from Celestrak for the constellation we simulate.

We target Planet Labs SkySat: small Earth-observation LEO sats in
sun-synchronous orbit. Similar bus class to York's S-class smallsats,
constellation size ~20 birds -- close to our 10-20 target.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

CELESTRAK_SKYSAT = "https://celestrak.org/NORAD/elements/gp.php?GROUP=planet&FORMAT=tle"

OUT = Path(__file__).resolve().parent.parent / "data" / "tle" / "planet.tle"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching TLEs from {CELESTRAK_SKYSAT}", file=sys.stderr)
    with urllib.request.urlopen(CELESTRAK_SKYSAT, timeout=30) as resp:
        data = resp.read()
    OUT.write_bytes(data)
    n_lines = data.decode().count("\n")
    print(f"Wrote {OUT} ({n_lines} lines, ~{n_lines // 3} satellites)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
