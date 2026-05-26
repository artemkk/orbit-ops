"""Unit tests for the fault injection layer.

Each fault has a clear symptom; tests verify that symptom appears in
the modified TickResult while the underlying TickResult fields not
affected by that fault remain unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from orbit_ops.sim.constellation import TickResult
from orbit_ops.sim.faults import FaultRegistry, FaultSpec, FaultType
from orbit_ops.sim.satellite import SatelliteState
from orbit_ops.sim.subsystems import EpsTelemetry, ThermalTelemetry


def _geo(sat_id: str = "SKYSAT-1", t: datetime | None = None) -> SatelliteState:
    return SatelliteState(
        sat_id=sat_id,
        sim_time=t or datetime(2026, 5, 1, tzinfo=UTC),
        position_eci_km=(7000.0, 0.0, 0.0),
        velocity_eci_km_s=(0.0, 7.5, 0.0),
        sun_vector_eci=(1.0, 0.0, 0.0),
        eclipsed=False,
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_km=550.0,
    )


def _eps() -> EpsTelemetry:
    return EpsTelemetry(
        solar_power_w=200.0,
        bus_power_w=90.0,
        net_power_w=110.0,
        battery_soc=0.9,
        battery_charge_wh=135.0,
    )


def _thermal(k: float = 290.0) -> ThermalTelemetry:
    return ThermalTelemetry(
        bus_temperature_k=k,
        bus_temperature_c=k - 273.15,
        solar_heat_input_w=190.0,
        earth_ir_input_w=100.0,
        radiative_heat_output_w=300.0,
        net_heat_w=-10.0,
    )


def _tick(
    t: datetime, sat_id: str = "SKYSAT-1", temp_k: float = 290.0
) -> tuple[str, datetime, TickResult]:
    return sat_id, t, TickResult(geo=_geo(sat_id, t), eps=_eps(), thermal=_thermal(temp_k))


def test_no_faults_passes_through_unchanged() -> None:
    reg = FaultRegistry()
    sat_id, t, tr = _tick(datetime(2026, 5, 1, tzinfo=UTC))
    out = reg.apply(sat_id, t, tr)
    assert out is tr  # no copy needed when no faults


def test_fault_not_yet_started_has_no_effect() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso="2026-05-02T00:00:00+00:00", params={"fade_rate_per_day": 0.5},
        ),
    ])
    sat_id, t, tr = _tick(datetime(2026, 5, 1, tzinfo=UTC))  # before fault start
    out = reg.apply(sat_id, t, tr)
    assert out.eps.battery_soc == tr.eps.battery_soc


def test_fault_on_other_sat_does_not_affect_this_one() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-7", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso="2026-05-01T00:00:00+00:00", params={"fade_rate_per_day": 0.5},
        ),
    ])
    sat_id, t, tr = _tick(datetime(2026, 5, 1, 12, tzinfo=UTC), sat_id="SKYSAT-1")
    out = reg.apply(sat_id, t, tr)
    assert out.eps.battery_soc == tr.eps.battery_soc


def test_battery_capacity_fade_lowers_reported_soc_over_time() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso="2026-05-01T00:00:00+00:00",
            params={"fade_rate_per_day": 0.10, "floor": 0.5},
        ),
    ])
    start = datetime(2026, 5, 1, tzinfo=UTC)
    # Day 0: no fade
    _, _, tr0 = _tick(start)
    out0 = reg.apply("SKYSAT-1", start, tr0)
    assert out0.eps.battery_soc == pytest.approx(0.9, rel=1e-6)
    # Day 1: 10% fade
    _, _, tr1 = _tick(start + timedelta(days=1))
    out1 = reg.apply("SKYSAT-1", start + timedelta(days=1), tr1)
    assert out1.eps.battery_soc == pytest.approx(0.9 * 0.9, rel=1e-6)
    # Day 10: floor clamps at 0.5 (since 1 - 0.1*10 = 0)
    _, _, tr10 = _tick(start + timedelta(days=10))
    out10 = reg.apply("SKYSAT-1", start + timedelta(days=10), tr10)
    assert out10.eps.battery_soc == pytest.approx(0.9 * 0.5, rel=1e-6)


def test_battery_capacity_fade_does_not_touch_thermal_or_geometry() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso="2026-05-01T00:00:00+00:00", params={"fade_rate_per_day": 0.5},
        ),
    ])
    sat_id, t, tr = _tick(datetime(2026, 5, 2, tzinfo=UTC), temp_k=295.0)
    out = reg.apply(sat_id, t, tr)
    assert out.thermal == tr.thermal
    assert out.geo == tr.geo


def test_stuck_sensor_holds_value_across_ticks() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.STUCK_TEMPERATURE_SENSOR,
            start_iso="2026-05-01T00:00:00+00:00",
        ),
    ])
    start = datetime(2026, 5, 1, tzinfo=UTC)

    # First call captures the current temperature
    _, _, tr0 = _tick(start, temp_k=290.0)
    out0 = reg.apply("SKYSAT-1", start, tr0)
    assert out0.thermal.bus_temperature_k == pytest.approx(290.0)

    # Subsequent calls hold that value even when underlying changes
    _, _, tr1 = _tick(start + timedelta(minutes=10), temp_k=295.0)
    out1 = reg.apply("SKYSAT-1", start + timedelta(minutes=10), tr1)
    assert out1.thermal.bus_temperature_k == pytest.approx(290.0)

    _, _, tr2 = _tick(start + timedelta(hours=2), temp_k=280.0)
    out2 = reg.apply("SKYSAT-1", start + timedelta(hours=2), tr2)
    assert out2.thermal.bus_temperature_k == pytest.approx(290.0)


def test_stuck_sensor_keeps_celsius_consistent_with_kelvin() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.STUCK_TEMPERATURE_SENSOR,
            start_iso="2026-05-01T00:00:00+00:00",
        ),
    ])
    start = datetime(2026, 5, 1, tzinfo=UTC)
    _, _, tr0 = _tick(start, temp_k=287.15)
    out0 = reg.apply("SKYSAT-1", start, tr0)
    assert out0.thermal.bus_temperature_c == pytest.approx(out0.thermal.bus_temperature_k - 273.15)


def test_stuck_sensor_leaves_other_channels_flowing() -> None:
    """Even with sensor stuck, the model's solar_heat_input and net_heat_w
    should still reflect what the underlying physics says."""
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.STUCK_TEMPERATURE_SENSOR,
            start_iso="2026-05-01T00:00:00+00:00",
        ),
    ])
    start = datetime(2026, 5, 1, tzinfo=UTC)
    _, _, tr0 = _tick(start, temp_k=290.0)
    reg.apply("SKYSAT-1", start, tr0)
    _, _, tr1 = _tick(start + timedelta(minutes=10), temp_k=295.0)
    # Modify the original thermal to have a different solar_heat_input to confirm passthrough
    tr1 = TickResult(
        geo=tr1.geo, eps=tr1.eps,
        thermal=replace(tr1.thermal, solar_heat_input_w=0.0),
    )
    out1 = reg.apply("SKYSAT-1", start + timedelta(minutes=10), tr1)
    assert out1.thermal.solar_heat_input_w == 0.0  # passthrough


def test_thermal_runaway_grows_linearly_then_caps() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.THERMAL_RUNAWAY,
            start_iso="2026-05-01T00:00:00+00:00",
            params={"rate_k_per_hour": 4.0, "cap_k": 20.0},
        ),
    ])
    start = datetime(2026, 5, 1, tzinfo=UTC)

    # t = 0: no bias
    _, _, tr0 = _tick(start, temp_k=290.0)
    out0 = reg.apply("SKYSAT-1", start, tr0)
    assert out0.thermal.bus_temperature_k == pytest.approx(290.0)

    # t = 1 hour: +4 K
    _, _, tr1 = _tick(start + timedelta(hours=1), temp_k=290.0)
    out1 = reg.apply("SKYSAT-1", start + timedelta(hours=1), tr1)
    assert out1.thermal.bus_temperature_k == pytest.approx(294.0)

    # t = 10 hours: capped at +20 K
    _, _, tr10 = _tick(start + timedelta(hours=10), temp_k=290.0)
    out10 = reg.apply("SKYSAT-1", start + timedelta(hours=10), tr10)
    assert out10.thermal.bus_temperature_k == pytest.approx(310.0)


def test_yaml_loader_parses_example_config() -> None:
    """Verifies data/faults.example.yaml loads cleanly with the expected shape."""
    repo = Path(__file__).resolve().parent.parent
    reg = FaultRegistry.from_yaml(repo / "data" / "faults.example.yaml")
    assert len(reg.specs) == 3
    types = {s.fault_type for s in reg.specs}
    assert types == {
        FaultType.BATTERY_CAPACITY_FADE,
        FaultType.STUCK_TEMPERATURE_SENSOR,
        FaultType.THERMAL_RUNAWAY,
    }


def test_missing_yaml_returns_empty_registry() -> None:
    reg = FaultRegistry.from_yaml(Path("/does/not/exist/at/all.yaml"))
    assert reg.specs == []


def test_two_faults_on_same_sat_both_apply() -> None:
    """A sat can have multiple concurrent faults; all should layer."""
    reg = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso="2026-05-01T00:00:00+00:00",
            params={"fade_rate_per_day": 0.5, "floor": 0.5},
        ),
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.THERMAL_RUNAWAY,
            start_iso="2026-05-01T00:00:00+00:00",
            params={"rate_k_per_hour": 2.0, "cap_k": 20.0},
        ),
    ])
    start = datetime(2026, 5, 1, tzinfo=UTC)
    _, _, tr = _tick(start + timedelta(hours=2), temp_k=290.0)
    out = reg.apply("SKYSAT-1", start + timedelta(hours=2), tr)
    # Both faults should have taken effect
    assert out.eps.battery_soc < tr.eps.battery_soc
    assert out.thermal.bus_temperature_k > tr.thermal.bus_temperature_k


def test_fault_spec_requires_exactly_one_start_field() -> None:
    """Schema validation: both or neither is an error at YAML load time."""
    import tempfile

    both_yaml = """
faults:
  - sat_id: "SAT-1"
    fault_type: "thermal_runaway"
    start_iso: "2026-05-01T00:00:00+00:00"
    start_offset: "+00:30:00"
"""
    neither_yaml = """
faults:
  - sat_id: "SAT-1"
    fault_type: "thermal_runaway"
"""
    for bad in (both_yaml, neither_yaml):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(bad)
            path = Path(f.name)
        try:
            with pytest.raises(ValueError, match="exactly one"):
                FaultRegistry.from_yaml(path)
        finally:
            path.unlink()


def test_offset_parsing_handles_hms_and_days() -> None:
    from orbit_ops.sim.faults import _parse_offset

    assert _parse_offset("+00:30:00") == timedelta(minutes=30)
    assert _parse_offset("+01:00:00") == timedelta(hours=1)
    assert _parse_offset("+002-12:00:00") == timedelta(days=2, hours=12)


def test_bind_to_sim_start_resolves_offsets() -> None:
    reg = FaultRegistry(specs=[
        FaultSpec(sat_id="SAT-1", fault_type=FaultType.THERMAL_RUNAWAY,
                  start_offset="+01:30:00"),
        FaultSpec(sat_id="SAT-2", fault_type=FaultType.BATTERY_CAPACITY_FADE,
                  start_iso="2026-05-01T00:00:00+00:00"),  # already absolute
    ])
    sim_start = datetime(2026, 5, 26, 20, 0, 0, tzinfo=UTC)
    bound = reg.bind_to_sim_start(sim_start)

    # Offset spec resolved
    assert bound.specs[0].start_iso == "2026-05-26T21:30:00+00:00"
    assert bound.specs[0].start_offset is None

    # Absolute spec untouched
    assert bound.specs[1].start_iso == "2026-05-01T00:00:00+00:00"
