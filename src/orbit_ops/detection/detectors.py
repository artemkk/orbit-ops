"""Three anomaly detectors, one per fault type.

Each detector exposes the same interface:

    detector.update(sample: dict) -> AnomalyEvent | None

`sample` is one row from the `sat_minute_rollup` mart -- a dict keyed by the
mart's column names. The detector decides whether this sample's arrival
warrants firing an event.

State lives in the detector instance. One instance per (sat_id, fault_type).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from orbit_ops.detection.events import AnomalyEvent, AnomalySeverity

# ---------------------------------------------------------------------------
# Capacity fade -- CUSUM on rolling max battery SoC
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CapacityFadeDetector:
    """CUSUM detector for battery capacity fade.

    Watches the per-minute mart for the running maximum of battery_soc_mean
    over a `window_minutes` lookback. Capacity fade causes this running-max
    to drift downward over many orbits. CUSUM accumulates the deviation
    from a slack-adjusted baseline; when the cumulative deviation crosses
    `threshold`, fires.

    Why CUSUM here:
    - The fade signal is slow and noisy; per-minute SoC values vary widely.
    - Traditional Z-score detectors miss slow drift because the standard
      deviation absorbs it.
    - CUSUM is mathematically designed for "detect a sustained shift in
      the mean of a noisy signal," which is exactly the fade profile.

    Score: cumulative downward deviation in SoC units.
    """

    sat_id: str
    threshold: float = 0.10
    """Cumulative deviation threshold for firing (SoC units)."""
    slack: float = 0.001
    """Slack term subtracted each sample to prevent noise accumulation."""
    window_minutes: int = 90
    """Lookback for the running max (1 orbital period ~ 90 minutes)."""
    detector_name: str = "capacity_fade"

    _window: deque[float] = field(default_factory=deque, init=False)
    _baseline: float | None = field(default=None, init=False)
    _cusum: float = field(default=0.0, init=False)
    _fired: bool = field(default=False, init=False)

    def update(self, sample: dict) -> AnomalyEvent | None:
        soc = float(sample["battery_soc_mean"])
        self._window.append(soc)
        while len(self._window) > self.window_minutes:
            self._window.popleft()

        if len(self._window) < self.window_minutes:
            return None

        current_max = max(self._window)

        if self._baseline is None:
            self._baseline = current_max
            return None

        deviation = self._baseline - current_max
        self._cusum = max(0.0, self._cusum + deviation - self.slack)

        if self._cusum >= self.threshold and not self._fired:
            self._fired = True
            return AnomalyEvent(
                sat_id=self.sat_id,
                detector_name=self.detector_name,
                sim_time_iso=str(sample["minute_bucket"]),
                severity=AnomalySeverity.WARNING,
                score=self._cusum,
                description=(
                    f"Battery SoC ceiling drifted by {self._cusum:.3f} from baseline "
                    f"{self._baseline:.3f}; consistent with capacity fade."
                ),
            )
        return None


# ---------------------------------------------------------------------------
# Stuck sensor -- cross-channel residual
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class StuckSensorDetector:
    """Detector for stuck temperature sensors via cross-channel residual.

    The thermal model says:
        dT ~ net_heat_w * dt / (m * c)
    Given the reported `net_heat_w_mean` and a known thermal mass, we
    *expect* a per-minute temperature change. If the reported temperature
    isn't moving while we expect it to, the residual builds. Sustained
    residual = stuck sensor.

    Why residual here:
    - A stuck sensor reads a plausible value; threshold detectors miss it.
    - Z-score on the temperature itself misses it (the value is fine).
    - But the correlation with the other channels is broken, and that's
      observable as soon as you compute the expected change.

    Score: absolute residual in K, accumulated over a short window.
    """

    sat_id: str
    thermal_mass_j_per_k: float = 110.0 * 900.0
    """m * c for the bus. Defaults to SkySat-class values from subsystem_params."""
    residual_threshold_k: float = 0.1
    """Per-minute residual threshold (K). Calibrated above eclipse-transition
    residual noise (observed up to ~0.15 K on nominal sats) and below
    sustained stuck-sensor signal (multi-K during heat swings). The
    threshold is empirical against the modeled SkySat bus."""
    consecutive_minutes_required: int = 5
    """Number of consecutive minutes above threshold before firing.
    Suppresses false positives from numerical noise."""
    detector_name: str = "stuck_sensor"

    _last_temp_k: float | None = field(default=None, init=False)
    _consecutive_count: int = field(default=0, init=False)
    _fired: bool = field(default=False, init=False)

    def update(self, sample: dict) -> AnomalyEvent | None:
        temp_k = float(sample["bus_temperature_k_mean"])
        net_heat_w = float(sample["net_heat_w_mean"])

        if self._last_temp_k is None:
            self._last_temp_k = temp_k
            return None

        dt_s = 60.0
        expected_delta = net_heat_w * dt_s / self.thermal_mass_j_per_k
        actual_delta = temp_k - self._last_temp_k
        residual_k = abs(expected_delta - actual_delta)

        if residual_k > self.residual_threshold_k and abs(expected_delta) > 0.01:
            self._consecutive_count += 1
        else:
            self._consecutive_count = 0

        self._last_temp_k = temp_k

        if self._consecutive_count >= self.consecutive_minutes_required and not self._fired:
            self._fired = True
            return AnomalyEvent(
                sat_id=self.sat_id,
                detector_name=self.detector_name,
                sim_time_iso=str(sample["minute_bucket"]),
                severity=AnomalySeverity.CRITICAL,
                score=residual_k,
                description=(
                    f"Temperature held while heat balance predicts movement; "
                    f"residual {residual_k:.2f} K sustained for "
                    f"{self._consecutive_count} minutes."
                ),
            )
        return None


# ---------------------------------------------------------------------------
# Thermal runaway -- threshold + slope
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ThermalRunawayDetector:
    """Threshold + slope detector for thermal runaway.

    Fires when:
    1. bus_temperature_c exceeds `temperature_ceiling_c`, AND
    2. the recent slope of temperature over `slope_window_minutes` is
       positive (the excursion is ongoing, not transient).

    Why threshold here:
    - Thermal runaway is a hard operational-limit excursion. The bus
      shouldn't be above 50 C. Period. A threshold catches this directly.
    - Adding the slope check suppresses false positives from normal sunlit
      warming that briefly grazes the ceiling.
    - This is the case where ML would be silly. The interview defense is
      explicit: pick thresholds where thresholds work.

    Score: degrees above ceiling.
    """

    sat_id: str
    temperature_ceiling_c: float = 35.0
    slope_window_minutes: int = 5
    """Window for computing recent dT/dt."""
    min_positive_slope_k_per_min: float = 0.04
    """Minimum positive slope (K/min) to confirm runaway is ongoing. Calibrated
    below the demo's runaway rate (0.058 K/min from a 3.5 K/hr bias) while
    staying above normal sunlit warming, which in the modeled SkySat thermal
    mass produces slopes well under 0.02 K/min. The slope check exists to
    suppress false positives from brief transient excursions; it should not
    gate true monotonic runaway."""
    detector_name: str = "thermal_runaway"

    _window: deque[float] = field(default_factory=deque, init=False)
    _fired: bool = field(default=False, init=False)

    def update(self, sample: dict) -> AnomalyEvent | None:
        temp_c = float(sample["bus_temperature_k_mean"]) - 273.15
        self._window.append(temp_c)
        while len(self._window) > self.slope_window_minutes:
            self._window.popleft()

        if temp_c <= self.temperature_ceiling_c:
            return None
        if len(self._window) < self.slope_window_minutes:
            return None

        slope = (self._window[-1] - self._window[0]) / (self.slope_window_minutes - 1)
        if slope < self.min_positive_slope_k_per_min:
            return None

        if not self._fired:
            self._fired = True
            return AnomalyEvent(
                sat_id=self.sat_id,
                detector_name=self.detector_name,
                sim_time_iso=str(sample["minute_bucket"]),
                severity=AnomalySeverity.CRITICAL,
                score=temp_c - self.temperature_ceiling_c,
                description=(
                    f"Bus temperature {temp_c:.1f} C exceeds ceiling "
                    f"{self.temperature_ceiling_c:.1f} C with positive slope "
                    f"{slope:.2f} K/min."
                ),
            )
        return None
