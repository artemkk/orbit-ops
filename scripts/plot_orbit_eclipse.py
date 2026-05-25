"""Plot battery SoC and temperature over ~3 orbits of one SkySat.

The committed image is the visual proof that the EPS and thermal models
respond to eclipse. Eclipse regions are shaded; SoC and temperature should
visibly dip when the satellite is in Earth's shadow.

Output: docs/figures/orbit_eclipse.png
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from orbit_ops.common.clock import ClockMode, SimClock  # noqa: E402
from orbit_ops.sim.satellite import Satellite, load_tle_file  # noqa: E402
from orbit_ops.sim.subsystems import (  # noqa: E402
    eps_initial_state,
    eps_step,
    thermal_initial_state,
    thermal_step,
)

TLE_PATH = REPO / "data" / "tle" / "planet.tle"
OUT_PATH = REPO / "docs" / "figures" / "orbit_eclipse.png"


def main() -> int:
    if not TLE_PATH.exists():
        print(f"TLE file missing at {TLE_PATH}; run `make tle` first", file=sys.stderr)
        return 1

    entries = load_tle_file(TLE_PATH)
    skysat = next(((n, l1, l2) for (n, l1, l2) in entries if "SKYSAT" in n.upper()), None)
    if skysat is None:
        print("No SkySat in TLE file", file=sys.stderr)
        return 1
    name, l1, l2 = skysat

    minutes = 270  # ~3 orbits
    clock = SimClock(
        start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        tick_seconds=60.0,
        mode=ClockMode.FAST,
    )
    sat = Satellite(name, l1, l2, clock)
    eps_s = eps_initial_state()
    thermal_s = thermal_initial_state()

    t_min = np.arange(minutes)
    soc = np.zeros(minutes)
    temp_c = np.zeros(minutes)
    eclipsed = np.zeros(minutes, dtype=bool)

    for i in range(minutes):
        geo = sat.state()
        eps_s, eps_t = eps_step(geo, eps_s, 60.0)
        thermal_s, thermal_t = thermal_step(geo, thermal_s, 60.0)
        soc[i] = eps_t.battery_soc
        temp_c[i] = thermal_t.bus_temperature_c
        eclipsed[i] = geo.eclipsed
        clock.tick()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    fig.suptitle(f"{name} — EPS + Thermal response over ~3 orbits", fontsize=12)

    # SoC
    ax1.plot(t_min, soc * 100, color="tab:blue", lw=1.5, label="Battery SoC")
    ax1.set_ylabel("Battery SoC (%)")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right")

    # Temperature
    ax2.plot(t_min, temp_c, color="tab:red", lw=1.5, label="Bus temperature")
    ax2.set_ylabel("Bus temperature (°C)")
    ax2.set_xlabel("Sim time (minutes)")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right")

    # Shade eclipse regions on both axes.
    in_ecl = False
    start = 0
    for i in range(minutes):
        if eclipsed[i] and not in_ecl:
            start = i
            in_ecl = True
        elif not eclipsed[i] and in_ecl:
            ax1.axvspan(start, i, alpha=0.15, color="gray", lw=0)
            ax2.axvspan(start, i, alpha=0.15, color="gray", lw=0)
            in_ecl = False
    if in_ecl:
        ax1.axvspan(start, minutes - 1, alpha=0.15, color="gray", lw=0)
        ax2.axvspan(start, minutes - 1, alpha=0.15, color="gray", lw=0)

    # Add a single legend entry for the shading.
    from matplotlib.patches import Patch
    eclipse_patch = Patch(facecolor="gray", alpha=0.15, label="Eclipse")
    ax1.legend(handles=[*ax1.get_legend().legend_handles, eclipse_patch], loc="upper right")
    ax2.legend(handles=[*ax2.get_legend().legend_handles, eclipse_patch], loc="upper right")

    fig.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=120, bbox_inches="tight")
    print(f"Wrote {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
