"""Skyfield-backed satellite propagation.

A Satellite wraps a TLE and produces SatelliteState samples driven by a
SimClock. This module owns all coordinate-frame conversions; downstream
code consumes SatelliteState and never touches Skyfield directly.

Frames
------
ECI  — Earth-centered inertial (Skyfield's GCRS/ICRF). Used for
       position, velocity, and sun-vector math. Skyfield's
       ``EarthSatellite.at(t)`` returns GCRS natively; we expose it
       as-is rather than rotating to ECEF, because (a) the sun-vector
       dot product in the EPS model needs an inertial frame, and (b)
       ground-track work uses the geodetic sub-satellite point below.
LLA  — Geodetic latitude (deg, north positive), longitude (deg, east
       positive, -180..180), altitude above WGS84 ellipsoid (km).
       Derived from the ECI position via ``wgs84.subpoint_of()``.

Design note: if a future component (e.g., ground-station visibility)
needs ECEF x/y/z, add a conversion then — don't pessimise every tick
by rotating a frame nobody reads yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from skyfield.api import EarthSatellite, load, wgs84

from orbit_ops.common.clock import SimClock


@dataclass(frozen=True, slots=True)
class SatelliteState:
    """One propagated sample of a satellite's geometric state.

    All vectors are 3-tuples of floats. Units called out per field.
    """

    sat_id: str
    sim_time: datetime
    # Position and velocity in ECI / GCRS (km, km/s).
    position_eci_km: tuple[float, float, float]
    velocity_eci_km_s: tuple[float, float, float]
    # Sun direction unit vector in ECI (dimensionless). Points from sat → Sun.
    sun_vector_eci: tuple[float, float, float]
    # True iff the satellite is in Earth's shadow (not sunlit).
    eclipsed: bool
    # Geodetic sub-satellite point.
    latitude_deg: float
    longitude_deg: float
    altitude_km: float


class Satellite:
    """One propagated satellite, driven by a SimClock.

    Parameters
    ----------
    sat_id : str
        Stable identifier. Use the TLE's name (line 0) or NORAD ID.
    tle_line1, tle_line2 : str
        The two-line element set. Do not include the name line.
    clock : SimClock
        The sim clock this satellite's `state()` reads from.
    """

    def __init__(
        self,
        sat_id: str,
        tle_line1: str,
        tle_line2: str,
        clock: SimClock,
    ) -> None:
        self.sat_id = sat_id
        self._clock = clock
        self._ts = load.timescale()
        self._sat = EarthSatellite(tle_line1, tle_line2, sat_id, self._ts)
        # Earth-Sun ephemeris. Loaded lazily on first state() call to keep
        # construction cheap and unit tests fast.
        self._eph = None  # type: ignore[assignment]
        self._sun = None  # type: ignore[assignment]
        self._earth = None  # type: ignore[assignment]

    def _ensure_ephemeris(self) -> None:
        if self._eph is None:
            self._eph = load("de421.bsp")
            self._sun = self._eph["sun"]
            self._earth = self._eph["earth"]

    def state(self) -> SatelliteState:
        """Compute the satellite's state at the clock's current sim time."""
        self._ensure_ephemeris()
        now = self._clock.now
        t = self._ts.from_datetime(now)

        # Position and velocity in ECI (GCRS). This is Skyfield's native
        # frame for EarthSatellite — no rotation needed.
        geocentric = self._sat.at(t)
        pos_eci_km = geocentric.position.km
        vel_eci_km_s = geocentric.velocity.km_per_s

        # Geodetic sub-satellite point via WGS84.
        subpoint = wgs84.subpoint_of(geocentric)
        lat_deg = subpoint.latitude.degrees
        lon_deg = subpoint.longitude.degrees
        alt_km = wgs84.height_of(geocentric).km

        # Sun vector in ECI: direction from satellite to Sun, unit length.
        sat_from_earth = self._earth + self._sat
        sun_apparent = sat_from_earth.at(t).observe(self._sun).apparent()
        sun_vec_km = sun_apparent.position.km
        sun_unit = np.asarray(sun_vec_km) / np.linalg.norm(sun_vec_km)

        # Eclipse check: is_sunlit() returns True when sunlit.
        eclipsed = not bool(geocentric.is_sunlit(self._eph))

        return SatelliteState(
            sat_id=self.sat_id,
            sim_time=now,
            position_eci_km=(float(pos_eci_km[0]), float(pos_eci_km[1]), float(pos_eci_km[2])),
            velocity_eci_km_s=(
                float(vel_eci_km_s[0]),
                float(vel_eci_km_s[1]),
                float(vel_eci_km_s[2]),
            ),
            sun_vector_eci=(float(sun_unit[0]), float(sun_unit[1]), float(sun_unit[2])),
            eclipsed=eclipsed,
            latitude_deg=float(lat_deg),
            longitude_deg=float(lon_deg),
            altitude_km=float(alt_km),
        )


def load_tle_file(path: Path) -> list[tuple[str, str, str]]:
    """Parse a 3-line-per-sat TLE file. Returns list of (name, line1, line2)."""
    lines = [ln.rstrip() for ln in path.read_text().splitlines() if ln.strip()]
    if len(lines) % 3 != 0:
        raise ValueError(f"TLE file has {len(lines)} lines; expected multiple of 3")
    out: list[tuple[str, str, str]] = []
    for i in range(0, len(lines), 3):
        name, l1, l2 = lines[i].strip(), lines[i + 1], lines[i + 2]
        if not l1.startswith("1 ") or not l2.startswith("2 "):
            raise ValueError(f"Bad TLE block at line {i}: {name!r}")
        out.append((name, l1, l2))
    return out
