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

## Conventions for future prompts

1. Every prompt has a single-line purpose suitable for the ledger table.
2. Every deliverable summary begins with `✓ p-orb-ops-NNN complete` (or `✗ p-orb-ops-NNN failed at step N` if it didn't).
3. Every successful prompt ends by updating this file: appending a row to the Ledger table, optionally adding a Notes entry, then committing with message `Log p-orb-ops-NNN in prompt ledger`.
4. Substantive design or architectural decisions get a dedicated note in the Notes section, not just a row.
