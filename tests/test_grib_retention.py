"""GRIB file retention (split-plan D5) and the bounded rolling window."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.forecast_key import ProjectPaths
from src.retention.forecast_policy import (
    FORECAST_RETENTION_HOURS_ENV,
    forecast_partition_window_start,
    forecast_retention_cutoff,
    forecast_retention_hours,
)
from src.retention.grib_files import prune_grib_files


NOW_UTC = datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
RETENTION_HOURS = 24


def _write_raw_partition(
    *,
    project_root: Path,
    indicator: str = "t_2m",
    run_label: str = "20260822T0900",
    lead_label: str = "PT000H00M",
) -> tuple[Path, Path]:
    partition_dir = (
        project_root
        / "data"
        / "raw"
        / "icon_d2_ruc"
        / indicator
        / run_label
        / lead_label
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    grib_path = partition_dir / f"{indicator}.grib2"
    sidecar_path = partition_dir / "download_metadata.json"
    grib_path.write_bytes(b"fake-grib-content")
    sidecar_path.write_text('{"acquisition_status": "downloaded"}\n')
    return grib_path, sidecar_path


def test_retention_apply_removes_expired_grib_sidecar_and_empty_directories(
    tmp_path: Path,
) -> None:
    grib_path, sidecar_path = _write_raw_partition(project_root=tmp_path)
    lead_dir = grib_path.parent
    run_dir = lead_dir.parent
    indicator_dir = run_dir.parent
    forecast_root = indicator_dir.parent

    result = prune_grib_files(
        keep_run_times=(),
        paths=ProjectPaths(project_root=tmp_path),
        retention_hours=RETENTION_HOURS,
        now_utc=NOW_UTC,
        dry_run=False,
    )

    assert result.retention_hours == 24
    assert result.deleted_file_count == 1
    assert result.deleted_sidecar_file_count == 1
    assert result.kept_recent_file_count == 0
    assert not grib_path.exists()
    assert not sidecar_path.exists()
    assert not lead_dir.exists()
    assert not run_dir.exists()
    assert not indicator_dir.exists()
    assert forecast_root.is_dir()


def test_retention_preserves_run_exactly_at_24_hour_boundary(
    tmp_path: Path,
) -> None:
    expired_grib, _ = _write_raw_partition(
        project_root=tmp_path,
        run_label="20260822T0900",
    )
    boundary_grib, boundary_sidecar = _write_raw_partition(
        project_root=tmp_path,
        run_label="20260822T1000",
    )

    result = prune_grib_files(
        keep_run_times=(),
        paths=ProjectPaths(project_root=tmp_path),
        retention_hours=24,
        now_utc=NOW_UTC,
        dry_run=False,
    )

    assert result.deleted_file_count == 1
    assert result.kept_recent_file_count == 1
    assert not expired_grib.exists()
    assert boundary_grib.is_file()
    assert boundary_sidecar.is_file()


def test_retention_dry_run_reports_sources_without_deleting(
    tmp_path: Path,
) -> None:
    grib_path, sidecar_path = _write_raw_partition(project_root=tmp_path)

    result = prune_grib_files(
        keep_run_times=(),
        paths=ProjectPaths(project_root=tmp_path),
        retention_hours=24,
        now_utc=NOW_UTC,
        dry_run=True,
    )

    assert result.deleted_file_count == 1
    assert result.deleted_sidecar_file_count == 1
    assert result.bytes_deleted == grib_path.stat().st_size + sidecar_path.stat().st_size
    assert grib_path.is_file()
    assert sidecar_path.is_file()


@pytest.mark.parametrize("hours", [0, -1, 25, 48])
def test_retention_rejects_windows_outside_one_to_24_hours(hours: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 24 hours"):
        forecast_retention_hours(hours)


def test_retention_reads_bounded_hourly_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(FORECAST_RETENTION_HOURS_ENV, "12")
    assert forecast_retention_hours() == 12
    assert forecast_retention_cutoff(now_utc=NOW_UTC) == NOW_UTC - timedelta(hours=12)


def test_partition_window_contains_at_most_24_whole_hour_runs() -> None:
    now = datetime(2026, 8, 23, 10, 37, tzinfo=timezone.utc)
    assert forecast_partition_window_start(now_utc=now, retention_hours=24) == (
        datetime(2026, 8, 22, 11, 0, tzinfo=timezone.utc)
    )
    assert forecast_partition_window_start(now_utc=now, retention_hours=1) == (
        datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)
    )


def test_old_run_still_in_the_database_keeps_its_files(tmp_path: Path) -> None:
    kept_grib, kept_sidecar = _write_raw_partition(
        project_root=tmp_path, run_label="20260821T0900"
    )
    gone_grib, _ = _write_raw_partition(project_root=tmp_path, run_label="20260821T0800")

    result = prune_grib_files(
        keep_run_times={datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)},
        paths=ProjectPaths(project_root=tmp_path),
        retention_hours=24,
        now_utc=NOW_UTC,
        dry_run=False,
    )

    assert kept_grib.is_file()
    assert kept_sidecar.is_file()
    assert not gone_grib.exists()
    assert result.database_run_count == 1
    assert result.kept_database_run_file_count == 1
    assert result.deleted_file_count == 1


def test_database_run_times_from_other_zones_are_compared_in_utc(tmp_path: Path) -> None:
    grib, _ = _write_raw_partition(project_root=tmp_path, run_label="20260821T0900")
    berlin_summer = timezone(timedelta(hours=2))

    result = prune_grib_files(
        keep_run_times={datetime(2026, 8, 21, 11, 0, tzinfo=berlin_summer)},
        paths=ProjectPaths(project_root=tmp_path),
        retention_hours=24,
        now_utc=NOW_UTC,
        dry_run=False,
    )

    assert grib.is_file()
    assert result.deleted_file_count == 0
