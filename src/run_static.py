"""Build the static inputs once: the ICON grid and its cells, the VG250 and
Zensus 2022 raw loads, the normalized hierarchy and population and the
cell-Gemeinde bridge, with the grid check and checks 1-4.

Usage:
    uv run --env-file .env python -m src.run_static

Needs ZENSUS2022_TOKEN only when the Zensus files are not yet present under
data/raw/germany/. Safe to repeat: an existing geography version is left
unchanged; population and bridge are rebuilt.
"""

import argparse
import json
import logging
from pathlib import Path
from time import perf_counter

from src.dagster_home import ensure_dagster_home
from src.dagster_home import execute_job


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_static(project_root: Path = PROJECT_ROOT) -> dict[str, object]:
    ensure_dagster_home(project_root)
    started = perf_counter()
    result = execute_job("static")
    if not result.success:
        raise RuntimeError(
            f"static failed; inspect Dagster run {result.run_id}"
        )
    return {
        "status": "ready",
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
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0].replace("\n", " ")
    )
    parser.parse_args(argv)  # no options; --help must not start the job
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO
    )
    print(json.dumps(run_static(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
