"""Anomaly detection package.

One detector class per fault type. Each detector is stateful per (sat_id,
detector_type) and consumes a stream of mart-grain samples (per-sat,
per-minute rollups). On each sample, it returns either an AnomalyEvent or
None.

The detection method per detector is deliberately different:

- CapacityFadeDetector: CUSUM on rolling max-SoC. Catches slow drift.
- StuckSensorDetector: residual between predicted and actual temperature
  change. Catches lost correlation.
- ThermalRunawayDetector: threshold + slope. Catches monotonic excursions.

The variety is the point: pragmatic anomaly detection picks the right tool
per signal shape, not one tool for everything.
"""

from orbit_ops.detection.detectors import (
    CapacityFadeDetector,
    StuckSensorDetector,
    ThermalRunawayDetector,
)
from orbit_ops.detection.events import AnomalyEvent, AnomalySeverity

__all__ = [
    "AnomalyEvent",
    "AnomalySeverity",
    "CapacityFadeDetector",
    "StuckSensorDetector",
    "ThermalRunawayDetector",
]
