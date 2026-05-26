"""A Constellation owns N satellites and their per-subsystem internal states.

One `tick()` advances every satellite by one sim-clock tick and returns a
list of `(SatelliteState, EpsTelemetry, ThermalTelemetry)` tuples -- one
per satellite. Downstream code (the producer) is responsible for turning
those tuples into wire messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orbit_ops.common.clock import SimClock
from orbit_ops.sim.satellite import Satellite, SatelliteState, load_tle_file
from orbit_ops.sim.subsystems import (
    EpsState,
    EpsTelemetry,
    ThermalState,
    ThermalTelemetry,
    eps_initial_state,
    eps_step,
    thermal_initial_state,
    thermal_step,
)


@dataclass(slots=True)
class _SatRuntime:
    """Per-satellite mutable state held by the Constellation."""

    sat: Satellite
    eps: EpsState
    thermal: ThermalState


@dataclass(frozen=True, slots=True)
class TickResult:
    """One satellite's full output for one tick."""

    geo: SatelliteState
    eps: EpsTelemetry
    thermal: ThermalTelemetry


class Constellation:
    """A fleet of satellites sharing a SimClock.

    Construct from a list of `(name, tle_line1, tle_line2)` tuples, or via
    the classmethod `from_tle_file` for the common case.
    """

    def __init__(
        self,
        tles: list[tuple[str, str, str]],
        clock: SimClock,
    ) -> None:
        if not tles:
            raise ValueError("Constellation requires at least one TLE")
        self._clock = clock
        self._sats: list[_SatRuntime] = [
            _SatRuntime(
                sat=Satellite(name, l1, l2, clock),
                eps=eps_initial_state(),
                thermal=thermal_initial_state(),
            )
            for (name, l1, l2) in tles
        ]

    @classmethod
    def from_tle_file(
        cls,
        path: Path,
        clock: SimClock,
        *,
        name_filter: str | None = None,
        limit: int | None = None,
    ) -> Constellation:
        """Build a constellation from a TLE file.

        Parameters
        ----------
        path : Path
            TLE file (3 lines per sat: name + line1 + line2).
        clock : SimClock
            Shared clock all satellites read from.
        name_filter : str | None
            If given, keep only TLE entries whose name (uppercased) contains
            this substring. E.g., "SKYSAT" keeps only SkySats from the Planet
            catalog.
        limit : int | None
            If given, keep at most this many satellites (after filtering).
        """
        entries = load_tle_file(path)
        if name_filter is not None:
            f = name_filter.upper()
            entries = [(n, l1, l2) for (n, l1, l2) in entries if f in n.upper()]
        if limit is not None:
            entries = entries[:limit]
        if not entries:
            raise ValueError(
                f"No TLE entries matched filter={name_filter!r}, limit={limit}"
            )
        return cls(entries, clock)

    @property
    def size(self) -> int:
        return len(self._sats)

    @property
    def sat_ids(self) -> list[str]:
        return [s.sat.sat_id for s in self._sats]

    @property
    def now(self) -> object:
        """Current sim time. Exposed so the producer doesn't need SLF001."""
        return self._clock.now

    def tick(self, dt_s: float | None = None) -> list[TickResult]:
        """Advance every satellite by one tick.

        Parameters
        ----------
        dt_s : float | None
            Integration step in seconds for the subsystem models. Defaults to
            the clock's `tick_seconds`. Passed explicitly to make the call
            site honest about what the integration step is.

        Returns
        -------
        list[TickResult]
            One result per satellite, in the same order as `sat_ids`.
        """
        if dt_s is None:
            dt_s = self._clock.tick_seconds

        results: list[TickResult] = []
        for r in self._sats:
            geo = r.sat.state()
            r.eps, eps_t = eps_step(geo, r.eps, dt_s)
            r.thermal, thermal_t = thermal_step(geo, r.thermal, dt_s)
            results.append(TickResult(geo=geo, eps=eps_t, thermal=thermal_t))

        self._clock.tick()
        return results
