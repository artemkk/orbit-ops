# Build Plan

## Sprints

**Sprint 1 — Skeleton + subsystems (weeks 1–2, hard push).** End-to-end pipe working with one sat by end of week 1; all four subsystems modeled with realistic coupling and fault injection working across 15 sats by end of week 2.

**Sprint 2 — Transformations + detection (week 3).** dbt models (raw → staging → marts). Four detectors, one per subsystem. Backtested against injected faults with a confusion matrix in the README.

**Sprint 3 — Dashboard + polish (week 4+).** Grafana dashboards (fleet → sat → subsystem). Deployed version hardened. README design-decisions section filled in. 90-second Loom recorded.

## Week 1, day by day

1. **Repo + SimClock.** Repo scaffolded (done). `SimClock` with fast/realtime modes, tested.
2. **Orbit propagation.** Skyfield-backed `Satellite` class yielding position, velocity, sun vector, eclipse flag, sub-satellite point.
3. **EPS + thermal coupling.** Solar array power model, battery SoC integration, one-node thermal model. Verify eclipse is visible in plotted data.
4. **Redpanda + producer.** Docker-compose Redpanda. Producer publishes per-tick telemetry to `telemetry.raw`, keyed by sat_id.
5. **Consumer + Parquet + MinIO.** Docker-compose MinIO. Consumer batches and writes partitioned Parquet. DuckDB reads it back.
6. **Grafana panel + deployed skeleton.** One Grafana panel. Redpanda Cloud + R2 + Grafana Cloud free tiers provisioned and reachable.

Tag `v0.1-skeleton` end of week 1.

## Trickiest parts (de-risk early)

1. Sim time vs wall-clock time — solved by `SimClock` on day 1.
2. Deployed version on free tiers — provisioned skeleton end of week 1, not week 4.
3. Physics coupling (sun → power → SoC; eclipse → thermal) — one full chain working day 3.
4. dbt is batch-native; treat Parquet as the streaming/batch boundary.
5. Anomaly detection per subsystem with explicit method justification, not one generic detector.
6. Fault injection that's plausible (capacity fade, value-held sensors), not cartoonish (NaN, zeros).

## Architectural constraint to honor

Marts live as Parquet on object storage, queried by DuckDB. Never write models to a `.duckdb` file that only one tool can open. This keeps the dashboard layer swappable (Grafana now, possibly a small custom frontend later) without re-engineering the pipeline.
