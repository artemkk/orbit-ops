"""Wire schema for telemetry messages.

One message per (sat_id, tick). Flat structure, JSON-serializable, units
in field names. This is the contract between the producer and every
downstream consumer -- change it carefully.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from orbit_ops.sim.constellation import TickResult


@dataclass(frozen=True, slots=True)
class TelemetryRecord:
    """One telemetry sample for one satellite at one sim-time."""

    # Identity + time
    sat_id: str
    sim_time_iso: str
    """ISO 8601 UTC. We use a string to keep the wire format JSON-native."""

    # Geometric state
    position_eci_km_x: float
    position_eci_km_y: float
    position_eci_km_z: float
    velocity_eci_km_s_x: float
    velocity_eci_km_s_y: float
    velocity_eci_km_s_z: float
    sun_vector_eci_x: float
    sun_vector_eci_y: float
    sun_vector_eci_z: float
    eclipsed: bool
    latitude_deg: float
    longitude_deg: float
    altitude_km: float

    # EPS
    solar_power_w: float
    bus_power_w: float
    net_power_w: float
    battery_soc: float
    battery_charge_wh: float

    # Thermal
    bus_temperature_k: float
    bus_temperature_c: float
    solar_heat_input_w: float
    earth_ir_input_w: float
    radiative_heat_output_w: float
    net_heat_w: float

    @classmethod
    def from_tick(cls, sat_id: str, sim_time: datetime, tr: TickResult) -> TelemetryRecord:
        """Build a record from a Constellation TickResult."""
        return cls(
            sat_id=sat_id,
            sim_time_iso=sim_time.isoformat(),
            position_eci_km_x=tr.geo.position_eci_km[0],
            position_eci_km_y=tr.geo.position_eci_km[1],
            position_eci_km_z=tr.geo.position_eci_km[2],
            velocity_eci_km_s_x=tr.geo.velocity_eci_km_s[0],
            velocity_eci_km_s_y=tr.geo.velocity_eci_km_s[1],
            velocity_eci_km_s_z=tr.geo.velocity_eci_km_s[2],
            sun_vector_eci_x=tr.geo.sun_vector_eci[0],
            sun_vector_eci_y=tr.geo.sun_vector_eci[1],
            sun_vector_eci_z=tr.geo.sun_vector_eci[2],
            eclipsed=tr.geo.eclipsed,
            latitude_deg=tr.geo.latitude_deg,
            longitude_deg=tr.geo.longitude_deg,
            altitude_km=tr.geo.altitude_km,
            solar_power_w=tr.eps.solar_power_w,
            bus_power_w=tr.eps.bus_power_w,
            net_power_w=tr.eps.net_power_w,
            battery_soc=tr.eps.battery_soc,
            battery_charge_wh=tr.eps.battery_charge_wh,
            bus_temperature_k=tr.thermal.bus_temperature_k,
            bus_temperature_c=tr.thermal.bus_temperature_c,
            solar_heat_input_w=tr.thermal.solar_heat_input_w,
            earth_ir_input_w=tr.thermal.earth_ir_input_w,
            radiative_heat_output_w=tr.thermal.radiative_heat_output_w,
            net_heat_w=tr.thermal.net_heat_w,
        )

    def to_json_bytes(self) -> bytes:
        """JSON-encode for Kafka. UTF-8 bytes, no trailing newline."""
        return json.dumps(asdict(self), separators=(",", ":")).encode("utf-8")
