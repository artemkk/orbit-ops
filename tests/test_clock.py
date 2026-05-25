"""Tests for SimClock.

The TODO test at the bottom is intentionally failing. It documents the day-1
goal: flip it to passing by implementing REALTIME mode.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from orbit_ops.common.clock import ClockMode, SimClock


def test_clock_requires_tz_aware_start() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SimClock(start=datetime(2026, 1, 1))


def test_clock_rejects_bad_tick() -> None:
    with pytest.raises(ValueError, match="tick_seconds"):
        SimClock(start=datetime(2026, 1, 1, tzinfo=UTC), tick_seconds=0)


def test_clock_rejects_bad_speedup() -> None:
    with pytest.raises(ValueError, match="speedup"):
        SimClock(start=datetime(2026, 1, 1, tzinfo=UTC), speedup=0)


def test_fast_mode_advances_without_sleeping() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimClock(start=start, tick_seconds=10.0, mode=ClockMode.FAST)

    wall_before = time.perf_counter()
    for _ in range(100):
        clock.tick()
    wall_elapsed = time.perf_counter() - wall_before

    assert clock.now == start + timedelta(seconds=1000)
    assert clock.tick_count == 100
    assert wall_elapsed < 0.5, f"FAST mode should not sleep, took {wall_elapsed:.3f}s"


def test_now_property_returns_current_sim_time() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimClock(start=start, tick_seconds=1.0)
    assert clock.now == start
    clock.tick()
    assert clock.now == start + timedelta(seconds=1)


def test_realtime_mode_sleeps_approximately_one_wall_second_per_sim_second() -> None:
    """When implemented, REALTIME mode should sleep so wall-time tracks sim-time."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
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


def test_realtime_mode_respects_speedup() -> None:
    """speedup=10 means 1 wall-second = 10 sim-seconds."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimClock(
        start=start,
        tick_seconds=0.1,
        mode=ClockMode.REALTIME,
        speedup=10.0,
    )

    wall_before = time.perf_counter()
    for _ in range(10):  # 10 ticks * 0.1s = 1 sim-second, at 10x = 0.1s wall
        clock.tick()
    wall_elapsed = time.perf_counter() - wall_before

    assert clock.now == start + timedelta(seconds=1)
    assert 0.05 <= wall_elapsed <= 0.25, (
        f"expected ~0.1s wall time at speedup=10, got {wall_elapsed:.3f}s"
    )


def test_realtime_mode_absorbs_tick_work_without_drift() -> None:
    """Work done between ticks should eat into sleep, not extend wall time.

    Simulate 50ms of work per tick; with tick_seconds=0.1 the loop should
    still finish in ~1s wall time, not 1.5s (which is what a naive
    sleep(tick_seconds) implementation would produce).
    """
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimClock(
        start=start,
        tick_seconds=0.1,
        mode=ClockMode.REALTIME,
        speedup=1.0,
    )

    wall_before = time.perf_counter()
    for _ in range(10):
        time.sleep(0.05)  # fake "work" between ticks
        clock.tick()
    wall_elapsed = time.perf_counter() - wall_before

    # Without drift compensation this would take ~1.5s. With it, ~1s.
    assert 0.85 <= wall_elapsed <= 1.25, (
        f"deadline scheduling failed; took {wall_elapsed:.3f}s "
        f"(naive sleep would give ~1.5s)"
    )


def test_realtime_mode_does_not_run_faster_than_realtime_on_overrun() -> None:
    """If a tick's work exceeds its budget, the clock lags but never speeds up to compensate."""
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimClock(
        start=start,
        tick_seconds=0.05,  # 50ms budget per tick
        mode=ClockMode.REALTIME,
        speedup=1.0,
    )

    wall_before = time.perf_counter()
    for _ in range(5):
        time.sleep(0.15)  # work exceeds budget by 100ms each tick
        clock.tick()
    wall_elapsed = time.perf_counter() - wall_before

    # Each tick's work is 150ms; 5 ticks = ~750ms minimum.
    # The clock cannot teleport forward, so wall time must be at least the work time.
    assert wall_elapsed >= 0.70, (
        f"clock ran faster than realtime on overrun; took {wall_elapsed:.3f}s "
        f"(should be >= 0.75s)"
    )
