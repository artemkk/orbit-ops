"""Simulation clock.

Every component that needs to know "what time is it in the sim" reads from a
SimClock instance. Wall-clock time (``time.time()``, ``datetime.now()``) is
forbidden anywhere downstream of this module. That separation is the single
most important architectural decision in the project: it lets the same
producer code drive a fast batch (generate a week of telemetry in 5 minutes
of wall time) or a real-time stream (1 sim-second per 1 wall-second for the
demo) without changes elsewhere.

Day-1 implementation task. The class below is a stub with the intended API
and a failing test. Fill it in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class ClockMode(str, Enum):
    FAST = "fast"
    REALTIME = "realtime"


@dataclass
class SimClock:
    """Simulation clock.

    Parameters
    ----------
    start : datetime
        UTC datetime the sim begins at.
    tick_seconds : float
        Sim seconds per tick. The fundamental sample period.
    mode : ClockMode
        FAST: ``tick()`` advances sim time with no wall-clock sleep.
        REALTIME: ``tick()`` sleeps so 1 sim-second ≈ 1 wall-second
        (scaled by ``speedup``).
    speedup : float
        Only used in REALTIME. 1.0 = real time. 60.0 = 1 wall-min per sim-hour.
    """

    start: datetime
    tick_seconds: float = 1.0
    mode: ClockMode = ClockMode.FAST
    speedup: float = 1.0

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            raise ValueError("SimClock.start must be timezone-aware (use UTC)")
        if self.tick_seconds <= 0:
            raise ValueError("tick_seconds must be > 0")
        if self.speedup <= 0:
            raise ValueError("speedup must be > 0")
        self._now = self.start
        self._tick_count = 0

    @property
    def now(self) -> datetime:
        """Current sim time."""
        return self._now

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def tick(self) -> datetime:
        """Advance one tick. Returns the new sim time.

        In FAST mode this is just arithmetic. In REALTIME mode this sleeps
        ``tick_seconds / speedup`` wall-seconds before returning.

        TODO(day 1): implement REALTIME sleep behavior.
        """
        self._now = self._now + timedelta(seconds=self.tick_seconds)
        self._tick_count += 1
        return self._now

    @classmethod
    def utc_now_start(cls, **kwargs: object) -> SimClock:
        """Convenience: start a clock at the current wall-clock UTC."""
        return cls(start=datetime.now(timezone.utc), **kwargs)  # type: ignore[arg-type]
