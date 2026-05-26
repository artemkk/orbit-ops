"""Unit tests for the three detectors.

Each test constructs a synthetic stream of mart-grain samples that exercises
one specific behavior of the detector, then asserts the detector fires (or
doesn't) as expected.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orbit_ops.detection.detectors import (
    CapacityFadeDetector,
    StuckSensorDetector,
    ThermalRunawayDetector,
)


def _t(offset_min: int) -> str:
    base = datetime(2026, 5, 1, tzinfo=UTC)
    return (base + timedelta(minutes=offset_min)).isoformat()


def _eps_sample(soc: float, minute: int) -> dict:
    return {
        "minute_bucket": _t(minute),
        "battery_soc_mean": soc,
        "bus_temperature_k_mean": 290.0,
        "net_heat_w_mean": 0.0,
    }


def _therm_sample(temp_k: float, net_heat_w: float, minute: int) -> dict:
    return {
        "minute_bucket": _t(minute),
        "battery_soc_mean": 0.85,
        "bus_temperature_k_mean": temp_k,
        "net_heat_w_mean": net_heat_w,
    }


# -------------------- CapacityFadeDetector --------------------


def test_capacity_fade_does_not_fire_on_constant_signal() -> None:
    det = CapacityFadeDetector(sat_id="SAT-1", window_minutes=10, threshold=0.05)
    for i in range(60):
        ev = det.update(_eps_sample(0.85, i))
        assert ev is None


def test_capacity_fade_fires_on_sustained_downward_drift() -> None:
    det = CapacityFadeDetector(sat_id="SAT-1", window_minutes=10, threshold=0.05, slack=0.0)
    # Build the baseline window
    for i in range(10):
        det.update(_eps_sample(0.95, i))
    # Drift down 0.01/sample
    events = []
    for i in range(10, 30):
        ev = det.update(_eps_sample(0.95 - 0.01 * (i - 10), i))
        if ev:
            events.append(ev)
    assert len(events) == 1
    assert events[0].detector_name == "capacity_fade"
    assert events[0].score >= 0.05


def test_capacity_fade_fires_only_once() -> None:
    det = CapacityFadeDetector(sat_id="SAT-1", window_minutes=10, threshold=0.03, slack=0.0)
    for i in range(10):
        det.update(_eps_sample(0.95, i))
    fired = 0
    for i in range(10, 100):
        ev = det.update(_eps_sample(0.50, i))
        if ev:
            fired += 1
    assert fired == 1


# -------------------- StuckSensorDetector --------------------


def test_stuck_sensor_does_not_fire_when_temperature_tracks_heat() -> None:
    det = StuckSensorDetector(
        sat_id="SAT-1",
        thermal_mass_j_per_k=100.0,
        residual_threshold_k=1.0,
        consecutive_minutes_required=3,
    )
    temp = 290.0
    for i in range(20):
        net_heat = 1.0  # 1 W
        expected_delta = net_heat * 60.0 / 100.0  # 0.6 K
        temp += expected_delta
        ev = det.update(_therm_sample(temp, net_heat, i))
        assert ev is None


def test_stuck_sensor_fires_when_temperature_held_while_heat_nonzero() -> None:
    det = StuckSensorDetector(
        sat_id="SAT-1",
        thermal_mass_j_per_k=100.0,
        residual_threshold_k=1.0,
        consecutive_minutes_required=3,
    )
    det.update(_therm_sample(290.0, 0.0, 0))
    events = []
    for i in range(1, 10):
        net_heat = 5.0  # 5 W -> expected delta ~ 3 K
        ev = det.update(_therm_sample(290.0, net_heat, i))
        if ev:
            events.append(ev)
    assert len(events) == 1
    assert events[0].detector_name == "stuck_sensor"


def test_stuck_sensor_suppresses_when_heat_is_tiny() -> None:
    """If the model isn't predicting movement, a held value is fine."""
    det = StuckSensorDetector(
        sat_id="SAT-1",
        thermal_mass_j_per_k=100.0,
        residual_threshold_k=1.0,
        consecutive_minutes_required=3,
    )
    for i in range(20):
        ev = det.update(_therm_sample(290.0, 0.01, i))  # 0.01 W is negligible
        assert ev is None


# -------------------- ThermalRunawayDetector --------------------


def test_thermal_runaway_does_not_fire_below_ceiling() -> None:
    det = ThermalRunawayDetector(
        sat_id="SAT-1",
        temperature_ceiling_c=35.0,
        slope_window_minutes=5,
    )
    for i in range(50):
        ev = det.update(_therm_sample(303.15, 0.0, i))  # 30 C
        assert ev is None


def test_thermal_runaway_fires_on_monotonic_climb_past_ceiling() -> None:
    det = ThermalRunawayDetector(
        sat_id="SAT-1",
        temperature_ceiling_c=35.0,
        slope_window_minutes=5,
        min_positive_slope_k_per_min=0.5,
    )
    events = []
    for i in range(50):
        temp_c = 30.0 + 0.5 * i  # +0.5 K/min
        temp_k = temp_c + 273.15
        ev = det.update(_therm_sample(temp_k, 0.0, i))
        if ev:
            events.append(ev)
    assert len(events) == 1
    assert events[0].detector_name == "thermal_runaway"
    assert events[0].score > 0


def test_thermal_runaway_ignores_transient_brushes_against_ceiling() -> None:
    """Brief excursions above ceiling without positive slope should not fire."""
    det = ThermalRunawayDetector(
        sat_id="SAT-1",
        temperature_ceiling_c=35.0,
        slope_window_minutes=5,
        min_positive_slope_k_per_min=0.5,
    )
    events = []
    for i in range(50):
        temp_c = 36.0 + 0.1 * (i % 2)  # oscillates around 36
        ev = det.update(_therm_sample(temp_c + 273.15, 0.0, i))
        if ev:
            events.append(ev)
    assert len(events) == 0
