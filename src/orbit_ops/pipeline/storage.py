"""S3-compatible object storage writer.

Used for both MinIO (local docker stack) and R2 / real S3 (deployed). The
contract is "we write Parquet bytes to a key"; the underlying transport
is identical in both cases.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class S3Config:
    endpoint_url: str
    """E.g. http://localhost:9000 for MinIO, or None to use AWS-default for real S3."""
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"
    """MinIO and R2 both ignore region; AWS requires one."""

    @classmethod
    def from_env(cls) -> S3Config:
        """Build from MINIO_*-prefixed env vars (also used for R2 / S3)."""
        return cls(
            endpoint_url=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
            access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
            secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
            bucket=os.environ.get("MINIO_BUCKET", "telemetry"),
        )


class S3ParquetWriter:
    """Writes PyArrow tables to S3-compatible storage as Parquet."""

    def __init__(self, config: S3Config) -> None:
        import boto3
        from botocore.config import Config as BotoConfig

        self._config = config
        self._client = boto3.client(
            "s3",
            endpoint_url=config.endpoint_url,
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
            config=BotoConfig(signature_version="s3v4"),
        )

    def write(self, table: pa.Table, key: str) -> int:
        """Write a PyArrow table to S3 as a Parquet file. Returns bytes written."""
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="zstd")
        data = buf.getvalue()
        self._client.put_object(Bucket=self._config.bucket, Key=key, Body=data)
        log.info(
            "Wrote s3://%s/%s (%d bytes, %d rows)",
            self._config.bucket, key, len(data), table.num_rows,
        )
        return len(data)


class LocalParquetWriter:
    """Same interface as S3ParquetWriter but writes to the local filesystem.

    Used only by tests. Production always uses S3ParquetWriter.
    """

    def __init__(self, root_dir: str) -> None:
        self._root = root_dir
        os.makedirs(root_dir, exist_ok=True)

    def write(self, table: pa.Table, key: str) -> int:
        path = os.path.join(self._root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pq.write_table(table, path, compression="zstd")
        size = os.path.getsize(path)
        log.info("Wrote %s (%d bytes, %d rows)", path, size, table.num_rows)
        return size
