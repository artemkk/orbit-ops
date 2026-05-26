"""Partitioned in-memory batcher for telemetry messages.

One buffer per (sat_id, sim_date, sim_hour). A buffer flushes when:

1. A new message arrives with a *later* sim-hour for the same sat (the
   hour window has closed). This is the primary mechanism.
2. The buffer exceeds `max_rows_per_batch` (safety net; should be rare).
3. The batcher is asked to flush all buffers (shutdown).

Flushing means: turn the buffer into a PyArrow Table, hand it to the
writer with the Hive-partitioned key
`sat_id=<X>/date=<YYYY-MM-DD>/hour=<HH>/part-<NNNN>.parquet`,
and drop the buffer.

The batcher is sim-time aware. It does not consult wall-clock for any
flush decision; this keeps file boundaries stable whether the producer
runs in FAST or REALTIME mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

import pyarrow as pa

from orbit_ops.pipeline.messages import TelemetryRecord
from orbit_ops.pipeline.parquet_schema import TELEMETRY_SCHEMA

log = logging.getLogger(__name__)


class ParquetSink(Protocol):
    """Anything that accepts a PyArrow table and a key."""

    def write(self, table: pa.Table, key: str) -> int: ...


@dataclass(slots=True)
class _BufferKey:
    """Identifies a partition bucket."""

    sat_id: str
    date: str  # YYYY-MM-DD
    hour: int

    @classmethod
    def from_record(cls, rec: TelemetryRecord) -> _BufferKey:
        dt = datetime.fromisoformat(rec.sim_time_iso)
        return cls(sat_id=rec.sat_id, date=dt.strftime("%Y-%m-%d"), hour=dt.hour)

    def s3_key(self, part: int) -> str:
        return (
            f"sat_id={self.sat_id}/"
            f"date={self.date}/"
            f"hour={self.hour:02d}/"
            f"part-{part:04d}.parquet"
        )

    def hash_tuple(self) -> tuple[str, str, int]:
        return (self.sat_id, self.date, self.hour)


@dataclass(slots=True)
class _Buffer:
    key: _BufferKey
    rows: list[dict[str, object]] = field(default_factory=list)
    part_counter: int = 0


@dataclass(slots=True)
class BatcherStats:
    rows_buffered: int = 0
    rows_flushed: int = 0
    files_written: int = 0
    bytes_written: int = 0


class ParquetBatcher:
    def __init__(
        self,
        sink: ParquetSink,
        *,
        max_rows_per_batch: int = 50_000,
    ) -> None:
        self._sink = sink
        self._max_rows = max_rows_per_batch
        self._buffers: dict[tuple[str, str, int], _Buffer] = {}
        self._stats = BatcherStats()

    @property
    def stats(self) -> BatcherStats:
        return self._stats

    def accept(self, record: TelemetryRecord) -> None:
        """Add a record to its partition buffer. May trigger flushes."""
        bk = _BufferKey.from_record(record)
        ht = bk.hash_tuple()

        # If we have an open buffer for this sat in a *different* (older) hour,
        # close it before opening the new one. We assume per-sat sim-time
        # monotonicity (which the producer guarantees).
        self._close_stale_buffers_for_sat(record.sat_id, bk)

        buf = self._buffers.get(ht)
        if buf is None:
            buf = _Buffer(key=bk)
            self._buffers[ht] = buf

        buf.rows.append(_record_to_dict(record))
        self._stats.rows_buffered += 1

        if len(buf.rows) >= self._max_rows:
            self._flush_buffer(buf)

    def _close_stale_buffers_for_sat(self, sat_id: str, current: _BufferKey) -> None:
        """Flush any open buffers for this sat whose (date, hour) is older than `current`."""
        stale_keys: list[tuple[str, str, int]] = []
        cur_key = (current.date, current.hour)
        for ht, buf in self._buffers.items():
            if buf.key.sat_id != sat_id:
                continue
            if (buf.key.date, buf.key.hour) < cur_key:
                stale_keys.append(ht)
        for ht in stale_keys:
            self._flush_buffer(self._buffers[ht])

    def flush_all(self) -> None:
        """Flush every open buffer. Use on shutdown."""
        for buf in list(self._buffers.values()):
            self._flush_buffer(buf)

    def _flush_buffer(self, buf: _Buffer) -> None:
        if not buf.rows:
            self._buffers.pop(buf.key.hash_tuple(), None)
            return
        table = pa.Table.from_pylist(buf.rows, schema=TELEMETRY_SCHEMA)
        key = buf.key.s3_key(buf.part_counter)
        size = self._sink.write(table, key)
        self._stats.rows_flushed += len(buf.rows)
        self._stats.files_written += 1
        self._stats.bytes_written += size
        log.info("Flushed %d rows to %s (%d bytes)", len(buf.rows), key, size)
        buf.part_counter += 1
        buf.rows = []
        self._buffers.pop(buf.key.hash_tuple(), None)


def _record_to_dict(rec: TelemetryRecord) -> dict[str, object]:
    """TelemetryRecord -> plain dict, for pa.Table.from_pylist."""
    from dataclasses import asdict

    return asdict(rec)
