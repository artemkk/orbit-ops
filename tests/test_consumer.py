"""Unit tests for TelemetryConsumer using FakeSource + LocalParquetWriter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from orbit_ops.pipeline.batcher import ParquetBatcher
from orbit_ops.pipeline.consumer import FakeSource, TelemetryConsumer
from orbit_ops.pipeline.messages import TelemetryRecord
from orbit_ops.pipeline.storage import LocalParquetWriter


def _make_message(sat_id: str, t: datetime) -> tuple[bytes, bytes]:
    rec = TelemetryRecord(
        sat_id=sat_id,
        sim_time_iso=t.isoformat(),
        position_eci_km_x=7000.0, position_eci_km_y=0.0, position_eci_km_z=0.0,
        velocity_eci_km_s_x=0.0, velocity_eci_km_s_y=7.5, velocity_eci_km_s_z=0.0,
        sun_vector_eci_x=1.0, sun_vector_eci_y=0.0, sun_vector_eci_z=0.0,
        eclipsed=False, latitude_deg=0.0, longitude_deg=0.0, altitude_km=550.0,
        solar_power_w=200.0, bus_power_w=90.0, net_power_w=110.0,
        battery_soc=0.85, battery_charge_wh=127.5,
        bus_temperature_k=288.0, bus_temperature_c=14.85,
        solar_heat_input_w=190.0, earth_ir_input_w=100.0,
        radiative_heat_output_w=320.0, net_heat_w=0.0,
    )
    return sat_id.encode(), rec.to_json_bytes()


def test_consumer_drains_source_and_writes_parquet(tmp_path: Path) -> None:
    msgs = [_make_message(
        f"SKYSAT-{i % 3 + 1}",
        datetime(2026, 5, 24, 14, i % 60, 0, tzinfo=UTC),
    ) for i in range(30)]
    # Plus one in the next hour to trigger flushes for hour=14:
    msgs.append(_make_message("SKYSAT-1", datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC)))
    msgs.append(_make_message("SKYSAT-2", datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC)))
    msgs.append(_make_message("SKYSAT-3", datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC)))

    source = FakeSource(messages=msgs)
    writer = LocalParquetWriter(str(tmp_path))
    batcher = ParquetBatcher(writer)
    consumer = TelemetryConsumer(source, batcher, idle_polls_before_exit=2)

    stats = consumer.run()
    assert stats.messages_received == len(msgs)
    assert stats.decode_errors == 0
    assert batcher.stats.rows_flushed == len(msgs)
    # Three sats x two hours = 6 files
    written = list(tmp_path.rglob("*.parquet"))
    assert len(written) == 6


def test_consumer_partition_layout_is_hive_compatible(tmp_path: Path) -> None:
    msgs = [
        _make_message("SKYSAT-1", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC)),
        _make_message("SKYSAT-1", datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC)),
    ]
    source = FakeSource(messages=msgs)
    writer = LocalParquetWriter(str(tmp_path))
    batcher = ParquetBatcher(writer)
    consumer = TelemetryConsumer(source, batcher, idle_polls_before_exit=2)
    consumer.run()

    paths = [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.parquet")]
    assert any("sat_id=SKYSAT-1/date=2026-05-24/hour=14/" in p for p in paths)


def test_consumer_round_trips_records_via_duckdb(tmp_path: Path) -> None:
    """The bytes-in-equals-bytes-out invariant: produce N records, consume, query."""
    msgs = [_make_message(
        "SKYSAT-1",
        datetime(2026, 5, 24, 14, i, 0, tzinfo=UTC),
    ) for i in range(50)]
    # Roll-forward message to force hour=14 flush
    msgs.append(_make_message("SKYSAT-1", datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC)))

    source = FakeSource(messages=msgs)
    writer = LocalParquetWriter(str(tmp_path))
    batcher = ParquetBatcher(writer)
    consumer = TelemetryConsumer(source, batcher, idle_polls_before_exit=2)
    consumer.run()

    con = duckdb.connect()
    pattern = str(tmp_path / "**" / "*.parquet").replace("\\", "/")
    result = con.execute(
        f"SELECT count(*) AS n, count(DISTINCT sim_time_iso) AS distinct_times "
        f"FROM read_parquet('{pattern}', hive_partitioning=true) "
        f"WHERE sat_id = 'SKYSAT-1'"
    ).fetchone()
    n_rows, n_distinct_times = result
    assert n_rows == len(msgs)
    assert n_distinct_times == len(msgs)


def test_consumer_handles_bad_message_without_crashing(tmp_path: Path) -> None:
    good = _make_message("SKYSAT-1", datetime(2026, 5, 24, 14, 0, 0, tzinfo=UTC))
    bad_json = (b"SKYSAT-1", b"not valid json {")
    missing_field = (b"SKYSAT-1", json.dumps({"sat_id": "SKYSAT-1"}).encode())
    next_hour = _make_message("SKYSAT-1", datetime(2026, 5, 24, 15, 0, 0, tzinfo=UTC))

    source = FakeSource(messages=[good, bad_json, missing_field, next_hour])
    writer = LocalParquetWriter(str(tmp_path))
    batcher = ParquetBatcher(writer)
    consumer = TelemetryConsumer(source, batcher, idle_polls_before_exit=2)
    stats = consumer.run()

    assert stats.messages_received == 2  # good and next_hour
    assert stats.decode_errors == 2
