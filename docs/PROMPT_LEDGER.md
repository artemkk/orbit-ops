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

## Conventions for future prompts

1. Every prompt has a single-line purpose suitable for the ledger table.
2. Every deliverable summary begins with `✓ p-orb-ops-NNN complete` (or `✗ p-orb-ops-NNN failed at step N` if it didn't).
3. Every successful prompt ends by updating this file: appending a row to the Ledger table, optionally adding a Notes entry, then committing with message `Log p-orb-ops-NNN in prompt ledger`.
4. Substantive design or architectural decisions get a dedicated note in the Notes section, not just a row.
