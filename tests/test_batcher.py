"""Unit tests for ParquetBatcher.

Use a fake sink that captures (table, key) pairs in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pyarrow as pa

from orbit_ops.pipeline.batcher import ParquetBatcher
from orbit_ops.pipeline.messages import TelemetryRecord


@dataclass
class _CapturingSink:
    writes: list[tuple[pa.Table, str]]

    def __init__(self) -> None:
        self.writes = []

    def write(self, table: pa.Table, key: str) -> int:
        self.writes.append((table, key))
        return 42  # pretend size


def _rec(sat_id: str, sim_time: datetime, **overrides: object) -> TelemetryRecord:
    base = dict(
        sat_id=sat_id,
        sim_time_iso=sim_time.isoformat(),
        position_eci_km_x=7000.0,
        position_eci_km_y=0.0,
        position_eci_km_z=0.0,
        velocity_eci_km_s_x=0.0,
        velocity_eci_km_s_y=7.5,
        velocity_eci_km_s_z=0.0,
        sun_vector_eci_x=1.0,
        sun_vector_eci_y=0.0,
        sun_vector_eci_z=0.0,
        eclipsed=False,
        latitude_deg=0.0,
        longitude_deg=0.0,
        altitude_km=550.0,
        solar_power_w=200.0,
        bus_power_w=90.0,
        net_power_w=110.0,
        battery_soc=0.85,
        battery_charge_wh=127.5,
        bus_temperature_k=288.0,
        bus_temperature_c=14.85,
        solar_heat_input_w=190.0,
        earth_ir_input_w=100.0,
        radiative_heat_output_w=320.0,
        net_heat_w=0.0,
    )
    base.update(overrides)
    return TelemetryRecord(**base)  # type: ignore[arg-type]


def test_single_record_buffers_but_does_not_flush() -> None:
    sink = _CapturingSink()
    b = ParquetBatcher(sink)
    b.accept(_rec("SKYSAT-1", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)))
    assert sink.writes == []
    assert b.stats.rows_buffered == 1
    assert b.stats.files_written == 0


def test_hour_rollover_flushes_old_buffer() -> None:
    sink = _CapturingSink()
    b = ParquetBatcher(sink)
    sat = "SKYSAT-1"
    b.accept(_rec(sat, datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)))
    b.accept(_rec(sat, datetime(2026, 5, 24, 14, 30, 0, tzinfo=UTC)))
    assert sink.writes == []  # same hour, no flush
    b.accept(_rec(sat, datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC)))
    assert len(sink.writes) == 1
    table, key = sink.writes[0]
    assert table.num_rows == 2
    assert key == "sat_id=SKYSAT-1/date=2026-05-24/hour=14/part-0000.parquet"


def test_per_sat_partitioning_does_not_cross_sats() -> None:
    sink = _CapturingSink()
    b = ParquetBatcher(sink)
    b.accept(_rec("SKYSAT-1", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)))
    b.accept(_rec("SKYSAT-2", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)))
    # Roll SKYSAT-1's hour forward, leaving SKYSAT-2's buffer intact.
    b.accept(_rec("SKYSAT-1", datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC)))
    assert len(sink.writes) == 1
    _, key = sink.writes[0]
    assert "sat_id=SKYSAT-1" in key
    # SKYSAT-2 still has an open buffer
    assert b.stats.rows_buffered == 3
    assert b.stats.rows_flushed == 1


def test_max_rows_safety_flush() -> None:
    sink = _CapturingSink()
    b = ParquetBatcher(sink, max_rows_per_batch=3)
    for i in range(7):
        # All same sat, same hour -- only max_rows triggers flushes.
        b.accept(_rec("SKYSAT-1", datetime(2026, 5, 24, 14, 0, i, tzinfo=UTC)))
    # 3 flushed -> 4 remaining buffered. Note the safety flush should kick in
    # the moment a buffer crosses the threshold; subsequent rows open a new
    # buffer for the same key.
    assert b.stats.files_written == 2  # rows 1-3 flushed, 4-6 flushed
    assert b.stats.rows_flushed == 6
    assert b.stats.rows_buffered == 7
    # 7th row sits in the new (open) buffer; flush_all picks it up
    b.flush_all()
    assert b.stats.files_written == 3
    assert b.stats.rows_flushed == 7


def test_flush_all_drains_open_buffers() -> None:
    sink = _CapturingSink()
    b = ParquetBatcher(sink)
    b.accept(_rec("SKYSAT-1", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)))
    b.accept(_rec("SKYSAT-2", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)))
    b.flush_all()
    assert len(sink.writes) == 2
    assert {sink.writes[0][1].split("/", 1)[0], sink.writes[1][1].split("/", 1)[0]} == {
        "sat_id=SKYSAT-1",
        "sat_id=SKYSAT-2",
    }


def test_partition_key_format() -> None:
    sink = _CapturingSink()
    b = ParquetBatcher(sink)
    b.accept(_rec("SKYSAT-7", datetime(2026, 5, 24, 9, 15, 0, tzinfo=UTC)))
    b.flush_all()
    _, key = sink.writes[0]
    assert key == "sat_id=SKYSAT-7/date=2026-05-24/hour=09/part-0000.parquet"


def test_table_has_telemetry_schema_columns() -> None:
    sink = _CapturingSink()
    b = ParquetBatcher(sink)
    b.accept(_rec("SKYSAT-1", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)))
    b.flush_all()
    table, _ = sink.writes[0]
    names = set(table.column_names)
    # Spot-check a representative set
    assert {"sat_id", "sim_time_iso", "battery_soc", "bus_temperature_k", "eclipsed"} <= names
