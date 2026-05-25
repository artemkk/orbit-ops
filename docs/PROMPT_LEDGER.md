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

## Notes

### p-orb-ops-001 / 002 (deprecated)

Early scaffolding approach used a tarball generated in the Claude.ai sandbox. The tarball couldn't be located on the Windows machine and would have required manual re-download. Replaced with p-orb-ops-003, which writes every file directly from the prompt — no binary artifacts, fully reproducible from prompt text.

### p-orb-ops-003 (partial)

Steps 1–9 (scaffold creation, GitHub push, uv sync, test suite green) all succeeded. Step 10 (Docker stack startup) failed because the docker-compose.yml referenced `GF_INSTALL_PLUGINS: motherduck-duckdb-datasource`, an unsigned plugin that can't be installed via the registry env var. Patched by p-orb-ops-004.

### p-orb-ops-004

Removed the Grafana DuckDB plugin reference. Plugin will be re-added in Sprint 3 (dashboards) with the proper unsigned-plugin install workflow. Until then, Grafana boots cleanly and the Test Data datasource is sufficient for verifying the stack.

## Conventions for future prompts

1. Every prompt has a single-line purpose suitable for the ledger table.
2. Every deliverable summary begins with `✓ p-orb-ops-NNN complete` (or `✗ p-orb-ops-NNN failed at step N` if it didn't).
3. Every successful prompt ends by updating this file: appending a row to the Ledger table, optionally adding a Notes entry, then committing with message `Log p-orb-ops-NNN in prompt ledger`.
4. Substantive design or architectural decisions get a dedicated note in the Notes section, not just a row.
