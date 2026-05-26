"""End-to-end pipeline integration test.

Producer -> Redpanda -> Consumer -> MinIO -> DuckDB round trip.

Skips cleanly if Redpanda or MinIO aren't reachable on localhost.
"""

from __future__ import annotations

import os
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from orbit_ops.common.clock import ClockMode, SimClock
from orbit_ops.pipeline.batcher import ParquetBatcher
from orbit_ops.pipeline.consumer import KafkaSource, TelemetryConsumer
from orbit_ops.pipeline.producer import ConstellationProducer, KafkaSink
from orbit_ops.pipeline.storage import S3Config, S3ParquetWriter
from orbit_ops.sim.constellation import Constellation

TLE_PATH = Path(__file__).resolve().parent.parent / "data" / "tle" / "planet.tle"


def _reachable(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


@pytest.mark.integration
def test_full_pipeline_round_trip() -> None:
    """Skips unless both Redpanda (19092) and MinIO (9000) are up locally."""
    brokers = os.environ.get("REDPANDA_BROKERS", "localhost:19092")
    minio = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    rp_host, _, rp_port = brokers.partition(":")
    mn_stripped = minio.replace("http://", "").replace("https://", "")
    mn_host = mn_stripped.split(":")[0]
    mn_port = int(mn_stripped.split(":")[1]) if ":" in mn_stripped else 9000

    if not _reachable(rp_host, int(rp_port)):
        pytest.skip(f"redpanda not reachable at {brokers}")
    if not _reachable(mn_host, mn_port):
        pytest.skip(f"minio not reachable at {minio}")
    if not TLE_PATH.exists():
        pytest.skip("no TLE file; run `make tle`")

    # Unique consumer group per run to avoid cross-test pollution
    run_id = f"e2e-{int(time.time())}"

    # 1. Produce a small fleet's worth of telemetry for a few ticks
    clock = SimClock(
        start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        tick_seconds=60.0,
        mode=ClockMode.FAST,
    )
    con = Constellation.from_tle_file(TLE_PATH, clock, name_filter="SKYSAT", limit=2)
    sink = KafkaSink(brokers, client_id=f"orbit-ops-{run_id}")
    producer = ConstellationProducer(con, sink)
    stats_prod = producer.run(max_ticks=5)
    assert stats_prod.messages_sent == 10  # 2 sats x 5 ticks

    # 2. Consume them back and write to MinIO
    s3 = S3Config.from_env()
    writer = S3ParquetWriter(s3)
    batcher = ParquetBatcher(writer)
    source = KafkaSource(brokers, group_id=run_id, from_beginning=True)
    consumer = TelemetryConsumer(
        source, batcher, poll_timeout_s=1.0, idle_polls_before_exit=5
    )
    stats_cons = consumer.run()
    assert stats_cons.messages_received >= 10
    assert stats_cons.decode_errors == 0

    # 3. Query the resulting Parquet via DuckDB
    duck = duckdb.connect()
    s3_endpoint = s3.endpoint_url.replace("http://", "").replace("https://", "")
    duck.execute(f"""
        INSTALL httpfs; LOAD httpfs;
        SET s3_url_style = 'path';
        SET s3_endpoint = '{s3_endpoint}';
        SET s3_access_key_id = '{s3.access_key}';
        SET s3_secret_access_key = '{s3.secret_key}';
        SET s3_use_ssl = false;
    """)
    glob = f"s3://{s3.bucket}/sat_id=*/date=*/hour=*/*.parquet"
    n = duck.execute(
        f"SELECT count(*) FROM read_parquet('{glob}', hive_partitioning=true)"
    ).fetchone()[0]
    assert n >= 10, f"expected >= 10 rows in Parquet, found {n}"
