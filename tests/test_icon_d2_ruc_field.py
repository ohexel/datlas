"""prepare_field: one validated full-grid field, or a quarantine note and an error."""

import json
from pathlib import Path

import numpy as np
import pytest

from src.forecast_key import ForecastKey, ProjectPaths
from src.icon_d2_ruc_grib import DecodedIconField
from src.icon_grid_contract import ICON_D2_GRID_CONTRACT
from src.ingestion import icon_d2_ruc_field


FORECAST = ForecastKey.from_dwd_labels(run_time="2026-08-24T16:00", lead_time="PT001H00M")
POINTS = ICON_D2_GRID_CONTRACT.field_point_count


def _retained_file(paths: ProjectPaths) -> Path:
    path = paths.raw_icon_field(indicator="T_2M", forecast=FORECAST)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"retained fixture")
    return path


def _quarantine_note(paths: ProjectPaths) -> dict:
    note = (
        paths.data_root / "raw" / "quarantine" / "icon_d2_ruc"
        / FORECAST.run_label / FORECAST.lead_time_label / "t_2m" / "failure.json"
    )
    return json.loads(note.read_text(encoding="utf-8"))


def test_valid_field_returns_all_grid_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = ProjectPaths(project_root=tmp_path)
    source = _retained_file(paths)
    values = np.arange(POINTS, dtype="float32")
    monkeypatch.setattr(
        icon_d2_ruc_field,
        "decode_and_validate_field",
        lambda **kwargs: DecodedIconField(values=values, metadata={"units": "K"}),
    )

    prepared = icon_d2_ruc_field.prepare_field(paths=paths, forecast=FORECAST, indicator="T_2M")

    assert prepared.source_path == source
    assert prepared.source_unit == "K"
    assert prepared.values.dtype == np.float64
    assert prepared.values.shape == (POINTS,)
    assert prepared.values[-1] == POINTS - 1


def test_decode_error_leaves_a_quarantine_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = ProjectPaths(project_root=tmp_path)
    _retained_file(paths)

    def broken(**kwargs):
        raise ValueError("truncated GRIB message")

    monkeypatch.setattr(icon_d2_ruc_field, "decode_and_validate_field", broken)

    with pytest.raises(ValueError, match="truncated GRIB message"):
        icon_d2_ruc_field.prepare_field(paths=paths, forecast=FORECAST, indicator="T_2M")

    note = _quarantine_note(paths)
    assert note["indicator"] == "T_2M"
    assert note["error_type"] == "ValueError"
    assert note["source_sha256"]


def test_wrong_point_count_is_refused_and_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = ProjectPaths(project_root=tmp_path)
    _retained_file(paths)
    monkeypatch.setattr(
        icon_d2_ruc_field,
        "decode_and_validate_field",
        lambda **kwargs: DecodedIconField(values=np.zeros(POINTS - 1), metadata={"units": "K"}),
    )

    with pytest.raises(ValueError, match="expected"):
        icon_d2_ruc_field.prepare_field(paths=paths, forecast=FORECAST, indicator="T_2M")

    assert "expected" in _quarantine_note(paths)["error"]
