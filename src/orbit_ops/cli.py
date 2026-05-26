"""CLI entrypoint."""

from __future__ import annotations

import os
from pathlib import Path

import typer

from orbit_ops.common.clock import ClockMode, SimClock
from orbit_ops.pipeline.producer import (
    ConstellationProducer,
    FakeSink,
    KafkaSink,
    setup_logging,
)
from orbit_ops.sim.constellation import Constellation

app = typer.Typer(help="orbit-ops command line")
sim_app = typer.Typer(help="simulator commands")
pipeline_app = typer.Typer(help="pipeline commands")
app.add_typer(sim_app, name="sim")
app.add_typer(pipeline_app, name="pipeline")

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_TLE = REPO / "data" / "tle" / "planet.tle"


@sim_app.command("run")
def sim_run(
    tle_path: Path = typer.Option(
        DEFAULT_TLE,
        "--tle",
        help="Path to a TLE file (3 lines per satellite).",
    ),
    name_filter: str = typer.Option(
        "SKYSAT",
        "--filter",
        help="Substring filter on satellite name. Default keeps only SkySats.",
    ),
    limit: int = typer.Option(
        15,
        "--limit",
        help="Max number of satellites to include.",
    ),
    tick_seconds: float = typer.Option(
        1.0,
        "--tick-seconds",
        help="Sim-seconds per tick.",
    ),
    mode: str = typer.Option(
        "fast",
        "--mode",
        help="Clock mode: fast or realtime.",
    ),
    speedup: float = typer.Option(
        1.0,
        "--speedup",
        help="Realtime mode speedup factor.",
    ),
    max_ticks: int = typer.Option(
        100,
        "--max-ticks",
        help="Number of ticks to run before stopping. Use 0 for unlimited.",
    ),
    brokers: str = typer.Option(
        os.environ.get("REDPANDA_BROKERS", "localhost:19092"),
        "--brokers",
        help="Kafka brokers.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Use the in-memory FakeSink instead of publishing to Kafka.",
    ),
    faults_path: Path = typer.Option(
        Path("data/faults.yaml"),
        "--faults",
        help="Path to fault config YAML. Missing file means no faults.",
    ),
) -> None:
    """Run the constellation simulator and publish telemetry."""
    setup_logging()
    clock = SimClock(
        start=SimClock.utc_now_start().start,
        tick_seconds=tick_seconds,
        mode=ClockMode(mode),
        speedup=speedup,
    )
    constellation = Constellation.from_tle_file(
        tle_path, clock, name_filter=name_filter, limit=limit
    )
    from orbit_ops.sim.faults import FaultRegistry
    faults = FaultRegistry.from_yaml(faults_path)
    if faults.specs:
        typer.echo(f"Loaded {len(faults.specs)} fault spec(s) from {faults_path}")

    sink = FakeSink() if dry_run else KafkaSink(brokers)
    producer = ConstellationProducer(constellation, sink, faults=faults)
    producer.install_signal_handlers()

    limit_ticks: int | None = None if max_ticks == 0 else max_ticks
    stats = producer.run(max_ticks=limit_ticks)
    typer.echo(
        f"Done. ticks={stats.ticks} messages={stats.messages_sent} "
        f"sats={constellation.size}"
    )


@pipeline_app.command("consume")
def pipeline_consume(
    brokers: str = typer.Option(
        os.environ.get("REDPANDA_BROKERS", "localhost:19092"),
        "--brokers",
        help="Kafka brokers.",
    ),
    minio_endpoint: str = typer.Option(
        os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
        "--endpoint",
        help="S3-compatible endpoint URL.",
    ),
    bucket: str = typer.Option(
        os.environ.get("MINIO_BUCKET", "telemetry"),
        "--bucket",
        help="S3 bucket to write Parquet files into.",
    ),
    group_id: str = typer.Option(
        "orbit-ops-consumer",
        "--group",
        help="Kafka consumer group ID.",
    ),
    from_beginning: bool = typer.Option(
        True,
        "--from-beginning/--from-latest",
        help="Read from the start of the topic (default) or only new messages.",
    ),
    max_rows_per_batch: int = typer.Option(
        50_000,
        "--max-rows-per-batch",
        help="Flush a partition buffer when it reaches this row count.",
    ),
    idle_polls_before_exit: int = typer.Option(
        0,
        "--idle-polls-before-exit",
        help="Exit after this many empty polls in a row. 0 = run forever.",
    ),
) -> None:
    """Consume telemetry.raw and write Parquet to S3-compatible storage."""
    from orbit_ops.pipeline.batcher import ParquetBatcher
    from orbit_ops.pipeline.consumer import (
        KafkaSource,
        TelemetryConsumer,
        setup_logging,
    )
    from orbit_ops.pipeline.storage import S3Config, S3ParquetWriter

    setup_logging()
    config = S3Config(
        endpoint_url=minio_endpoint,
        access_key=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        bucket=bucket,
    )
    writer = S3ParquetWriter(config)
    batcher = ParquetBatcher(writer, max_rows_per_batch=max_rows_per_batch)
    source = KafkaSource(brokers, group_id=group_id, from_beginning=from_beginning)
    consumer = TelemetryConsumer(
        source,
        batcher,
        idle_polls_before_exit=idle_polls_before_exit or None,
    )
    consumer.install_signal_handlers()

    stats = consumer.run()
    typer.echo(
        f"Done. polls={stats.polls} messages={stats.messages_received} "
        f"decode_errors={stats.decode_errors} "
        f"files_written={batcher.stats.files_written} "
        f"bytes_written={batcher.stats.bytes_written}"
    )


if __name__ == "__main__":
    app()
