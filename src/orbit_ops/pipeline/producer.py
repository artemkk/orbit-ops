"""Constellation producer: run the sim forward, publish telemetry to Redpanda.

The producer owns the tick loop. Each tick, it asks the Constellation for
one TickResult per satellite, wraps each into a TelemetryRecord, and hands
them to a MessageSink. The sink abstracts publishing -- production uses
KafkaSink (publishes to Redpanda); tests use FakeSink (records in memory).
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from dataclasses import dataclass
from typing import Protocol

from orbit_ops.pipeline.messages import TelemetryRecord
from orbit_ops.sim.constellation import Constellation

log = logging.getLogger(__name__)

TOPIC_RAW = "telemetry.raw"


class MessageSink(Protocol):
    """Anything that can accept (key, payload) byte pairs."""

    def send(self, topic: str, key: bytes, value: bytes) -> None: ...

    def flush(self, timeout_s: float = 10.0) -> None: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class FakeSink:
    """In-memory sink for tests. Records every send call as a dict."""

    sent: list[dict[str, object]]

    def __init__(self) -> None:
        self.sent = []

    def send(self, topic: str, key: bytes, value: bytes) -> None:
        self.sent.append({"topic": topic, "key": key.decode(), "value": json.loads(value)})

    def flush(self, timeout_s: float = 10.0) -> None:
        return

    def close(self) -> None:
        return


class KafkaSink:
    """Confluent-kafka-python producer, wrapped to the MessageSink protocol."""

    def __init__(self, brokers: str, *, client_id: str = "orbit-ops-producer") -> None:
        # Import here so unit tests that only use FakeSink don't pay the
        # confluent-kafka import cost.
        from confluent_kafka import Producer

        self._producer = Producer(
            {
                "bootstrap.servers": brokers,
                "client.id": client_id,
                "enable.idempotence": True,
                "linger.ms": 50,
                "compression.type": "zstd",
            }
        )

    def send(self, topic: str, key: bytes, value: bytes) -> None:
        self._producer.produce(topic=topic, key=key, value=value)
        # Drive delivery callbacks; non-blocking.
        self._producer.poll(0)

    def flush(self, timeout_s: float = 10.0) -> None:
        remaining = self._producer.flush(timeout=timeout_s)
        if remaining:
            log.warning("KafkaSink.flush left %d messages unsent", remaining)

    def close(self) -> None:
        self._producer.flush(timeout=10.0)


@dataclass(slots=True)
class ProducerStats:
    ticks: int = 0
    messages_sent: int = 0


class ConstellationProducer:
    """Drives a Constellation forward, publishing one message per (sat, tick)."""

    def __init__(self, constellation: Constellation, sink: MessageSink) -> None:
        self._con = constellation
        self._sink = sink
        self._stats = ProducerStats()
        self._stop_requested = False

    @property
    def stats(self) -> ProducerStats:
        return self._stats

    def request_stop(self) -> None:
        self._stop_requested = True

    def install_signal_handlers(self) -> None:
        """SIGINT / SIGTERM trigger graceful shutdown."""

        def _handler(signum: int, _frame: object) -> None:
            log.info("Signal %d received, requesting stop", signum)
            self.request_stop()

        signal.signal(signal.SIGINT, _handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handler)

    def run(self, *, max_ticks: int | None = None) -> ProducerStats:
        """Run until stopped or max_ticks reached.

        Returns final stats.
        """
        try:
            while not self._stop_requested:
                if max_ticks is not None and self._stats.ticks >= max_ticks:
                    break
                self._tick_once()
            self._sink.flush()
        finally:
            self._sink.close()
        return self._stats

    def _tick_once(self) -> None:
        # `tick()` advances the clock as its last step; sim_time at the moment
        # the geometry was computed is one tick_seconds ago. To attach the
        # *correct* sim-time to each record, snapshot before calling tick().
        sim_time_before = self._con.now
        results = self._con.tick()
        sat_ids = self._con.sat_ids
        for sat_id, tr in zip(sat_ids, results, strict=True):
            record = TelemetryRecord.from_tick(sat_id, sim_time_before, tr)
            self._sink.send(
                TOPIC_RAW,
                key=sat_id.encode("utf-8"),
                value=record.to_json_bytes(),
            )
            self._stats.messages_sent += 1
        self._stats.ticks += 1


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
