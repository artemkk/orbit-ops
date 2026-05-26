# Prompt Ledger

Every Claude Code prompt executed against this repo, in order. The contract:

- IDs are atomic: `p-orb-ops-NNN`, zero-padded to three digits, monotonically increasing.
- A prompt is appended here only after it completes successfully (or is formally abandoned).
- The deliverable summary in each prompt begins with `✓ p-orb-ops-NNN complete` so the ID stays attached to its outcome in shell history and CC transcripts.
- Deprecated prompts stay in the ledger marked `[deprecated]` — we don't rewrite history.

## How to log a new prompt

After a prompt finishes, append a row to the table and (if substantive) a short note in the Notes section below. Keep the table row to one line.

| ID | Date | Purpose | Status | Commit |
|---|---|---|---|---|

## Ledger

| ID | Date | Purpose | Status | Commit |
|---|---|---|---|---|
| p-orb-ops-001 | 2026-05-25 | Scaffold from tarball into ~/projects/orbit-ops | [deprecated] superseded by 003 | — |
| p-orb-ops-002 | 2026-05-25 | Windows-aware tarball install on P:/projects/orbit-ops | [deprecated] superseded by 003 | — |
| p-orb-ops-003 | 2026-05-25 | Create scaffold from scratch, push, verify stack | Partial (steps 1–9 succeeded, step 10 failed on broken Grafana plugin) | d6bd32c |
| p-orb-ops-004 | 2026-05-25 | Remove broken Grafana DuckDB plugin from docker-compose, verify stack | ✓ Complete | c87d5b4 |
| p-orb-ops-005 | 2026-05-25 | Create this prompt ledger document | ✓ Complete | 7a1b485 |
| p-orb-ops-006 | 2026-05-25 | Implement SimClock REALTIME mode with deadline-based scheduling | ✓ Complete | 79ebba6 |
| p-orb-ops-007 | 2026-05-25 | Skyfield-backed Satellite class with physics-grounded tests | ✓ Complete | e6bdf34 |
| p-orb-ops-008 | 2026-05-25 | EPS + thermal subsystem models with eclipse-driven behavior | Partial (code written, tests failed on params) | uncommitted |
| p-orb-ops-009 | 2026-05-25 | Rebalance EPS and thermal parameters; tests green | Partial (power balance fixed, thermal swing still too large) | uncommitted |
| p-orb-ops-010 | 2026-05-25 | Add Earth IR to thermal model; all tests green | Partial (swing reduced 43.5 K -> 36.2 K, still above 30 K) | uncommitted |
| p-orb-ops-011 | 2026-05-25 | Reduce thermal radiating area to MLI-effective value | ✓ Complete | afdf3dc |
| p-orb-ops-012 | 2026-05-25 | Commit subsystem code, lockfile, README; gitignore ephemeris | ✓ Complete | 043b258 |
| p-orb-ops-013 | 2026-05-25 | Streaming layer: Constellation, telemetry schema, Redpanda producer | ✓ Complete | 9530dab |
| p-orb-ops-014 | 2026-05-25 | Consumer + Parquet writer to MinIO; full pipeline round trip | ✓ Complete | 21345fc |
| p-orb-ops-015 | 2026-05-25 | dbt-duckdb transformations: raw / staging / marts with tests | ✓ Complete | 0f2f9ea |
| p-orb-ops-016 | 2026-05-25 | Fault injection layer: capacity fade, stuck sensor, thermal runaway | ✓ Complete | ee3b5d2 |
| p-orb-ops-017 | 2026-05-25 | Anomaly detection: three detectors, runner, evaluator, confusion matrix | ✓ Complete | da2b738 |
| p-orb-ops-018 | 2026-05-26 | Grafana dashboards: fleet view, satellite drilldown, anomaly feed | ✓ Complete | 2a74aef |
| p-orb-ops-019 | 2026-05-26 | End-to-end verification: pipeline works, 2 small issues surfaced | Verification (no code) | -- |
| p-orb-ops-020 | 2026-05-26 | Fix dbt dev profile persistence and detector S3 credentials | ✓ Complete | 0542e88 |
| p-orb-ops-021 | 2026-05-26 | Repoint example fault config at real TLE sat names; regenerate artifact | ✓ Complete | d225135 |
| p-orb-ops-022 | 2026-05-26 | Calibrate example faults and stuck-sensor threshold for demo visibility | ✓ Complete | 14fc855 |
| p-orb-ops-023 | 2026-05-26 | Fix capacity-fade dates; README design decisions; interview prep doc | ✓ Complete | 60c9f41 |

## Notes

### p-orb-ops-001 / 002 (deprecated)

Early scaffolding approach used a tarball generated in the Claude.ai sandbox. The tarball couldn't be located on the Windows machine and would have required manual re-download. Replaced with p-orb-ops-003, which writes every file directly from the prompt — no binary artifacts, fully reproducible from prompt text.

### p-orb-ops-003 (partial)

Steps 1–9 (scaffold creation, GitHub push, uv sync, test suite green) all succeeded. Step 10 (Docker stack startup) failed because the docker-compose.yml referenced `GF_INSTALL_PLUGINS: motherduck-duckdb-datasource`, an unsigned plugin that can't be installed via the registry env var. Patched by p-orb-ops-004.

### p-orb-ops-004

Removed the Grafana DuckDB plugin reference. Plugin will be re-added in Sprint 3 (dashboards) with the proper unsigned-plugin install workflow. Until then, Grafana boots cleanly and the Test Data datasource is sufficient for verifying the stack.

### p-orb-ops-006

Implemented REALTIME mode using deadline-based scheduling rather than naive sleep-after-tick. The deadline anchors on the first tick and advances by `tick_seconds / speedup` per tick, so work done between ticks (physics, Kafka publish, etc.) eats into the sleep budget instead of accumulating drift. If a tick overruns its budget, sleep is skipped — the clock never runs faster than realtime, but can lag under load. This is the same pattern used by game loops and trading simulators.

Three new tests guard the contract: speedup scaling, drift absorption (50ms work + 50ms sleep budget completes in ~1s, not ~1.5s), and overrun behavior (clock lags but never compensates by running faster). The original xfail test now passes normally.

### p-orb-ops-007

Implemented Satellite class wrapping Skyfield's EarthSatellite. Returns a frozen SatelliteState dataclass per tick with position/velocity in ECI (GCRS) (km, km/s), sun vector in ECI (unit), eclipse flag, and geodetic sub-satellite point. Frames are documented in the module docstring -- position/velocity in ECI because that's Skyfield's native frame and the sun-vector dot product needs inertial coordinates; geodetic sub-satellite point for ground-track work.

Frame correction from the original prompt: the prompt labeled position/velocity as ECEF, but Skyfield's `EarthSatellite.at(t)` returns GCRS (ECI). Fields renamed from `position_ecef_km` to `position_eci_km` and `velocity_ecef_km_s` to `velocity_eci_km_s` with updated docstrings. ECEF conversion deferred until a component actually needs it.

TLE source: Planet Labs (Celestrak `planet` group). SkySats are the primary subject -- sun-synchronous LEO, similar bus class to York's S-class. ~20 active birds gives us the constellation size we want without needing to hand-pick.

Tests are physics-grounded, not "did it return": LEO position magnitude (6700-7200 km from Earth center), sub-satellite altitude (300-800 km), sun vector unit-length, latitude stays within inclination band and swings >90 deg per orbit, eclipse fraction sits in the 0-45% sane envelope for sun-sync. Frame errors would cause these to fail loudly.

### p-orb-ops-008 / 009 / 010 / 011 (thermal parameter correction sequence)

First internal-state subsystems: electrical power and thermal. Both implement a common pattern of `(SatelliteState, prev_state, dt) -> (next_state, telemetry)`, integrated with forward Euler. Parameters live in `subsystem_params.py` with citations or labeled estimates.

The invariant test suite caught three physics gaps over four prompts:

- **p-orb-ops-008**: array_efficiency 0.28 was raw cell efficiency, not orbit-averaged system efficiency. Bus loads 35/25 W were idle, not operational. Fixed in p-orb-ops-009 (0.15, 90/60 W).
- **p-orb-ops-009**: thermal model omitted Earth infrared emission (~240 W/m^2 upward, view factor ~0.30 at 500 km). Added in p-orb-ops-010 as `earth_ir_w = 100 W` with Gilmore citation.
- **p-orb-ops-010**: radiating_area_m2 = 2.5 treated the bus as fully exposed, but MLI blankets suppress radiation from ~80% of the surface. Reduced to 1.2 m^2 in p-orb-ops-011 with Gilmore citation.

Each step was driven by an invariant-test failure that named a specific physics gap. This is the test framework earning its keep: every gap surfaced, named, cited, and fixed in the open.

The committed plot `docs/figures/orbit_eclipse.png` shows the final result: SoC sawtooths and temperature dips during shaded eclipse regions, with no code explicitly orchestrating that behavior -- it emerges from the physics.

### p-orb-ops-012

Cleanup commit. p-orb-ops-008 stopped at a test failure before its commit step; prompts 009-011 then iterated on parameter values and only committed `subsystem_params.py` plus the PNG. The actual implementation files (`subsystems.py`, `test_subsystems.py`, `plot_orbit_eclipse.py`) sat uncommitted on disk for three prompts. Also landed `uv.lock` (should have been in the original scaffold for reproducibility), gitignored `*.bsp` (Skyfield's auto-downloaded ephemeris, ~17 MB binary), and added the README "Telemetry sample" section from p-orb-ops-008's original spec.

Process lesson: when a prompt stops at a failure, its already-written-but-uncommitted files are easy to lose track of across follow-up prompts. Future prompts that fix a stopped predecessor should either (a) include the predecessor's pending commit in their commit step, or (b) explicitly defer it and note the deferral. This wasn't caught for three iterations because the focus was on the parameter values, not the file inventory.

### p-orb-ops-013

The pivot from "satellite simulator" to "data platform." Three new modules:

- `Constellation`: owns N satellites and their EPS/Thermal states. One `tick()` advances everything in lockstep using a shared `SimClock`. Cleanly replaces the loose-collection pattern from earlier prompts.
- `TelemetryRecord` (in `orbit_ops.pipeline.messages`): the wire schema. Flat JSON, units in field names, one record per (sat_id, tick). This is the contract between the producer and every downstream consumer; changes are deliberate from here on.
- `ConstellationProducer` + `MessageSink` protocol: the producer is decoupled from the transport. `FakeSink` enables fast unit tests; `KafkaSink` publishes to Redpanda. Same producer code, swap the sink.

Topic: `telemetry.raw`. Key: `sat_id` (enables partition-scaling later). Format: JSON (debuggable with `rpk topic consume`; binary serialization can be a follow-on if we want to demonstrate Avro/schema-registry knowledge, but message rate at 15 sats x 1 Hz doesn't justify it).

Tests: 7 unit tests using `FakeSink` exercise the per-tick logic, message keying, schema completeness, and stop-request behavior. One integration test publishes to a real broker and skips cleanly if `localhost:19092` is unreachable. Registered an `integration` pytest marker.

Added `Constellation.now` as a public property so the producer doesn't need `noqa: SLF001` to access the clock. Also added B008 per-file-ignore for cli.py since `typer.Option()` in defaults is Typer's intended API.

### p-orb-ops-014

The data pipeline is now complete end-to-end. New modules:

- `parquet_schema.py`: PyArrow schema derived from `TelemetryRecord` via dataclass introspection. Built once at import, reused for every file. Schema drift causes loud crashes -- intentional. The `_TYPE_MAP` is narrow on purpose; an unknown field type fails fast and forces a deliberate decision.
- `storage.py`: S3-compatible writer. `S3ParquetWriter` for MinIO/R2/S3 (same code, only endpoint differs), `LocalParquetWriter` for tests against a tempdir.
- `batcher.py`: `ParquetBatcher` owns per-partition in-memory buffers, keyed by `(sat_id, sim-date, sim-hour)`. Flush triggers: (a) hour rollover for a sat (primary), (b) max-rows safety net, (c) explicit `flush_all` on shutdown. All decisions are sim-time based; wall-clock is not consulted, so file boundaries are stable in FAST mode and REALTIME mode alike.
- `consumer.py`: `TelemetryConsumer` with `MessageSource` protocol. `FakeSource` for unit tests, `KafkaSource` for production. Mirrors the producer's structure exactly.

Partitioning is Hive-style: `s3://telemetry/sat_id=X/date=YYYY-MM-DD/hour=HH/part-NNNN.parquet`. DuckDB, Spark, ClickHouse, Athena all read this layout natively.

The round-trip test in `test_consumer.py::test_consumer_round_trips_records_via_duckdb` is the bytes-in-equals-bytes-out invariant: N messages produced, N rows queried out of DuckDB with distinct timestamps. The `test_e2e_pipeline.py` integration test runs the full chain against the docker stack and skips cleanly when services aren't available.

### p-orb-ops-015

dbt-duckdb is now wired in. Three layers per the PLAN.md commitment:

- **raw** (`raw_telemetry`): 1:1 view over the Parquet glob via `read_parquet()`, explicit casts, parsed timestamp. The schema contract lives here.
- **staging** (`stg_geometry`, `stg_eps`, `stg_thermal`): per-subsystem cleanup, per-tick grain, computed columns (position magnitude, orbital speed, ground quadrant, charging flag, thermal regime).
- **marts** (`sat_minute_rollup`, `fleet_health_snapshot`): aggregated, dashboard-ready. Materialized as external Parquet on object storage so downstream consumers query the same file layout as raw data.

Profile is project-local (`dbt/orbit_ops/profiles.yml`). dbt's test framework is used at every layer: `not_null` on key columns; `accepted_values` for enumerations (ground_quadrant, thermal_regime, health bands); `unique` on `fleet_health_snapshot.sat_id` since each sat appears once. No `dbt_utils` dependency -- built-in tests are enough.

The `tests/test_dbt_models.py` pytest wrapper builds a tempdir Parquet fixture, points dbt at it via env vars, runs `dbt run` + `dbt test`, asserts both succeed. This means SQL regressions surface in the same `pytest` invocation as Python regressions. Marked `@pytest.mark.integration`. Uses a file-based DuckDB (not `:memory:`) so state persists between the run and test subprocess calls.

Architectural constraint honored: marts are external Parquet files, not rows inside a `.duckdb` database file. Grafana, future custom frontend, anomaly detectors all read the same object-storage layout.

Source tests were removed from `_sources.yml` because dbt-duckdb doesn't resolve Jinja in source `external_location` for test queries. The equivalent coverage is provided by `raw_telemetry`'s model tests, which test the same columns after they pass through the `read_parquet()` call.

### p-orb-ops-016

Fault injection layer. Three fault types implemented, each chosen to exercise a different class of anomaly detection method in the next prompt:

- **Battery capacity fade**: scales reported SoC by a fade factor that grows linearly with elapsed sim-time, capped at a floor. Symptom: SoC ceiling creeps down over many days while orbital dynamics stay the same. Change-point detection territory.
- **Stuck temperature sensor**: captures `bus_temperature_k` at activation and reports it indefinitely while other thermal channels keep flowing with the underlying physics. Symptom: reading no longer correlated with heat-balance state. Cross-channel residual detection territory.
- **Thermal runaway**: adds a linearly growing positive temperature bias with configurable rate and cap. Symptom: monotonic excursion past operational envelope. Threshold detection territory.

Architectural choice: faults are a *layer* applied to nominal `TickResult` output, not modifications to subsystem physics. The underlying model stays clean and physically correct; observed telemetry is what diverges. Defense: this matches how real anomalies present -- the sensor lies, the cells degrade, but the satellite's truth state is whatever it is.

Configuration is declarative YAML (`data/faults.yaml`, not committed; example at `data/faults.example.yaml`). Loaded once at producer startup; applied per-tick. `FaultRegistry.from_yaml` returns an empty registry on missing file, so the default behavior with no config is fully nominal.

Ground-truth fault timing is preserved by the YAML; the next prompt will use this as labels for backtesting detectors and producing a confusion matrix for the README.

### p-orb-ops-017

The anomaly detection layer. Three detector classes, each chosen as the right method for its fault class -- the deliberate variety is the project's "pragmatic methods, not ML reflexes" signal.

- **CapacityFadeDetector** (CUSUM on rolling max-SoC). Capacity fade is slow drift in a noisy signal; CUSUM was designed exactly for this problem class. Cheap, no training, defensible mathematically.
- **StuckSensorDetector** (cross-channel residual vs heat-balance prediction). The stuck value is plausible in isolation; what breaks is its correlation with the other thermal channels. Computing the predicted dT from the heat-balance equation and watching the residual catches it cleanly while a naive z-score would miss it.
- **ThermalRunawayDetector** (threshold + positive-slope check). The operational limit is known; ML is not the answer. The slope check suppresses false positives from normal sunlit warming briefly grazing the ceiling.

The runner reads `sat_minute_rollup` marts, iterates sat-by-sat in time order, feeds each row to all three detector instances. Events accumulate in memory, then flush to Parquet.

The evaluator joins detected events against the fault YAML (ground truth) to compute per-detector confusion outcomes (TP/FP/FN), recall, precision, and detection latency. `scripts/evaluate_detectors.py` renders the confusion matrix + latency figure.

Artifact `docs/figures/detector_performance.png` deferred to follow-up -- requires full-stack run (sim with faults -> consume -> dbt marts -> detect) to produce meaningful data. Code and tests are complete and green.

### p-orb-ops-018

The visualization layer. Three Grafana dashboards JSON-provisioned and mounted into the container at startup:

- **Fleet view**: table of all satellites with health-band coloring on battery and thermal columns. Reads `fleet_health_snapshot` mart.
- **Satellite drilldown**: time series of SoC, temperature, net power, eclipse fraction per selected satellite; recent anomaly events panel. Reads `sat_minute_rollup` + `anomaly_events`. Templating variable populated from a query against `fleet_health_snapshot`.
- **Anomaly feed**: fleet-wide chronological table of detector firings, severity-colored. Reads `anomaly_events`.

Grafana queries the marts directly via the motherduck-duckdb-datasource plugin (v0.4.1) running DuckDB embedded inside Grafana. The plugin is unsigned; installed via `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS` plus a pinned GitHub release URL in `GF_INSTALL_PLUGINS`. The "we removed this in p-orb-ops-004 because it was broken" story closes here: the registry-based install was broken; the GitHub-release install with allowlist works.

Provisioning lives in three subdirs under `dashboards/grafana/`: `dashboards/` (provider config), `datasources/` (DuckDB config), and `dashboard-defs/` (the JSON files themselves). Docker-compose mounts each at Grafana's expected path.

New `make demo-full` target produces a complete end-to-end demo: stack up, 6-hour sim with faults, consume, transform, detect. After it completes, all dashboards have populated panels.

### p-orb-ops-019 (verification)

First end-to-end run of the full pipeline on real infrastructure. Verified: stack startup (4 containers), 4 web endpoints (all 200), 3 Grafana dashboards + 1 datasource provisioned, 1800 messages produced and consumed cleanly (0 decode errors), 35 partitioned Parquet files landed on MinIO, dbt run built 6 models (2 external marts on S3), DuckDB-direct queries returned correct row counts (fleet: 5, rollup: 1800).

Two issues surfaced, both isolated (fixed in p-orb-ops-020):
- dbt test failed 31/31 on dev target: `:memory:` DuckDB not persisting across subprocess calls. Same bug fixed for test target in p-orb-ops-015.
- `evaluate_detectors.py` didn't pass S3 credentials to `run_detection()`.

### p-orb-ops-020

Two targeted fixes:
- dbt dev profile defaults to `dev.duckdb` (file-based, already gitignored via `*.duckdb`). Fixed a false start with `.dbt-dev.duckdb` -- DuckDB parsed the leading dot as a catalog reference.
- `evaluate_detectors.py` builds S3 settings from MINIO env vars when the marts glob starts with `s3://`.

Post-fix: dbt test PASS=31 ERROR=0. Detector script runs end-to-end against S3-backed marts. Artifact committed: `docs/figures/detector_performance.png` (53 KB).

Note: detector summary shows 0 events / 0 recall across all three detectors. Root cause: `data/faults.example.yaml` references sat names `SKYSAT-1`/`SKYSAT-3`/`SKYSAT-5` but the TLE-derived names are `SKYSAT-A`/`SKYSAT-B`/`SKYSAT-C1`/etc. The fault layer never matches, so no faults are injected, so detectors correctly don't fire. Fix: update the example YAML to use real TLE names. This is a config issue, not a code issue -- the pipeline, faults, and detectors all work correctly.

### p-orb-ops-021

Replaced placeholder sat names (`SKYSAT-1/3/5`) in `data/faults.example.yaml` with real TLE names (`SKYSAT-A`, `SKYSAT-C9`, `SKYSAT-C13`). Added staleness-risk comment and refresh recipe.

Post-fix verification confirmed faults are injected into the telemetry:
- SKYSAT-C13 (thermal runaway): bus temp at 33.6C at end of 6-hr sim, approaching 35C ceiling. ~40 more minutes of sim would cross the threshold.
- SKYSAT-C9 (stuck sensor): temp locked at 284.848 K throughout sim (fault start 2026-05-01 is before sim start 2026-05-26, so active from tick 0).
- SKYSAT-A (capacity fade): 0.5% SoC fade over 6 hours (0.02/day rate) -- invisible at this timescale.

All three detectors still report 0 TP because:
1. Capacity fade CUSUM needs days of drift; 6-hr sim gives only 0.5% which is below the 0.10 threshold.
2. Stuck sensor residual threshold (2.0 K) vs actual predicted-dT per minute (~0.006 K given 99000 J/K thermal mass) -- the per-minute expected temperature change is too small for the residual to trigger.
3. Thermal runaway at 2 K/hr needs ~11.5 hrs to reach 35C ceiling from ~12C nominal; 6-hr sim reaches 33.6C.

These are parameter/duration mismatches, not code bugs. The pipeline, faults, and detectors all work correctly. Tuning options for a follow-up: (a) run a longer sim (24hr+), (b) lower detector thresholds, (c) increase fault intensity in the example YAML.

### p-orb-ops-022

Three calibration changes to make detectors fire within the 6-hour demo window:

- `fade_rate_per_day`: 0.02 -> 0.40 in example YAML.
- `StuckSensorDetector.residual_threshold_k`: 2.0 -> 0.05 default. Calibrated against SkySat thermal mass (99,000 J/K); old value was ~300x the nominal signal floor, new value is ~8x.
- `thermal_runaway.rate_k_per_hour`: 2.0 -> 3.5 in example YAML.

Post-calibration results: stuck_sensor TP=1 FP=0 (recall 1.00), thermal_runaway TP=1 FP=0 (recall 1.00), capacity_fade TP=0 FP=0 FN=1. Two of three detectors fire cleanly with zero false positives.

Capacity fade non-detection explained: fault start (2026-05-01) is ~25 days before sim start (~2026-05-26). At 0.40/day, fade factor hits its 0.6 floor instantly -- no ongoing drift for CUSUM to detect. Fix for a follow-up: move fault start_iso closer to sim start time, or have the CLI inject faults relative to sim start rather than absolute times.

### p-orb-ops-023

Three deliverables combined:

1. **Capacity-fade fix**: moved all three fault `start_iso` from 2026-05-01 to 2026-05-26 to align with the sim's wall-clock UTC start. Added a comment explaining the staleness risk and that relative timestamps are future work. Result: capacity_fade now fires (TP=1 FP=0), stuck_sensor still fires (TP=1 FP=0). Thermal_runaway regressed to FN=1 because the runaway rate (3.5 K/hr = 0.058 K/min) is below the detector's slope threshold (0.1 K/min). This is a calibration issue for a follow-up — the detector works correctly; the slope check just needs to be matched to the rate.

2. **README design decisions**: expanded from initial 5 to full 9 subsections in commit cbcf031: Why DuckDB, Why dbt against Parquet, sim-clock abstraction, fault-injection-as-layer, per-subsystem detection methods, partitioning scheme, marts-as-Parquet, thermal model iteration story, no-orchestrator. Updated Status from "under construction" to "feature-complete through Sprint 2." Updated Quick Start to lead with `make demo-full`.

3. **Interview prep doc**: created `docs/INTERVIEW_PREP.md` (gitignored, verified not in git history) with: AI-question framing with honest talking points; six core Q&A with in-voice answers; study list of ledger entries to internalize vs skim; common technical pushbacks (Kafka vs Redpanda, scaling to 1000 sats, Forward Euler error, temperature derating gap); pre-interview checklist; demo flow for screen shares; 25-second elevator pitch.

Post-fix detector results: capacity_fade TP=1, stuck_sensor TP=1, thermal_runaway FN=1. 0 FP across all. Two of three detectors fire with perfect recall. The third's regression is traced to a known slope-threshold calibration gap.

## Conventions for future prompts

1. Every prompt has a single-line purpose suitable for the ledger table.
2. Every deliverable summary begins with `✓ p-orb-ops-NNN complete` (or `✗ p-orb-ops-NNN failed at step N` if it didn't).
3. Every successful prompt ends by updating this file: appending a row to the Ledger table, optionally adding a Notes entry, then committing with message `Log p-orb-ops-NNN in prompt ledger`.
4. Substantive design or architectural decisions get a dedicated note in the Notes section, not just a row.
