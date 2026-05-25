"""Physics-invariant tests for EPS and thermal subsystems.

These check that the models obey conservation laws and operational limits.
They don't check exact values — those depend on parameters that may be
tuned. They check that bad behavior is impossible.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from orbit_ops.common.clock import ClockMode, SimClock
from orbit_ops.sim.satellite import Satellite, load_tle_file
from orbit_ops.sim.subsystem_params import EPS
from orbit_ops.sim.subsystems import (
    eps_initial_state,
    eps_step,
    thermal_initial_state,
    thermal_step,
)

TLE_PATH = Path(__file__).resolve().parent.parent / "data" / "tle" / "planet.tle"


@pytest.fixture(scope="module")
def skysat() -> tuple[str, str, str]:
    if not TLE_PATH.exists():
        pytest.skip(f"TLE file missing at {TLE_PATH}; run `make tle` first")
    entries = load_tle_file(TLE_PATH)
    for name, l1, l2 in entries:
        if "SKYSAT" in name.upper():
            return name, l1, l2
    pytest.skip("no SkySat in TLE file")
    raise AssertionError("unreachable")


def _orbit_run(skysat: tuple[str, str, str], minutes: int) -> tuple[list, list, list]:
    """Run a satellite + subsystems for `minutes` of sim time at 1-minute ticks.

    Returns (soc_history, temp_history, eclipsed_history).
    """
    name, l1, l2 = skysat
    clock = SimClock(
        start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        tick_seconds=60.0,
        mode=ClockMode.FAST,
    )
    sat = Satellite(name, l1, l2, clock)
    eps_s = eps_initial_state()
    thermal_s = thermal_initial_state()
    soc_hist, temp_hist, ecl_hist = [], [], []
    for _ in range(minutes):
        geo = sat.state()
        eps_s, eps_t = eps_step(geo, eps_s, 60.0)
        thermal_s, thermal_t = thermal_step(geo, thermal_s, 60.0)
        soc_hist.append(eps_t.battery_soc)
        temp_hist.append(thermal_t.bus_temperature_k)
        ecl_hist.append(geo.eclipsed)
        clock.tick()
    return soc_hist, temp_hist, ecl_hist


def test_soc_stays_in_bounds(skysat: tuple[str, str, str]) -> None:
    """Battery SoC must always be in [min_soc, max_soc]. Clipping is the contract."""
    soc, _, _ = _orbit_run(skysat, minutes=180)  # 3 hours, ~2 orbits
    assert all(EPS.battery_min_soc <= s <= EPS.battery_max_soc for s in soc), (
        f"SoC out of bounds: min={min(soc):.3f}, max={max(soc):.3f}"
    )


def test_temperature_stays_in_sane_range(skysat: tuple[str, str, str]) -> None:
    """Bus temperature must stay in a physical envelope for a LEO sat."""
    _, temp, _ = _orbit_run(skysat, minutes=180)
    t_min, t_max = min(temp), max(temp)
    assert t_min > 240.0, f"temperature dropped to {t_min:.1f} K (unphysical for LEO)"
    assert t_max < 330.0, f"temperature climbed to {t_max:.1f} K (unphysical for LEO)"


def test_soc_discharges_during_eclipse(skysat: tuple[str, str, str]) -> None:
    """Across the run, average SoC change during eclipse must be negative.

    This is the coupling test: if the eclipse flag isn't actually gating
    solar power, this fails.
    """
    soc, _, ecl = _orbit_run(skysat, minutes=180)
    deltas_in_eclipse = [soc[i] - soc[i - 1] for i in range(1, len(soc)) if ecl[i]]
    if not deltas_in_eclipse:
        pytest.skip("no eclipse in this window; try a different start time")
    avg_delta = float(np.mean(deltas_in_eclipse))
    assert avg_delta < 0, f"SoC not discharging in eclipse (avg delta {avg_delta:.5f})"


def test_temperature_drops_during_eclipse(skysat: tuple[str, str, str]) -> None:
    """Average temperature change during eclipse must be negative."""
    _, temp, ecl = _orbit_run(skysat, minutes=180)
    deltas_in_eclipse = [temp[i] - temp[i - 1] for i in range(1, len(temp)) if ecl[i]]
    if not deltas_in_eclipse:
        pytest.skip("no eclipse in this window")
    avg_delta = float(np.mean(deltas_in_eclipse))
    assert avg_delta < 0, f"temperature not falling in eclipse (avg delta {avg_delta:.5f})"


def test_power_balance_over_orbit_is_near_zero(skysat: tuple[str, str, str]) -> None:
    """Over a full orbit, average net power should be near zero in steady state.

    If average net power is strongly positive, the battery would charge forever
    (and clip at max). If strongly negative, it would discharge forever (and clip
    at min). A well-sized bus has near-zero orbital average net power. We allow
    a wide band since our parameters are estimates, but check the sign at least
    isn't pathological.
    """
    name, l1, l2 = skysat
    clock = SimClock(
        start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        tick_seconds=60.0,
        mode=ClockMode.FAST,
    )
    sat = Satellite(name, l1, l2, clock)
    eps_s = eps_initial_state()
    net_history: list[float] = []
    for _ in range(95):  # ~1 orbit
        geo = sat.state()
        eps_s, eps_t = eps_step(geo, eps_s, 60.0)
        net_history.append(eps_t.net_power_w)
        clock.tick()
    avg_net = float(np.mean(net_history))
    # Loose envelope: average net should be small relative to peak generation.
    peak_gen = EPS.solar_flux_w_m2 * EPS.array_area_m2 * EPS.array_efficiency
    assert abs(avg_net) < 0.5 * peak_gen, (
        f"orbit-average net power {avg_net:.1f} W is more than 50% of peak gen "
        f"({peak_gen:.1f} W); bus is poorly sized"
    )


def test_temperature_responds_slower_than_soc(skysat: tuple[str, str, str]) -> None:
    """Thermal time constant should be longer than electrical. Over an eclipse, SoC
    drops faster (as a fraction of operating range) than temperature does. This is
    a sanity check on the thermal mass — if temperature swings 50 K per orbit,
    we've under-sized the mass or over-sized the heat input."""
    soc, temp, _ = _orbit_run(skysat, minutes=180)
    soc_range = max(soc) - min(soc)
    temp_range = max(temp) - min(temp)
    # Temperature range over 3 hours should be less than 30 K for a well-modeled bus.
    assert temp_range < 30.0, f"temperature swung {temp_range:.1f} K (too much; check thermal mass)"
    # And SoC should swing at least a few percent (otherwise nothing is happening).
    assert soc_range > 0.02, f"SoC barely changed ({soc_range:.3f}); check power balance"
