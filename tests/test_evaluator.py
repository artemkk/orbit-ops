"""Tests for the detector evaluator."""

from __future__ import annotations

from datetime import UTC, datetime

from orbit_ops.detection.evaluator import evaluate
from orbit_ops.detection.events import AnomalyEvent, AnomalySeverity
from orbit_ops.sim.faults import FaultRegistry, FaultSpec, FaultType


def _event(sat: str, det: str, t: datetime) -> AnomalyEvent:
    return AnomalyEvent(
        sat_id=sat,
        detector_name=det,
        sim_time_iso=t.isoformat(),
        severity=AnomalySeverity.WARNING,
        score=1.0,
        description="test",
    )


def test_true_positive_when_event_during_fault_window() -> None:
    fault_start = datetime(2026, 5, 1, tzinfo=UTC)
    faults = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso=fault_start.isoformat(),
        ),
    ])
    events = [_event("SKYSAT-1", "capacity_fade", datetime(2026, 5, 2, tzinfo=UTC))]
    sc = evaluate(events, faults)
    assert sc["capacity_fade"].true_positives == 1
    assert sc["capacity_fade"].false_positives == 0
    assert sc["capacity_fade"].false_negatives == 0


def test_false_positive_when_event_before_fault_start() -> None:
    fault_start = datetime(2026, 5, 5, tzinfo=UTC)
    faults = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso=fault_start.isoformat(),
        ),
    ])
    events = [_event("SKYSAT-1", "capacity_fade", datetime(2026, 5, 1, tzinfo=UTC))]
    sc = evaluate(events, faults)
    assert sc["capacity_fade"].true_positives == 0
    assert sc["capacity_fade"].false_positives == 1


def test_false_positive_when_no_fault_on_that_sat() -> None:
    faults = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-2", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso="2026-05-01T00:00:00+00:00",
        ),
    ])
    events = [_event("SKYSAT-1", "capacity_fade", datetime(2026, 5, 2, tzinfo=UTC))]
    sc = evaluate(events, faults)
    assert sc["capacity_fade"].false_positives == 1
    assert sc["capacity_fade"].true_positives == 0


def test_false_negative_when_fault_active_but_no_event() -> None:
    faults = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.THERMAL_RUNAWAY,
            start_iso="2026-05-01T00:00:00+00:00",
        ),
    ])
    sc = evaluate([], faults)
    assert sc["thermal_runaway"].false_negatives == 1
    assert sc["thermal_runaway"].true_positives == 0


def test_latency_recorded_from_fault_start_to_first_event() -> None:
    fault_start = datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC)
    faults = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso=fault_start.isoformat(),
        ),
    ])
    events = [_event("SKYSAT-1", "capacity_fade", fault_start.replace(hour=3))]
    sc = evaluate(events, faults)
    assert sc["capacity_fade"].mean_latency_seconds == 3 * 3600.0


def test_recall_and_precision_computed_correctly() -> None:
    faults = FaultRegistry(specs=[
        FaultSpec(
            sat_id="SKYSAT-1", fault_type=FaultType.BATTERY_CAPACITY_FADE,
            start_iso="2026-05-01T00:00:00+00:00",
        ),
    ])
    events = [_event("SKYSAT-1", "capacity_fade", datetime(2026, 5, 2, tzinfo=UTC))]
    sc = evaluate(events, faults)["capacity_fade"]
    assert sc.recall == 1.0
    assert sc.precision == 1.0
