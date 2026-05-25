"""Tests for SimClock.

The TODO test at the bottom is intentionally failing. It documents the day-1
goal: flip it to passing by implementing REALTIME mode.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from orbit_ops.common.clock import ClockMode, SimClock


def test_clock_requires_tz_aware_start() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SimClock(start=datetime(2026, 1, 1))


def test_clock_rejects_bad_tick() -> None:
    with pytest.raises(ValueError, match="tick_seconds"):
        SimClock(start=datetime(2026, 1, 1, tzinfo=timezone.utc), tick_seconds=0)


def test_clock_rejects_bad_speedup() -> None:
    with pytest.raises(ValueError, match="speedup"):
        SimClock(start=datetime(2026, 1, 1, tzinfo=timezone.utc), speedup=0)


def test_fast_mode_advances_without_sleeping() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = SimClock(start=start, tick_seconds=10.0, mode=ClockMode.FAST)

    wall_before = time.perf_counter()
    for _ in range(100):
        clock.tick()
    wall_elapsed = time.perf_counter() - wall_before

    assert clock.now == start + timedelta(seconds=1000)
    assert clock.tick_count == 100
    assert wall_elapsed < 0.5, f"FAST mode should not sleep, took {wall_elapsed:.3f}s"


def test_now_property_returns_current_sim_time() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = SimClock(start=start, tick_seconds=1.0)
    assert clock.now == start
    clock.tick()
    assert clock.now == start + timedelta(seconds=1)


@pytest.mark.xfail(reason="day-1 task: implement REALTIME mode", strict=True)
def test_realtime_mode_sleeps_approximately_one_wall_second_per_sim_second() -> None:
    """When implemented, REALTIME mode should sleep so wall-time tracks sim-time."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = SimClock(
        start=start,
        tick_seconds=0.1,
        mode=ClockMode.REALTIME,
        speedup=1.0,
    )

    wall_before = time.perf_counter()
    for _ in range(10):
        clock.tick()
    wall_elapsed = time.perf_counter() - wall_before

    assert 0.8 <= wall_elapsed <= 1.5, f"expected ~1s wall time, got {wall_elapsed:.3f}s"
