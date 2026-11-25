"""Germany-layer jobs. The Berlin jobs and sensor are unchanged (F)."""

from datetime import date

import dagster as dg

from src.dagster_pipeline.assets.employment import (
    EMPLOYMENT_ASSETS,
    normalized_indicator_value,
    raw_ba_gemeindedaten,
)
from src.dagster_pipeline.assets.sectors import (
    SECTOR_ASSETS,
    raw_ba_regionalreport,
    raw_ba_wz_heft,
)
from src.dagster_pipeline.assets.forecast import (
    analytical_current_forecast_25h,
    normalized_gemeinde_forecast,
    normalized_icon_gemeinde_bridge,
)
from src.dagster_pipeline.assets.normalized import NORMALIZED_ASSETS
from src.dagster_pipeline.assets.raw import RAW_ASSETS
from src.dagster_pipeline.assets.database_spatial import SPATIAL_ASSETS
from src.dagster_pipeline.assets.icon_d2_ruc import RAW_ICON_D2_RUC_ASSETS


STATIC_JOB = dg.define_asset_job(
    name="static",
    selection=dg.AssetSelection.assets(
        *SPATIAL_ASSETS,
        *RAW_ASSETS,
        *NORMALIZED_ASSETS,
        normalized_icon_gemeinde_bridge,
    ),
    description=(
        "Load the ICON grid and build its cells; acquire and load VG250 and "
        "Zensus 2022; build the normalized hierarchy, population and the "
        "cell-Gemeinde bridge."
    ),
)

FORECAST_JOB = dg.define_asset_job(
    name="forecast",
    selection=dg.AssetSelection.assets(
        *RAW_ICON_D2_RUC_ASSETS,
        normalized_gemeinde_forecast,
    ),
    description=(
        "One forecast partition for Germany: the four retained raw DWD "
        "fields (file-only, shared with Berlin) and the Germany cell and "
        "Gemeinde aggregation."
    ),
)

PUBLISH_JOB = dg.define_asset_job(
    name="forecast_publish",
    selection=dg.AssetSelection.assets(analytical_current_forecast_25h),
    description=(
        "Publish the current complete Germany run, apply retention and run "
        "checks 5-6."
    ),
)

EMPLOYMENT_JOB = dg.define_asset_job(
    name="employment",
    selection=dg.AssetSelection.assets(*EMPLOYMENT_ASSETS),
    description=(
        "Acquire one vintage of the BA Gemeindedaten (run config: reference "
        "date), load it raw and refresh the indicator values on the hierarchy, "
        "with the BA source checks. Needs germany_static first."
    ),
)


def employment_run_config(reference_date: date) -> dict:
    """Run config that sets the reference date of both employment assets."""
    config = {"config": {"reference_date": reference_date.isoformat()}}
    return {
        "ops": {
            raw_ba_gemeindedaten.op.name: config,
            normalized_indicator_value.op.name: config,
        }
    }


SECTORS_JOB = dg.define_asset_job(
    name="sectors",
    selection=dg.AssetSelection.assets(*SECTOR_ASSETS),
    description=(
        "Download one quarter of the BA sector data (run config: file date): "
        "the 17 WZ booklets for that quarter and a year earlier, and one "
        "Regionalreport per Kreis, one request at a time; load them raw and "
        "refresh the sector values, with the sector checks. Needs "
        "germany_static first."
    ),
)


def sector_run_config(file_date: date) -> dict:
    """Run config that sets the file date of both raw sector assets."""
    config = {"config": {"file_date": file_date.isoformat()}}
    return {"ops": {raw_ba_wz_heft.op.name: config, raw_ba_regionalreport.op.name: config}}


JOBS = [
    STATIC_JOB,
    FORECAST_JOB,
    PUBLISH_JOB,
    EMPLOYMENT_JOB,
    SECTORS_JOB,
]
