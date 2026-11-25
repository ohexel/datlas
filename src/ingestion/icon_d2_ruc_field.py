"""Decode and validate one retained ICON-D2-RUC GRIB field.

A field that fails to decode or validate leaves a failure note under
data/raw/quarantine/icon_d2_ruc/ and raises.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.dwd_icon_d2_ruc import field_url, sha256_file
from src.forecast_key import ForecastKey, ProjectPaths
from src.icon_d2_ruc_grib import decode_and_validate_field
from src.icon_grid_contract import (
    ICON_D2_GRID_CONTRACT,
)



@dataclass(frozen=True)
class PreparedField:
    indicator: str
    source_path: Path
    source_url: str
    source_sha256: str
    source_unit: str
    values: np.ndarray


def _source_path(
    paths: ProjectPaths,
    *,
    indicator: str,
    forecast: ForecastKey,
) -> Path:
    return paths.raw_icon_field(
        indicator=indicator,
        forecast=forecast,
    )


def _quarantine_path(
    *,
    paths: ProjectPaths,
    forecast: ForecastKey,
    indicator: str,
) -> Path:
    return (
        paths.data_root
        / 'raw'
        / 'quarantine'
        / 'icon_d2_ruc'
        / forecast.run_label
        / forecast.lead_time_label
        / indicator.lower()
        / 'failure.json'
    )


def _write_decode_failure(
    *,
    paths: ProjectPaths,
    forecast: ForecastKey,
    indicator: str,
    source_path: Path,
    error: Exception,
) -> None:
    target = _quarantine_path(
        paths=paths,
        forecast=forecast,
        indicator=indicator,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
        'run_time_utc': forecast.run_time.isoformat(),
        'lead_time': forecast.lead_time_label,
        'valid_time_utc': forecast.valid_time.isoformat(),
        'indicator': indicator,
        'source_path': str(source_path),
        'source_sha256': (
            sha256_file(source_path)
            if source_path.exists()
            else None
        ),
        'error_type': type(error).__name__,
        'error': str(error),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )


def prepare_field(
    *,
    paths: ProjectPaths,
    forecast: ForecastKey,
    indicator: str,
) -> PreparedField:
    source_path = _source_path(
        paths,
        indicator=indicator,
        forecast=forecast,
    )
    if not source_path.exists():
        raise FileNotFoundError(
            f'Retained raw weather file not found: {source_path}'
        )

    try:
        decoded = decode_and_validate_field(
            path=source_path,
            indicator=indicator,
            forecast=forecast,
            expected_point_count=ICON_D2_GRID_CONTRACT.field_point_count,
        )
    except Exception as exc:
        _write_decode_failure(
            paths=paths,
            forecast=forecast,
            indicator=indicator,
            source_path=source_path,
            error=exc,
        )
        raise

    values = np.asarray(
        decoded.values,
        dtype='float64',
    ).reshape(-1)

    if len(values) != ICON_D2_GRID_CONTRACT.field_point_count:
        error = ValueError(
            f'{indicator} decoded {len(values):,} values; expected '
            f'{ICON_D2_GRID_CONTRACT.field_point_count:,}'
        )
        _write_decode_failure(
            paths=paths,
            forecast=forecast,
            indicator=indicator,
            source_path=source_path,
            error=error,
        )
        raise error

    source_unit = str(decoded.metadata.get('units', '')).strip()
    if not source_unit:
        error = ValueError(
            f'{indicator} decoded metadata contains no source unit'
        )
        _write_decode_failure(
            paths=paths,
            forecast=forecast,
            indicator=indicator,
            source_path=source_path,
            error=error,
        )
        raise error

    return PreparedField(
        indicator=indicator,
        source_path=source_path,
        source_url=field_url(indicator, forecast),
        source_sha256=sha256_file(source_path),
        source_unit=source_unit,
        values=values,
    )
