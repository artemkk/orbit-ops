"""Evaluate detector output against fault YAML ground truth.

For each (sat_id, detector_name) we have:
- Detected events: rows in the anomaly_events Parquet, with sim_time_iso
- Ground-truth fault windows: from the fault YAML, one per fault spec,
  starting at start_iso and running indefinitely (or until sim end)

The mapping between detector_name and fault_type is fixed:
- capacity_fade        <-> BATTERY_CAPACITY_FADE
- stuck_sensor         <-> STUCK_TEMPERATURE_SENSOR
- thermal_runaway      <-> THERMAL_RUNAWAY
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from orbit_ops.detection.events import AnomalyEvent
from orbit_ops.sim.faults import FaultRegistry, FaultType

DETECTOR_FOR_FAULT: dict[FaultType, str] = {
    FaultType.BATTERY_CAPACITY_FADE: "capacity_fade",
    FaultType.STUCK_TEMPERATURE_SENSOR: "stuck_sensor",
    FaultType.THERMAL_RUNAWAY: "thermal_runaway",
}


@dataclass(slots=True)
class DetectorScorecard:
    detector_name: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    latencies_seconds: list[float] = field(default_factory=list)

    @property
    def recall(self) -> float:
        tp_fn = self.true_positives + self.false_negatives
        return self.true_positives / tp_fn if tp_fn else 1.0

    @property
    def precision(self) -> float:
        tp_fp = self.true_positives + self.false_positives
        return self.true_positives / tp_fp if tp_fp else 1.0

    @property
    def mean_latency_seconds(self) -> float | None:
        return (
            sum(self.latencies_seconds) / len(self.latencies_seconds)
            if self.latencies_seconds
            else None
        )


def evaluate(
    events: list[AnomalyEvent],
    faults: FaultRegistry,
) -> dict[str, DetectorScorecard]:
    """Compute per-detector scorecards."""
    scorecards: dict[str, DetectorScorecard] = {
        name: DetectorScorecard(detector_name=name)
        for name in DETECTOR_FOR_FAULT.values()
    }

    # Index events by (sat_id, detector_name)
    events_by_key: dict[tuple[str, str], list[AnomalyEvent]] = {}
    for e in events:
        events_by_key.setdefault((e.sat_id, e.detector_name), []).append(e)

    # Index ground-truth fault windows
    faults_by_key: dict[tuple[str, str], list] = {}
    for spec in faults.specs:
        detector_name = DETECTOR_FOR_FAULT[spec.fault_type]
        faults_by_key.setdefault((spec.sat_id, detector_name), []).append(spec)

    # Score each detector's events
    for (sat, det), evts in events_by_key.items():
        sc = scorecards[det]
        fault_specs = faults_by_key.get((sat, det), [])
        if not fault_specs:
            sc.false_positives += len(evts)
            continue
        earliest_fault_start = min(s.start for s in fault_specs)
        for e in evts:
            event_time = datetime.fromisoformat(e.sim_time_iso)
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=UTC)
            if event_time >= earliest_fault_start:
                sc.true_positives += 1
                sc.latencies_seconds.append(
                    (event_time - earliest_fault_start).total_seconds()
                )
            else:
                sc.false_positives += 1

    # Score missed faults (false negatives)
    for (sat, det), fault_specs in faults_by_key.items():
        sc = scorecards[det]
        evts = events_by_key.get((sat, det), [])
        if not any(
            datetime.fromisoformat(e.sim_time_iso).replace(tzinfo=UTC)
            >= min(s.start for s in fault_specs)
            for e in evts
        ):
            sc.false_negatives += len(fault_specs)

    return scorecards
