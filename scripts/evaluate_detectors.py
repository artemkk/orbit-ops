"""Generate docs/figures/detector_performance.png.

Runs detection against marts, scores against fault YAML, renders a
confusion-matrix + latency figure.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from orbit_ops.detection.evaluator import evaluate  # noqa: E402
from orbit_ops.detection.runner import run_detection  # noqa: E402
from orbit_ops.sim.faults import FaultRegistry  # noqa: E402


def _duckdb_settings_from_env() -> dict[str, str]:
    """Build DuckDB S3 settings from MINIO_* env vars."""
    endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    endpoint_clean = endpoint.replace("http://", "").replace("https://", "")
    return {
        "s3_url_style": "path",
        "s3_endpoint": endpoint_clean,
        "s3_access_key_id": os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
        "s3_secret_access_key": os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
        "s3_use_ssl": "false",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--marts-glob", required=True, help="Glob for sat_minute_rollup parquet files.")
    parser.add_argument("--faults-yaml", required=True, help="Path to fault config YAML.")
    parser.add_argument(
        "--out",
        default=str(REPO / "docs" / "figures" / "detector_performance.png"),
        help="Output PNG path.",
    )
    args = parser.parse_args()

    faults = FaultRegistry.from_yaml(Path(args.faults_yaml))
    settings = _duckdb_settings_from_env() if args.marts_glob.startswith("s3://") else None
    events, stats = run_detection(args.marts_glob, duckdb_settings=settings)
    scorecards = evaluate(events, faults)

    print(f"Processed {stats.rows_consumed} rows across {stats.sats_processed} sats", file=sys.stderr)
    print(f"Emitted {stats.events_emitted} events", file=sys.stderr)

    # ---------- Render ----------
    fig, (ax_conf, ax_lat) = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Detector performance -- per-detector scorecards", fontsize=13)

    det_names = list(scorecards.keys())
    tp = [scorecards[n].true_positives for n in det_names]
    fp = [scorecards[n].false_positives for n in det_names]
    fn = [scorecards[n].false_negatives for n in det_names]

    x = np.arange(len(det_names))
    width = 0.25
    ax_conf.bar(x - width, tp, width, label="True Positives", color="tab:green")
    ax_conf.bar(x, fp, width, label="False Positives", color="tab:orange")
    ax_conf.bar(x + width, fn, width, label="False Negatives", color="tab:red")
    ax_conf.set_xticks(x)
    ax_conf.set_xticklabels(det_names, rotation=15)
    ax_conf.set_ylabel("Count")
    ax_conf.set_title("Confusion outcomes")
    ax_conf.legend()
    ax_conf.grid(True, axis="y", alpha=0.3)

    latency_minutes = []
    for n in det_names:
        lat = scorecards[n].mean_latency_seconds
        latency_minutes.append((lat or 0.0) / 60.0)
    ax_lat.bar(det_names, latency_minutes, color="tab:blue")
    ax_lat.set_ylabel("Mean detection latency (minutes)")
    ax_lat.set_title("Detection latency")
    ax_lat.set_xticklabels(det_names, rotation=15)
    ax_lat.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"Wrote {out_path}", file=sys.stderr)

    # ---------- Print summary table ----------
    print("\nPer-detector summary:", file=sys.stderr)
    header = f"{'detector':<20} {'TP':>4} {'FP':>4} {'FN':>4} {'recall':>8} {'precision':>10} {'latency_min':>12}"
    print(header, file=sys.stderr)
    for n in det_names:
        sc = scorecards[n]
        lat_min = sc.mean_latency_seconds / 60.0 if sc.mean_latency_seconds else float("nan")
        print(
            f"{n:<20} {sc.true_positives:>4} {sc.false_positives:>4} {sc.false_negatives:>4} "
            f"{sc.recall:>8.2f} {sc.precision:>10.2f} {lat_min:>12.1f}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
