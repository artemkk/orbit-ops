"""Fault injection layer.

Faults are transformations applied to nominal telemetry after the subsystem
step functions have run. The underlying physics stays clean; the observable
telemetry diverges according to the active fault set.

Architecture:

    [physics]                    [fault layer]
    SatelliteState --+
    EpsState ---------+--> subsystem_step --> TickResult --> FaultRegistry.apply --> TickResult'
    ThermalState ----+                                                              (observed)

Three fault types implemented here:

- BatteryCapacityFade: scales reported battery_soc downward by an ever-
  increasing fade factor. The internal SoC keeps tracking nominal charge;
  only the reported telemetry is affected, matching how cell degradation
  presents in real flight data (the cells are losing capacity; the rest of
  the bus doesn't know).

- StuckTemperatureSensor: holds bus_temperature_k at a captured value
  from the moment the fault activates. bus_temperature_c is recomputed
  from the held value to stay consistent. Other thermal channels keep
  flowing (they read different sensors).

- ThermalRunaway: adds a positive heat bias to the reported bus_temperature_k,
  growing linearly with time-since-onset. Models a stuck heater or lost
  radiator coupling. Threshold-detectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import yaml

from orbit_ops.sim.constellation import TickResult
from orbit_ops.sim.subsystems import EpsTelemetry, ThermalTelemetry


class FaultType(StrEnum):
    BATTERY_CAPACITY_FADE = "battery_capacity_fade"
    STUCK_TEMPERATURE_SENSOR = "stuck_temperature_sensor"
    THERMAL_RUNAWAY = "thermal_runaway"


@dataclass(frozen=True, slots=True)
class FaultSpec:
    """Declarative description of one fault. Loaded from YAML."""

    sat_id: str
    fault_type: FaultType
    start_iso: str
    """Sim-time ISO 8601 UTC. Fault becomes active when sim_time >= start."""
    params: dict[str, float] = field(default_factory=dict)

    @property
    def start(self) -> datetime:
        dt = datetime.fromisoformat(self.start_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt


@dataclass(slots=True)
class _StuckSensorState:
    """Captured value at the moment the stuck-sensor fault activated."""

    held_temperature_k: float | None = None


@dataclass(slots=True)
class FaultRegistry:
    """Owns active fault specs and per-fault mutable state (e.g. stuck values)."""

    specs: list[FaultSpec] = field(default_factory=list)
    _stuck_state: dict[str, _StuckSensorState] = field(default_factory=dict)
    """Keyed by sat_id; one stuck-sensor capture per sat."""

    @classmethod
    def from_yaml(cls, path: Path) -> FaultRegistry:
        if not path.exists():
            return cls(specs=[])
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        specs: list[FaultSpec] = []
        for entry in data.get("faults", []):
            specs.append(
                FaultSpec(
                    sat_id=entry["sat_id"],
                    fault_type=FaultType(entry["fault_type"]),
                    start_iso=entry["start_iso"],
                    params={k: float(v) for k, v in entry.get("params", {}).items()},
                )
            )
        return cls(specs=specs)

    def active_for(self, sat_id: str, sim_time: datetime) -> list[FaultSpec]:
        out: list[FaultSpec] = []
        for s in self.specs:
            if s.sat_id != sat_id:
                continue
            if sim_time >= s.start:
                out.append(s)
        return out

    def apply(self, sat_id: str, sim_time: datetime, tr: TickResult) -> TickResult:
        """Return a TickResult with any active faults applied."""
        active = self.active_for(sat_id, sim_time)
        if not active:
            return tr
        eps = tr.eps
        thermal = tr.thermal
        for fault in active:
            if fault.fault_type is FaultType.BATTERY_CAPACITY_FADE:
                eps = _apply_capacity_fade(eps, fault, sim_time)
            elif fault.fault_type is FaultType.STUCK_TEMPERATURE_SENSOR:
                thermal = self._apply_stuck_sensor(sat_id, thermal, fault, sim_time)
            elif fault.fault_type is FaultType.THERMAL_RUNAWAY:
                thermal = _apply_thermal_runaway(thermal, fault, sim_time)
        return TickResult(geo=tr.geo, eps=eps, thermal=thermal)

    def _apply_stuck_sensor(
        self,
        sat_id: str,
        thermal: ThermalTelemetry,
        fault: FaultSpec,
        sim_time: datetime,
    ) -> ThermalTelemetry:
        state = self._stuck_state.get(sat_id)
        if state is None:
            state = _StuckSensorState(held_temperature_k=thermal.bus_temperature_k)
            self._stuck_state[sat_id] = state
        held = state.held_temperature_k
        assert held is not None
        return ThermalTelemetry(
            bus_temperature_k=held,
            bus_temperature_c=held - 273.15,
            solar_heat_input_w=thermal.solar_heat_input_w,
            earth_ir_input_w=thermal.earth_ir_input_w,
            radiative_heat_output_w=thermal.radiative_heat_output_w,
            net_heat_w=thermal.net_heat_w,
        )


def _apply_capacity_fade(
    eps: EpsTelemetry,
    fault: FaultSpec,
    sim_time: datetime,
) -> EpsTelemetry:
    """Scale reported SoC by a fade factor that grows linearly with elapsed time."""
    fade_rate = fault.params.get("fade_rate_per_day", 0.02)
    floor = fault.params.get("floor", 0.5)
    elapsed_days = (sim_time - fault.start).total_seconds() / 86400.0
    fade = max(floor, 1.0 - fade_rate * max(0.0, elapsed_days))
    return EpsTelemetry(
        solar_power_w=eps.solar_power_w,
        bus_power_w=eps.bus_power_w,
        net_power_w=eps.net_power_w,
        battery_soc=eps.battery_soc * fade,
        battery_charge_wh=eps.battery_charge_wh * fade,
    )


def _apply_thermal_runaway(
    thermal: ThermalTelemetry,
    fault: FaultSpec,
    sim_time: datetime,
) -> ThermalTelemetry:
    """Add a linearly growing positive temperature bias to the reported value."""
    rate = fault.params.get("rate_k_per_hour", 2.0)
    cap = fault.params.get("cap_k", 50.0)
    elapsed_hours = (sim_time - fault.start).total_seconds() / 3600.0
    bias = min(cap, rate * max(0.0, elapsed_hours))
    new_k = thermal.bus_temperature_k + bias
    return ThermalTelemetry(
        bus_temperature_k=new_k,
        bus_temperature_c=new_k - 273.15,
        solar_heat_input_w=thermal.solar_heat_input_w,
        earth_ir_input_w=thermal.earth_ir_input_w,
        radiative_heat_output_w=thermal.radiative_heat_output_w,
        net_heat_w=thermal.net_heat_w,
    )
