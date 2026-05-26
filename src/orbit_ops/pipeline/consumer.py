"""Telemetry consumer: read from Redpanda, batch by partition, write Parquet.

Mirrors the producer's structure. `MessageSource` is the read-side protocol;
`FakeSource` is for tests, `KafkaSource` for production.
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from dataclasses import dataclass
from typing import Protocol

from orbit_ops.pipeline.batcher import ParquetBatcher
from orbit_ops.pipeline.messages import TelemetryRecord
from orbit_ops.pipeline.producer import TOPIC_RAW

log = logging.getLogger(__name__)

CONSUMER_GROUP = "orbit-ops-consumer"


class MessageSource(Protocol):
    """Anything that yields (key, value) byte pairs."""

    def poll(self, timeout_s: float) -> tuple[bytes, bytes] | None:
        """Return a single message, or None on timeout."""
        ...

    def close(self) -> None: ...


@dataclass(slots=True)
class FakeSource:
    """In-memory message source for tests. Drains a pre-loaded list."""

    messages: list[tuple[bytes, bytes]]
    _idx: int = 0

    def poll(self, timeout_s: float) -> tuple[bytes, bytes] | None:
        if self._idx >= len(self.messages):
            return None
        msg = self.messages[self._idx]
        self._idx += 1
        return msg

    def close(self) -> None:
        return


class KafkaSource:
    """confluent-kafka-python consumer wrapped to the MessageSource protocol."""

    def __init__(
        self,
        brokers: str,
        *,
        group_id: str = CONSUMER_GROUP,
        topic: str = TOPIC_RAW,
        from_beginning: bool = True,
    ) -> None:
        from confluent_kafka import Consumer

        self._consumer = Consumer(
            {
                "bootstrap.servers": brokers,
                "group.id": group_id,
                "auto.offset.reset": "earliest" if from_beginning else "latest",
                "enable.auto.commit": True,
            }
        )
        self._consumer.subscribe([topic])

    def poll(self, timeout_s: float) -> tuple[bytes, bytes] | None:
        msg = self._consumer.poll(timeout=timeout_s)
        if msg is None:
            return None
        if msg.error() is not None:
            log.warning("Kafka error: %s", msg.error())
            return None
        return msg.key() or b"", msg.value() or b""

    def close(self) -> None:
        self._consumer.close()


@dataclass(slots=True)
class ConsumerStats:
    polls: int = 0
    messages_received: int = 0
    decode_errors: int = 0


class TelemetryConsumer:
    def __init__(
        self,
        source: MessageSource,
        batcher: ParquetBatcher,
        *,
        poll_timeout_s: float = 1.0,
        idle_polls_before_exit: int | None = None,
    ) -> None:
        """
        Parameters
        ----------
        source : MessageSource
        batcher : ParquetBatcher
        poll_timeout_s : float
            How long to wait per poll for a message.
        idle_polls_before_exit : int | None
            If set, the consumer exits after this many consecutive empty polls.
            Useful for tests and for batch backfills. None = run until signaled.
        """
        self._source = source
        self._batcher = batcher
        self._poll_timeout = poll_timeout_s
        self._idle_limit = idle_polls_before_exit
        self._stats = ConsumerStats()
        self._stop_requested = False

    @property
    def stats(self) -> ConsumerStats:
        return self._stats

    def request_stop(self) -> None:
        self._stop_requested = True

    def install_signal_handlers(self) -> None:
        def _handler(signum: int, _frame: object) -> None:
            log.info("Signal %d received, requesting stop", signum)
            self.request_stop()

        signal.signal(signal.SIGINT, _handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handler)

    def run(self) -> ConsumerStats:
        idle_streak = 0
        try:
            while not self._stop_requested:
                msg = self._source.poll(self._poll_timeout)
                self._stats.polls += 1
                if msg is None:
                    idle_streak += 1
                    if self._idle_limit is not None and idle_streak >= self._idle_limit:
                        log.info("Idle limit reached; exiting consumer loop")
                        break
                    continue
                idle_streak = 0
                key, value = msg
                self._dispatch(key, value)
            self._batcher.flush_all()
        finally:
            self._source.close()
        return self._stats

    def _dispatch(self, key: bytes, value: bytes) -> None:
        try:
            payload = json.loads(value)
            record = _record_from_payload(payload)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            log.warning("Bad message (key=%r): %s", key, e)
            self._stats.decode_errors += 1
            return
        self._batcher.accept(record)
        self._stats.messages_received += 1


def _record_from_payload(payload: dict[str, object]) -> TelemetryRecord:
    """Reconstruct a TelemetryRecord from a JSON dict. KeyError surfaces missing fields."""
    return TelemetryRecord(**payload)  # type: ignore[arg-type]


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
