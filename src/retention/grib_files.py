"""GRIB file retention (split-plan D5).

A retained GRIB file is deleted, with its download sidecar and any directory
left empty, only when its run is both older than the rolling window
(FORECAST_RETENTION_HOURS, default and maximum 24 hours) and no longer in
the database (normalized.forecast_run). The database keeps the newest
complete run, the complete run before it and any newer run still loading
(normalized.prune_forecast), so its files stay reprocessable as long as its
rows exist. The publish step applies this after the database retention;
the command line inspects it (dry run) or applies it:

    uv run --env-file .env python -m src.retention.grib_files [--apply]
"""

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from psycopg import Connection

from src.database.connection import database_connection
from src.forecast_key import ProjectPaths, RUN_LABEL_FORMAT
from src.retention.forecast_policy import (
    forecast_retention_cutoff,
    forecast_retention_hours,
)


@dataclass(frozen=True)
class GribRetentionResult:
    retention_hours: int
    cutoff_utc: datetime
    database_run_count: int
    candidate_file_count: int
    deleted_file_count: int
    deleted_sidecar_file_count: int
    kept_recent_file_count: int
    kept_database_run_file_count: int
    bytes_deleted: int


def database_run_times(connection: Connection) -> frozenset[datetime]:
    """Run times that still have forecast rows in the database."""
    return frozenset(
        row[0]
        for row in connection.execute("SELECT run_time_utc FROM normalized.forecast_run")
    )


def _sidecar_path(grib_path: Path) -> Path:
    return grib_path.parent / "download_metadata.json"


def _prune_empty_directories(*, start: Path, root: Path) -> None:
    parent = start
    while parent != root and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def _run_time(path: Path) -> datetime:
    # data/raw/icon_d2_ruc/<indicator>/<run label>/<lead label>/<file>.grib2
    return datetime.strptime(path.parents[1].name, RUN_LABEL_FORMAT).replace(
        tzinfo=timezone.utc
    )


def prune_grib_files(
    *,
    keep_run_times: Iterable[datetime],
    paths: ProjectPaths | None = None,
    retention_hours: int | None = None,
    now_utc: datetime | None = None,
    dry_run: bool = True,
) -> GribRetentionResult:
    """Delete (or, in a dry run, count) the GRIB files no rule keeps."""
    project_paths = paths if paths is not None else ProjectPaths()
    keep = frozenset(value.astimezone(timezone.utc) for value in keep_run_times)
    hours = forecast_retention_hours(retention_hours)
    cutoff = forecast_retention_cutoff(now_utc=now_utc, retention_hours=hours)

    root = project_paths.data_root / "raw" / "icon_d2_ruc"
    candidates = sorted(root.glob("*/*/*/*.grib2"))

    deleted = deleted_sidecars = kept_recent = kept_database = bytes_deleted = 0
    for path in candidates:
        run_time = _run_time(path)
        if run_time >= cutoff:
            kept_recent += 1
            continue
        if run_time in keep:
            kept_database += 1
            continue

        sidecar = _sidecar_path(path)
        has_sidecar = sidecar.is_file()
        bytes_deleted += path.stat().st_size + (sidecar.stat().st_size if has_sidecar else 0)
        if not dry_run:
            path.unlink()
            if has_sidecar:
                sidecar.unlink()
            _prune_empty_directories(start=path.parent, root=root)
        deleted += 1
        deleted_sidecars += int(has_sidecar)

    return GribRetentionResult(
        retention_hours=hours,
        cutoff_utc=cutoff,
        database_run_count=len(keep),
        candidate_file_count=len(candidates),
        deleted_file_count=deleted,
        deleted_sidecar_file_count=deleted_sidecars,
        kept_recent_file_count=kept_recent,
        kept_database_run_file_count=kept_database,
        bytes_deleted=bytes_deleted,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or delete retained GRIB files whose run is older than the "
            "rolling window (at most 24 hours) and no longer in the database."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the files. Default is a dry run.",
    )
    args = parser.parse_args(argv)

    with database_connection(application_name="datlas_grib_retention") as connection:
        keep = database_run_times(connection)
    result = prune_grib_files(keep_run_times=keep, dry_run=not args.apply)
    print(json.dumps(asdict(result), default=str, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
