"""Load one vintage of the BA Gemeindedaten (employment per Gemeinde) into the
Germany layer, with the BA source checks.

Usage:
    uv run --env-file .env python -m src.run_employment [--reference-date 2025-06-30]

Needs the hierarchy from python -m src.run_static first. Safe to
repeat: the raw rows and indicator values of the reference date are replaced.
"""

import argparse
import json
import logging
from datetime import date
from pathlib import Path
from time import perf_counter

from src.dagster_home import ensure_dagster_home
from src.dagster_pipeline.jobs import employment_run_config
from src.ingestion.contract import BA_GEMEINDEDATEN_CONTRACT
from src.dagster_home import execute_job


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_employment(
    reference_date: date, project_root: Path = PROJECT_ROOT
) -> dict[str, object]:
    ensure_dagster_home(project_root)
    started = perf_counter()
    result = execute_job(
        "employment", run_config=employment_run_config(reference_date)
    )
    if not result.success:
        raise RuntimeError(f"employment failed; inspect Dagster run {result.run_id}")
    return {
        "status": "ready",
        "reference_date": reference_date.isoformat(),
        "wall_seconds": round(perf_counter() - started, 1),
        "checks": {
            evaluation.check_name: {
                "passed": evaluation.passed,
                "severity": evaluation.severity.value,
            }
            for evaluation in result.get_asset_check_evaluations()
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        default=BA_GEMEINDEDATEN_CONTRACT.latest_known,
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO
    )
    print(json.dumps(run_employment(args.reference_date), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
