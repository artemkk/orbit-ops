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
    sink = FakeSink() if dry_run else KafkaSink(brokers)
    producer = ConstellationProducer(constellation, sink)
    producer.install_signal_handlers()

    limit_ticks: int | None = None if max_ticks == 0 else max_ticks
    stats = producer.run(max_ticks=limit_ticks)
    typer.echo(
        f"Done. ticks={stats.ticks} messages={stats.messages_sent} "
        f"sats={constellation.size}"
    )


@pipeline_app.command("consume")
def pipeline_consume() -> None:
    """Consume from Redpanda and write Parquet. Stub -- next milestone."""
    typer.echo("pipeline consume: not implemented yet")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
