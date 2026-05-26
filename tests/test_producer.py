"""Tests for the producer + message schema.

Most tests use FakeSink so they're fast. One integration test attempts
to publish to a real broker and skips cleanly if unreachable.
"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from orbit_ops.common.clock import ClockMode, SimClock
from orbit_ops.pipeline.messages import TelemetryRecord
from orbit_ops.pipeline.producer import (
    TOPIC_RAW,
    ConstellationProducer,
    FakeSink,
)
from orbit_ops.sim.constellation import Constellation

TLE_PATH = Path(__file__).resolve().parent.parent / "data" / "tle" / "planet.tle"


def _con(limit: int = 3) -> Constellation:
    if not TLE_PATH.exists():
        pytest.skip("no TLE file; run `make tle`")
    clock = SimClock(
        start=datetime(2026, 5, 1, 0, 0, 0, tzinfo=UTC),
        tick_seconds=60.0,
        mode=ClockMode.FAST,
    )
    return Constellation.from_tle_file(TLE_PATH, clock, name_filter="SKYSAT", limit=limit)


def test_producer_publishes_one_message_per_sat_per_tick() -> None:
    con = _con(limit=3)
    sink = FakeSink()
    producer = ConstellationProducer(con, sink)
    producer.run(max_ticks=5)
    assert len(sink.sent) == 3 * 5
    assert producer.stats.ticks == 5
    assert producer.stats.messages_sent == 15


def test_producer_keys_messages_by_sat_id() -> None:
    con = _con(limit=3)
    sink = FakeSink()
    producer = ConstellationProducer(con, sink)
    producer.run(max_ticks=1)
    keys = {msg["key"] for msg in sink.sent}
    assert keys == set(con.sat_ids)


def test_producer_publishes_to_telemetry_raw_topic() -> None:
    con = _con(limit=2)
    sink = FakeSink()
    producer = ConstellationProducer(con, sink)
    producer.run(max_ticks=1)
    topics = {msg["topic"] for msg in sink.sent}
    assert topics == {TOPIC_RAW}


def test_message_payload_is_valid_json_with_expected_fields() -> None:
    con = _con(limit=1)
    sink = FakeSink()
    producer = ConstellationProducer(con, sink)
    producer.run(max_ticks=1)
    payload = sink.sent[0]["value"]
    # FakeSink already json.loaded the value.
    assert isinstance(payload, dict)
    expected_fields = {
        "sat_id",
        "sim_time_iso",
        "battery_soc",
        "bus_temperature_k",
        "solar_power_w",
        "eclipsed",
        "latitude_deg",
        "longitude_deg",
        "altitude_km",
    }
    assert expected_fields.issubset(payload.keys())


def test_message_sim_time_advances_with_ticks() -> None:
    con = _con(limit=1)
    sink = FakeSink()
    producer = ConstellationProducer(con, sink)
    producer.run(max_ticks=3)
    times = [msg["value"]["sim_time_iso"] for msg in sink.sent]
    # All sim_times must be unique and strictly increasing for a single sat.
    assert times == sorted(times)
    assert len(set(times)) == 3


def test_producer_stop_request_terminates_loop() -> None:
    con = _con(limit=2)
    sink = FakeSink()
    producer = ConstellationProducer(con, sink)
    producer.request_stop()  # request before run starts
    producer.run(max_ticks=100)
    assert producer.stats.ticks == 0
    assert producer.stats.messages_sent == 0


def test_telemetry_record_from_tick_roundtrip_through_json() -> None:
    con = _con(limit=1)
    results = con.tick()
    record = TelemetryRecord.from_tick(
        con.sat_ids[0], datetime(2026, 5, 1, tzinfo=UTC), results[0]
    )
    raw = record.to_json_bytes()
    decoded = json.loads(raw)
    assert decoded["sat_id"] == con.sat_ids[0]
    assert decoded["sim_time_iso"] == "2026-05-01T00:00:00+00:00"
    assert isinstance(decoded["battery_soc"], (int, float))
    assert isinstance(decoded["eclipsed"], bool)


# ---------- Integration test (skips if broker isn't reachable) ----------


def _broker_reachable(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


@pytest.mark.integration
def test_producer_publishes_to_real_broker() -> None:
    """Requires Redpanda running on localhost:19092 (i.e., `make demo` is up)."""
    brokers = os.environ.get("REDPANDA_BROKERS", "localhost:19092")
    host, _, port_s = brokers.partition(":")
    port = int(port_s) if port_s else 9092
    if not _broker_reachable(host, port):
        pytest.skip(f"broker not reachable at {brokers}; run `make demo` first")

    from orbit_ops.pipeline.producer import KafkaSink

    con = _con(limit=2)
    sink = KafkaSink(brokers, client_id="orbit-ops-test")
    producer = ConstellationProducer(con, sink)
    producer.run(max_ticks=3)
    sink.flush(timeout_s=5.0)
    assert producer.stats.messages_sent == 6
