"""Shared types for the detection layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AnomalySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AnomalyEvent:
    """One detector firing.

    Detection outputs are written to Parquet with these fields directly mapped
    to columns. The shape is deliberately flat for the same reason the
    telemetry schema is flat -- column-store friendliness and trivial
    cross-join with mart tables for evaluation.
    """

    sat_id: str
    detector_name: str
    """Identifier of the detector class that fired, e.g. 'capacity_fade'."""
    sim_time_iso: str
    """Sim-time at which the event was emitted."""
    severity: AnomalySeverity
    score: float
    """Detector-specific scalar describing how confident/severe. Units vary
    per detector and are documented in the detector's docstring."""
    description: str
    """Short human-readable explanation."""
