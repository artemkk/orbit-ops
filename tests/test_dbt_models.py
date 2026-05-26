"""End-to-end dbt smoke test.

Builds a small fixture dataset of Parquet files in a tempdir, points dbt
at it via environment variables, runs `dbt run` + `dbt test`, asserts
both succeed. Skips if `dbt` CLI is not installed (uv extras not synced).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from orbit_ops.pipeline.messages import TelemetryRecord
from orbit_ops.pipeline.parquet_schema import TELEMETRY_SCHEMA


def _has_dbt() -> bool:
    return shutil.which("dbt") is not None or _has_dbt_via_uv()


def _has_dbt_via_uv() -> bool:
    try:
        result = subprocess.run(
            ["uv", "run", "dbt", "--version"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _make_record(
    sat_id: str,
    t: datetime,
    *,
    soc: float = 0.85,
    temp_c: float = 14.0,
    eclipsed: bool = False,
) -> dict[str, object]:
    rec = TelemetryRecord(
        sat_id=sat_id,
        sim_time_iso=t.isoformat(),
        position_eci_km_x=7000.0, position_eci_km_y=0.0, position_eci_km_z=0.0,
        velocity_eci_km_s_x=0.0, velocity_eci_km_s_y=7.5, velocity_eci_km_s_z=0.0,
        sun_vector_eci_x=1.0, sun_vector_eci_y=0.0, sun_vector_eci_z=0.0,
        eclipsed=eclipsed, latitude_deg=10.0, longitude_deg=20.0, altitude_km=550.0,
        solar_power_w=(0.0 if eclipsed else 200.0),
        bus_power_w=(60.0 if eclipsed else 90.0),
        net_power_w=(-60.0 if eclipsed else 110.0),
        battery_soc=soc, battery_charge_wh=soc * 150.0,
        bus_temperature_k=temp_c + 273.15, bus_temperature_c=temp_c,
        solar_heat_input_w=(0.0 if eclipsed else 190.0), earth_ir_input_w=100.0,
        radiative_heat_output_w=300.0, net_heat_w=(-10.0 if eclipsed else 10.0),
    )
    from dataclasses import asdict
    return asdict(rec)


def _write_fixture_parquet(root: Path, sats: list[str], minutes: int) -> None:
    """Write a small partitioned Parquet dataset under `root`."""
    start = datetime(2026, 5, 1, 14, 0, 0, tzinfo=UTC)
    for sat in sats:
        rows = []
        for i in range(minutes):
            t = start + timedelta(minutes=i)
            eclipsed = (i % 20) < 6  # ~30% eclipse fraction
            soc = 0.85 - (0.001 * i if eclipsed else -0.0005 * i)
            rows.append(_make_record(
                sat, t, soc=max(0.2, min(1.0, soc)), eclipsed=eclipsed,
            ))
        date = start.strftime("%Y-%m-%d")
        hour = start.strftime("%H")
        out_dir = root / f"sat_id={sat}" / f"date={date}" / f"hour={hour}"
        out_dir.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(rows, schema=TELEMETRY_SCHEMA)
        pq.write_table(table, out_dir / "part-0000.parquet", compression="zstd")


@pytest.mark.integration
def test_dbt_run_and_test_against_fixture(tmp_path: Path) -> None:
    """Run `dbt run` + `dbt test` against a fixture Parquet dataset."""
    if not _has_dbt():
        pytest.skip("dbt CLI not available; run `uv sync --extra dbt`")

    telemetry_root = tmp_path / "telemetry"
    marts_root = tmp_path / "marts"
    telemetry_root.mkdir()
    marts_root.mkdir()

    _write_fixture_parquet(telemetry_root, sats=["SKYSAT-1", "SKYSAT-2"], minutes=20)

    glob = str(telemetry_root / "sat_id=*" / "date=*" / "hour=*" / "*.parquet")
    # Normalize to forward slashes for DuckDB glob compatibility
    glob = glob.replace("\\", "/")
    marts_str = str(marts_root).replace("\\", "/")

    db_path = str(tmp_path / "dbt_test.duckdb").replace("\\", "/")

    env = {
        **os.environ,
        "DBT_TELEMETRY_GLOB": glob,
        "DBT_EXTERNAL_ROOT": marts_str,
        "DBT_DUCKDB_PATH": db_path,
        "DBT_PROFILES_DIR": str(
            Path(__file__).resolve().parent.parent / "dbt" / "orbit_ops"
        ),
    }

    dbt_dir = Path(__file__).resolve().parent.parent / "dbt" / "orbit_ops"

    run = subprocess.run(
        ["uv", "run", "dbt", "run", "--profiles-dir", str(dbt_dir), "--target", "test"],
        cwd=dbt_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, f"dbt run failed:\n{run.stdout}\n{run.stderr}"

    test = subprocess.run(
        ["uv", "run", "dbt", "test", "--profiles-dir", str(dbt_dir), "--target", "test"],
        cwd=dbt_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert test.returncode == 0, f"dbt test failed:\n{test.stdout}\n{test.stderr}"

    # Mart files should now exist in marts_root.
    written = list(marts_root.rglob("*.parquet"))
    assert len(written) >= 2, f"expected mart Parquet files, found: {written}"
