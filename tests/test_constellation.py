"""Tests for the Constellation class.

Unit tests; no broker required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orbit_ops.common.clock import ClockMode, SimClock
from orbit_ops.sim.constellation import Constellation

TLE_PATH = Path(__file__).resolve().parent.parent / "data" / "tle" / "planet.tle"


def _clock() -> SimClock:
    return SimClock(
        start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        tick_seconds=60.0,
        mode=ClockMode.FAST,
    )


def test_constellation_requires_at_least_one_tle() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Constellation([], _clock())


def test_constellation_filters_and_limits() -> None:
    if not TLE_PATH.exists():
        pytest.skip("no TLE file; run `make tle`")
    con = Constellation.from_tle_file(TLE_PATH, _clock(), name_filter="SKYSAT", limit=5)
    assert con.size == 5
    assert all("SKYSAT" in sid.upper() for sid in con.sat_ids)


def test_constellation_tick_returns_one_result_per_sat() -> None:
    if not TLE_PATH.exists():
        pytest.skip("no TLE file; run `make tle`")
    con = Constellation.from_tle_file(TLE_PATH, _clock(), name_filter="SKYSAT", limit=3)
    results = con.tick(dt_s=60.0)
    assert len(results) == con.size
    # Every result should have plausible values from the subsystem models.
    for r in results:
        assert 0.0 <= r.eps.battery_soc <= 1.0
        assert 200.0 < r.thermal.bus_temperature_k < 350.0


def test_constellation_advances_clock() -> None:
    if not TLE_PATH.exists():
        pytest.skip("no TLE file; run `make tle`")
    clock = _clock()
    con = Constellation.from_tle_file(TLE_PATH, clock, name_filter="SKYSAT", limit=2)
    start = clock.now
    con.tick(dt_s=60.0)
    assert clock.now > start
