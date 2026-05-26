.PHONY: help install demo sim pipeline stop clean test lint format check tle transform transform-test detect

help:
	@echo "Targets:"
	@echo "  install   - install python deps with uv"
	@echo "  demo      - bring up the full local stack (redpanda, minio, grafana)"
	@echo "  sim       - run the simulator against the local stack"
	@echo "  pipeline  - run the consumer + parquet writer"
	@echo "  stop      - tear down docker-compose stack"
	@echo "  clean     - remove generated data + caches"
	@echo "  test      - run pytest"
	@echo "  lint      - ruff check"
	@echo "  format    - ruff format"
	@echo "  check     - lint + test"
	@echo "  tle       - refresh TLE data from Celestrak"
	@echo "  transform - run dbt models (raw -> staging -> marts)"
	@echo "  transform-test - run dbt tests"
	@echo "  detect    - run anomaly detectors against marts + evaluate"

install:
	uv sync --extra dev --extra dbt

demo:
	docker compose -f infra/docker/docker-compose.yml up -d
	@echo "Stack up. Grafana: http://localhost:3000  MinIO: http://localhost:9001  Redpanda Console: http://localhost:8080"

sim:
	uv run orbit-ops sim run

pipeline:
	uv run orbit-ops pipeline consume

stop:
	docker compose -f infra/docker/docker-compose.yml down

clean:
	rm -rf data/parquet data/duckdb data/checkpoints
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

test:
	uv run pytest

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

check: lint test

tle:
	uv run python scripts/fetch_tles.py

transform:
	cd dbt/orbit_ops && uv run dbt run --profiles-dir .

transform-test:
	cd dbt/orbit_ops && uv run dbt test --profiles-dir .

detect:
	@echo "Detection requires marts built first. Run: make transform"
	uv run python scripts/evaluate_detectors.py \
		--marts-glob "$${DETECT_MARTS_GLOB:-/tmp/orbit-ops/marts/sat_minute_rollup.parquet}" \
		--faults-yaml data/faults.yaml \
		--out docs/figures/detector_performance.png
