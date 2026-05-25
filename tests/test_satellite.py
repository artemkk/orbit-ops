"""Physics-grounded tests for the Satellite class.

We're not testing Skyfield (it's well-tested upstream). We're testing that
our Satellite + SatelliteState contract produces values that satisfy known
physical constraints. If these fail, something is wrong with frame
conventions, units, or our interpretation of Skyfield's API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from orbit_ops.common.clock import ClockMode, SimClock
from orbit_ops.sim.satellite import Satellite, load_tle_file

TLE_PATH = Path(__file__).resolve().parent.parent / "data" / "tle" / "planet.tle"


@pytest.fixture(scope="module")
def tle_entries() -> list[tuple[str, str, str]]:
    if not TLE_PATH.exists():
        pytest.skip(f"TLE file missing at {TLE_PATH}; run `make tle` first")
    entries = load_tle_file(TLE_PATH)
    if not entries:
        pytest.skip("TLE file has no satellites")
    return entries


@pytest.fixture
def one_sat(tle_entries: list[tuple[str, str, str]]) -> tuple[str, str, str]:
    # Prefer a SkySat for the LEO/sun-sync invariants below.
    for name, l1, l2 in tle_entries:
        if "SKYSAT" in name.upper():
            return name, l1, l2
    # Fall back to first entry if no SkySat in the file (shouldn't happen for the planet group).
    return tle_entries[0]


def _fresh_clock() -> SimClock:
    # Use a recent, deterministic UTC start. Tests must not depend on wall time.
    return SimClock(start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC), tick_seconds=60.0, mode=ClockMode.FAST)


def test_state_returns_well_formed_dataclass(one_sat: tuple[str, str, str]) -> None:
    name, l1, l2 = one_sat
    sat = Satellite(name, l1, l2, _fresh_clock())
    s = sat.state()
    assert s.sat_id == name
    assert s.sim_time.tzinfo is not None
    assert len(s.position_eci_km) == 3
    assert len(s.velocity_eci_km_s) == 3
    assert len(s.sun_vector_eci) == 3
    assert isinstance(s.eclipsed, bool)


def test_leo_position_magnitude(one_sat: tuple[str, str, str]) -> None:
    """LEO sats orbit at ~500-600 km altitude; position magnitude ~6800-7000 km from Earth center."""
    name, l1, l2 = one_sat
    sat = Satellite(name, l1, l2, _fresh_clock())
    s = sat.state()
    r = np.linalg.norm(s.position_eci_km)
    assert 6700.0 < r < 7200.0, f"position magnitude {r:.1f} km outside LEO band"


def test_altitude_is_leo(one_sat: tuple[str, str, str]) -> None:
    """Sub-satellite altitude should be in LEO band (300-800 km for SkySats)."""
    name, l1, l2 = one_sat
    sat = Satellite(name, l1, l2, _fresh_clock())
    s = sat.state()
    assert 300.0 < s.altitude_km < 800.0, f"altitude {s.altitude_km:.1f} km outside LEO band"


def test_sun_vector_is_unit_length(one_sat: tuple[str, str, str]) -> None:
    name, l1, l2 = one_sat
    sat = Satellite(name, l1, l2, _fresh_clock())
    s = sat.state()
    mag = float(np.linalg.norm(s.sun_vector_eci))
    assert abs(mag - 1.0) < 1e-6, f"sun vector magnitude {mag} not unit length"


def test_sub_satellite_latitude_within_inclination(one_sat: tuple[str, str, str]) -> None:
    """SkySats are sun-synchronous (~97.5° inclination). Sub-sat latitude must stay within ±97.5°,
    and over many samples should range widely (not stuck at 0 or near the poles)."""
    name, l1, l2 = one_sat
    clock = _fresh_clock()
    sat = Satellite(name, l1, l2, clock)
    lats: list[float] = []
    for _ in range(120):  # 120 ticks * 60s = 2 hours, ~1.25 orbits
        s = sat.state()
        lats.append(s.latitude_deg)
        clock.tick()
    lats_arr = np.asarray(lats)
    assert np.all(np.abs(lats_arr) <= 97.5), f"latitude outside inclination band: max={np.max(np.abs(lats_arr))}"
    # Over >1 orbit, latitude should swing meaningfully. If it's stuck near 0, something is wrong.
    assert (np.max(lats_arr) - np.min(lats_arr)) > 90.0, (
        f"latitude range {np.max(lats_arr) - np.min(lats_arr):.1f}° too small for >1 orbit"
    )


def test_eclipse_fraction_over_orbit_is_reasonable(one_sat: tuple[str, str, str]) -> None:
    """For a sun-sync LEO orbit, eclipse fraction is typically 0% (full-sun terminator orbit)
    to ~38% (worst case). 0-45% is the sane envelope. If we see 0 or 1 always, eclipse logic
    is broken."""
    name, l1, l2 = one_sat
    clock = _fresh_clock()
    sat = Satellite(name, l1, l2, clock)
    eclipsed_count = 0
    n_samples = 200  # ~3.3 hours at 60s ticks
    for _ in range(n_samples):
        if sat.state().eclipsed:
            eclipsed_count += 1
        clock.tick()
    fraction = eclipsed_count / n_samples
    assert 0.0 <= fraction <= 0.45, f"eclipse fraction {fraction:.2%} outside sane envelope"


def test_state_tracks_clock(one_sat: tuple[str, str, str]) -> None:
    """state().sim_time must equal clock.now at the moment of the call."""
    name, l1, l2 = one_sat
    clock = _fresh_clock()
    sat = Satellite(name, l1, l2, clock)

    s0 = sat.state()
    assert s0.sim_time == clock.now

    for _ in range(5):
        clock.tick()
    s1 = sat.state()
    assert s1.sim_time == clock.now
    assert s1.sim_time > s0.sim_time
