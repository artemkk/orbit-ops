"""Run detectors against the sat_minute_rollup mart, write events to Parquet.

The runner is intentionally batch-oriented: it reads the full marts table,
iterates sat-by-sat in time order, feeds each row to one instance of each
detector. Events are accumulated in memory and flushed to a single Parquet
file per run.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from orbit_ops.detection.detectors import (
    CapacityFadeDetector,
    StuckSensorDetector,
    ThermalRunawayDetector,
)
from orbit_ops.detection.events import AnomalyEvent

log = logging.getLogger(__name__)


EVENTS_SCHEMA = pa.schema([
    pa.field("sat_id", pa.string(), nullable=False),
    pa.field("detector_name", pa.string(), nullable=False),
    pa.field("sim_time_iso", pa.string(), nullable=False),
    pa.field("severity", pa.string(), nullable=False),
    pa.field("score", pa.float64(), nullable=False),
    pa.field("description", pa.string(), nullable=False),
])


@dataclass(slots=True)
class RunnerStats:
    sats_processed: int = 0
    rows_consumed: int = 0
    events_emitted: int = 0


def _make_detectors(sat_id: str) -> list:
    """One instance of each detector class, scoped to a sat."""
    return [
        CapacityFadeDetector(sat_id=sat_id),
        StuckSensorDetector(sat_id=sat_id),
        ThermalRunawayDetector(sat_id=sat_id),
    ]


def run_detection(
    marts_glob: str,
    *,
    duckdb_settings: dict[str, str] | None = None,
) -> tuple[list[AnomalyEvent], RunnerStats]:
    """Read the minute-rollup mart and run all detectors."""
    import duckdb

    con = duckdb.connect()
    if duckdb_settings:
        for k, v in duckdb_settings.items():
            con.execute(f"SET {k} = '{v}'")
        if any(k.startswith("s3_") for k in duckdb_settings):
            con.execute("INSTALL httpfs; LOAD httpfs")

    rows = con.execute(
        f"""
        SELECT sat_id, minute_bucket, battery_soc_mean,
               bus_temperature_k_mean, net_heat_w_mean
        FROM read_parquet('{marts_glob}')
        ORDER BY sat_id, minute_bucket
        """
    ).fetchall()

    events: list[AnomalyEvent] = []
    stats = RunnerStats(rows_consumed=len(rows))

    current_sat: str | None = None
    detectors: list = []

    for row in rows:
        sat_id, minute_bucket, soc, temp_k, net_heat = row
        if sat_id != current_sat:
            current_sat = sat_id
            detectors = _make_detectors(sat_id)
            stats.sats_processed += 1

        sample = {
            "minute_bucket": minute_bucket,
            "battery_soc_mean": soc,
            "bus_temperature_k_mean": temp_k,
            "net_heat_w_mean": net_heat,
        }
        for d in detectors:
            event = d.update(sample)
            if event is not None:
                events.append(event)
                stats.events_emitted += 1
                log.info(
                    "Event: %s %s @ %s", event.sat_id, event.detector_name, event.sim_time_iso
                )

    return events, stats


def write_events_parquet(events: list[AnomalyEvent], out_path: Path) -> int:
    """Write events to a Parquet file. Returns bytes written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for e in events:
        d = asdict(e)
        d["severity"] = e.severity.value if hasattr(e.severity, "value") else str(e.severity)
        rows.append(d)
    table = pa.Table.from_pylist(rows, schema=EVENTS_SCHEMA)
    pq.write_table(table, str(out_path), compression="zstd")
    return out_path.stat().st_size
