"""Plot the observable signature of each fault type.

Produces docs/figures/fault_signatures.png, a 3-row figure showing one
SkySat's telemetry under each fault type vs a nominal sat for comparison.

Output: docs/figures/fault_signatures.png
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
from orbit_ops.sim.constellation import Constellation  # noqa: E402
from orbit_ops.sim.faults import FaultRegistry, FaultSpec, FaultType  # noqa: E402
from orbit_ops.sim.satellite import load_tle_file  # noqa: E402

TLE_PATH = REPO / "data" / "tle" / "planet.tle"
OUT_PATH = REPO / "docs" / "figures" / "fault_signatures.png"


def run_one_sat(
    name: str, l1: str, l2: str, faults: FaultRegistry, hours: int = 6
) -> dict[str, np.ndarray]:
    """Run a single satellite under given faults, return time-series arrays."""
    minutes = hours * 60
    clock = SimClock(
        start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        tick_seconds=60.0,
        mode=ClockMode.FAST,
    )
    con = Constellation([(name, l1, l2)], clock)

    soc = np.zeros(minutes)
    temp = np.zeros(minutes)
    times = np.arange(minutes)

    for i in range(minutes):
        sim_time_before = con.now
        results = con.tick(dt_s=60.0)
        tr = results[0]
        tr = faults.apply(name, sim_time_before, tr)
        soc[i] = tr.eps.battery_soc
        temp[i] = tr.thermal.bus_temperature_c

    return {"minutes": times, "soc": soc, "temp_c": temp}


def main() -> int:
    if not TLE_PATH.exists():
        print(f"TLE file missing at {TLE_PATH}; run `make tle` first", file=sys.stderr)
        return 1

    entries = load_tle_file(TLE_PATH)
    skysats = [(n, l1, l2) for (n, l1, l2) in entries if "SKYSAT" in n.upper()]
    if len(skysats) < 1:
        print("Need at least one SkySat in the TLE file", file=sys.stderr)
        return 1
    name, l1, l2 = skysats[0]
    start = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)

    nominal_reg = FaultRegistry()
    fade_reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id=name, fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso=start.isoformat(),
            params={"fade_rate_per_day": 1.0, "floor": 0.5},
        ),
    ])
    stuck_reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id=name, fault_type=FaultType.STUCK_TEMPERATURE_SENSOR,
            start_iso=start.replace(hour=1).isoformat(),
        ),
    ])
    runaway_reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id=name, fault_type=FaultType.THERMAL_RUNAWAY,
            start_iso=start.replace(hour=1).isoformat(),
            params={"rate_k_per_hour": 4.0, "cap_k": 30.0},
        ),
    ])

    nominal = run_one_sat(name, l1, l2, nominal_reg, hours=6)
    fade = run_one_sat(name, l1, l2, fade_reg, hours=6)
    stuck = run_one_sat(name, l1, l2, stuck_reg, hours=6)
    runaway = run_one_sat(name, l1, l2, runaway_reg, hours=6)

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    fig.suptitle(f"{name} -- Fault signatures vs nominal (6 sim-hours)", fontsize=12)

    # Row 1: capacity fade in SoC
    ax = axes[0]
    ax.plot(nominal["minutes"], nominal["soc"], color="tab:blue", lw=1.2, label="Nominal")
    ax.plot(fade["minutes"], fade["soc"], color="tab:red", lw=1.5, label="Capacity fade (1.0/day rate)")
    ax.set_ylabel("Battery SoC")
    ax.set_title("Battery capacity fade -- SoC ceiling drops over time")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")

    # Row 2: stuck sensor in temperature
    ax = axes[1]
    ax.plot(nominal["minutes"], nominal["temp_c"], color="tab:blue", lw=1.2, label="Nominal")
    ax.plot(stuck["minutes"], stuck["temp_c"], color="tab:red", lw=1.5, label="Stuck @ t=60min")
    ax.axvline(60, color="black", linestyle=":", alpha=0.5)
    ax.set_ylabel("Bus temperature (C)")
    ax.set_title("Stuck temperature sensor -- value held while underlying physics keeps moving")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")

    # Row 3: thermal runaway
    ax = axes[2]
    ax.plot(nominal["minutes"], nominal["temp_c"], color="tab:blue", lw=1.2, label="Nominal")
    ax.plot(runaway["minutes"], runaway["temp_c"], color="tab:red", lw=1.5,
            label="Runaway from t=60min (+4 K/hr, cap +30 K)")
    ax.axvline(60, color="black", linestyle=":", alpha=0.5)
    ax.set_ylabel("Bus temperature (C)")
    ax.set_xlabel("Sim time (minutes)")
    ax.set_title("Thermal runaway -- monotonic bias growth past operational envelope")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")

    fig.tight_layout()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PATH, dpi=120, bbox_inches="tight")
    print(f"Wrote {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
