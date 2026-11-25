"""Dagster home directory shared by the command-line runners."""

import os
from pathlib import Path


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
