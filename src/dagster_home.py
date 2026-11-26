"""Dagster home directory and job execution shared by the command-line runners."""

import os
from pathlib import Path

import dagster as dg


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def ensure_dagster_home(project_root: Path = PROJECT_ROOT) -> Path:
    configured_home = os.environ.get("DAGSTER_HOME")
    dagster_home = (
        Path(configured_home).expanduser()
        if configured_home
        else project_root / ".dagster_home"
    )
    if not dagster_home.is_absolute():
        dagster_home = (project_root / dagster_home).resolve()

    dagster_home.mkdir(parents=True, exist_ok=True)
    os.environ["DAGSTER_HOME"] = str(dagster_home)
    return dagster_home


def execute_job(
    job_name: str, *, partition_key=None, run_config=None
) -> dg.ExecuteInProcessResult:
    """Execute one job of the project's definitions in this process."""
    from src.dagster_pipeline.definitions import defs

    instance = dg.DagsterInstance.get()
    try:
        return defs.resolve_job_def(job_name).execute_in_process(
            partition_key=partition_key,
            run_config=run_config,
            instance=instance,
            raise_on_error=False,
        )
    finally:
        instance.dispose()
