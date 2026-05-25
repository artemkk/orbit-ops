"""CLI entrypoint. Wired up incrementally as the sim and pipeline come online."""

from __future__ import annotations

import typer

app = typer.Typer(help="orbit-ops command line")
sim_app = typer.Typer(help="simulator commands")
pipeline_app = typer.Typer(help="pipeline commands")
app.add_typer(sim_app, name="sim")
app.add_typer(pipeline_app, name="pipeline")


@sim_app.command("run")
def sim_run() -> None:
    """Run the simulator. Stub — implemented in week 1, days 2–3."""
    typer.echo("sim run: not implemented yet")
    raise typer.Exit(code=1)


@pipeline_app.command("consume")
def pipeline_consume() -> None:
    """Consume from Redpanda and write Parquet. Stub — implemented day 5."""
    typer.echo("pipeline consume: not implemented yet")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
