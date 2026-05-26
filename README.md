# orbit-ops

A simulated satellite constellation and the data platform that operates it.

10–20 virtual satellites generate physically realistic telemetry — power, thermal, attitude, comms — based on real orbits propagated from public TLE data. That telemetry streams through a production-shaped pipeline (Redpanda → Parquet on object storage → dbt transformations → DuckDB queries → Grafana dashboards). Per-subsystem anomaly detection catches deliberately injected faults: battery degradation, stuck sensors, thermal runaway, attitude excursions.

## Status

Feature-complete through Sprint 2. See [docs/PLAN.md](docs/PLAN.md) for the
full build plan and [docs/PROMPT_LEDGER.md](docs/PROMPT_LEDGER.md) for the
build log.

## Quick start

```bash
make demo-full   # full demo: stack + sim + consume + transform + detect
open http://localhost:3000   # Grafana dashboards
make stop        # tear down
```

Or step-by-step:

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

## Telemetry sample

One SkySat propagated over ~3 orbits. Battery state-of-charge and bus
temperature respond to eclipse passages (shaded). The coupling is
emergent — nothing in the EPS or thermal code explicitly says "go down
in eclipse"; that pattern falls out of the physics.

![Orbit eclipse response](docs/figures/orbit_eclipse.png)

## Fault injection

To validate the anomaly detection layer, the simulator can inject realistic faults
on configured satellites. Faults are layered on top of nominal physics — the
underlying model stays correct; the observed telemetry is what diverges, matching
how real anomalies present (the sensor lies, the cell degrades, the truth state
is what it is).

Three fault types are currently supported, each chosen to exercise a different
class of detection method:

| Fault | Symptom | Natural detection method |
|---|---|---|
| Battery capacity fade | Reported SoC ceiling drops over many sim-days | Change-point (CUSUM, Page-Hinkley) |
| Stuck temperature sensor | Temperature reading held while underlying physics moves | Cross-channel residual |
| Thermal runaway | Monotonic bias growth past operational envelope | Threshold |

Fault configuration is declarative — see `data/faults.example.yaml` for the schema.
Activate by copying to `data/faults.yaml` and re-running the simulator.

![Fault signatures](docs/figures/fault_signatures.png)

## Anomaly detection

Each fault class is matched with a detection method appropriate to its
signal shape. The matrix below summarizes the choice rationale; the
figure shows current performance against the example fault configuration.

| Detector | Method | Why this method |
|---|---|---|
| Capacity fade | CUSUM on rolling max-SoC | Slow drift in a noisy signal; designed for sustained-shift detection |
| Stuck sensor | Cross-channel residual vs heat-balance model | The value is plausible; the *correlation* is broken |
| Thermal runaway | Threshold + slope check | Operational limits are known; ML is not the answer to every problem |

![Detector performance](docs/figures/detector_performance.png)

The evaluator joins detector outputs against the fault YAML (ground truth)
to compute per-detector confusion outcomes and detection latency.

## Dashboards

Three Grafana dashboards, JSON-provisioned and version-controlled in
`dashboards/grafana/`. Auto-loaded on container start.

| Dashboard | Purpose |
|---|---|
| Fleet view | "Is anything wrong right now" -- table of all sats with health-band coloring |
| Satellite drilldown | Pick one sat, see all its telemetry + recent events |
| Anomaly feed | Chronological log of detector firings across the fleet |

Grafana queries the marts Parquet files directly via the DuckDB datasource
plugin -- no separate query service. Honors the project's "everything
queryable from object storage" architectural constraint.

To see the dashboards with real data:

```bash
make demo-full
open http://localhost:3000
```

`make demo-full` brings up the stack, runs a 6-hour sim with the example
faults active, consumes, transforms, and runs detection. After it completes,
all three dashboards have populated panels.

## Design decisions

### Why DuckDB (and not ClickHouse)

ClickHouse is the better production OLAP engine for sustained high-throughput
queries. But this project's scale is 15 satellites at 1 Hz = 15 msgs/sec.
DuckDB is embedded, zero-ops, and reads Parquet directly from object storage.
An interviewer can `make demo-full` on their laptop without provisioning a
database server. ClickHouse would be the right upgrade if message rate grew
10-100x; DuckDB's ceiling is higher than this project will hit.

### Why dbt against Parquet (and not streaming SQL)

dbt is batch-native. Streaming SQL (ksqlDB, Flink SQL) would let us compute
rolling aggregates in real time. But the telemetry archive is Parquet on
object storage, and the transformations are analytical (aggregations, joins,
window functions) not event-driven. dbt-duckdb reads the Parquet directly;
the output marts land back as Parquet. The entire transformation layer is a
SQL project with version-controlled models, declarative tests, and a
`dbt run` that an interviewer can invoke without understanding streaming
infrastructure. Streaming SQL would be the right choice if detection latency
mattered at the sub-minute level; at the per-minute mart grain it doesn't.

### Per-subsystem detection method justification

One method per fault, not one method for all:

- **CUSUM** for capacity fade. The signal is slow drift buried in orbital
  noise. CUSUM accumulates evidence of a sustained mean shift; Z-scores
  absorb drift into their standard deviation and miss it.
- **Cross-channel residual** for stuck sensors. The reading is plausible
  in isolation; what breaks is the correlation with the heat-balance model.
  Threshold and Z-score detectors both miss this. The residual between
  predicted and actual temperature change catches it cleanly.
- **Threshold + slope** for thermal runaway. The operational limit is
  known (35 C bus ceiling). ML is not the answer to every problem. The
  slope check suppresses false positives from normal sunlit warming.

The variety is deliberate: it demonstrates method selection, not toolkit
familiarity.

### Partitioning scheme rationale

`sat_id=X/date=Y/hour=HH/part-NNNN.parquet` (Hive-style). Defense:

- `sat_id` is the most common filter (per-sat queries dominate ops).
- `date` + `hour` together give time-pruning for both daily and intra-day
  queries without the file-count explosion of per-minute partitions.
- Hive layout is natively understood by DuckDB, Spark, ClickHouse, Athena.
  No custom reader needed.

### Sim-clock vs wall-clock separation

`SimClock` is the single most important architectural decision. Every
component that needs "what time is it in the sim" reads from `SimClock.now`.
Wall-clock time (`time.time()`, `datetime.now()`) is forbidden downstream.

This lets the same producer code drive:
- **FAST mode**: generate a week of telemetry in 5 minutes of wall time.
- **REALTIME mode**: 1 sim-second per 1 wall-second for the live demo.

The separation is enforced by the deadline-based tick scheduler (not naive
sleep-after-tick), which absorbs work done between ticks so wall-time
tracks sim-time under load.

## Project context

Portfolio project targeting a data software role at a smallsat operator. The brief: demonstrate space-domain literacy, real data engineering practice, pragmatic anomaly detection, and the ability to ship something that runs on an interviewer's laptop.

## License

MIT
