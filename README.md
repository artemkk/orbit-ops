# orbit-ops

A simulated satellite constellation and the data platform that operates it.

10–20 virtual satellites generate physically realistic telemetry — power, thermal, attitude, comms — based on real orbits propagated from public TLE data. That telemetry streams through a production-shaped pipeline (Redpanda → Parquet on object storage → dbt transformations → DuckDB queries → Grafana dashboards). Per-subsystem anomaly detection catches deliberately injected faults: battery degradation, stuck sensors, thermal runaway, attitude excursions.

## Status

🚧 Under active construction. See [docs/PLAN.md](docs/PLAN.md) for the build plan.

## Quick start

```bash
make demo    # bring up the full stack
make sim     # run the simulator
make stop    # tear down
```

Requires Docker, Docker Compose, and `uv`.

## Architecture

```
TLEs (Celestrak) ──► Sim (Skyfield + subsystem models)
                        │
                        ▼ (per-tick telemetry, keyed by sat_id)
                     Redpanda
                        │
                        ▼ (batched, partitioned writes)
                     Parquet on MinIO/R2
                     sat_id=X/date=Y/hour=Z/
                        │
                        ▼ (scheduled runs)
                     dbt-duckdb (raw → staging → marts)
                        │
                        ├──► Detectors (per-subsystem) ──► anomaly_events
                        │
                        ▼
                     Grafana (fleet → sat → subsystem drilldown)
```

## Design decisions

To be filled in as decisions are made and defended. Sections planned:

- Why DuckDB (and not ClickHouse)
- Why dbt against Parquet (and not streaming SQL)
- Per-subsystem detection method justification
- Partitioning scheme rationale
- Sim-clock vs wall-clock separation

## Project context

Portfolio project targeting a data software role at a smallsat operator. The brief: demonstrate space-domain literacy, real data engineering practice, pragmatic anomaly detection, and the ability to ship something that runs on an interviewer's laptop.

## License

MIT
