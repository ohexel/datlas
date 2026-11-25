import dagster as dg

from src.dagster_pipeline.assets.database_spatial import SPATIAL_ASSETS
from src.dagster_pipeline.assets.germany_employment import (
    GERMANY_EMPLOYMENT_ASSETS,
)
from src.dagster_pipeline.assets.germany_forecast import (
    GERMANY_FORECAST_ASSETS,
)
from src.dagster_pipeline.assets.germany_normalized import (
    GERMANY_NORMALIZED_ASSETS,
)
from src.dagster_pipeline.assets.germany_raw import GERMANY_RAW_ASSETS
from src.dagster_pipeline.assets.germany_sectors import GERMANY_SECTOR_ASSETS
from src.dagster_pipeline.assets.icon_d2_ruc import RAW_ICON_D2_RUC_ASSETS
from src.dagster_pipeline.checks.database_spatial import SPATIAL_CHECKS
from src.dagster_pipeline.checks.germany_employment import (
    GERMANY_EMPLOYMENT_CHECKS,
)
from src.dagster_pipeline.checks.germany_forecast import (
    GERMANY_FORECAST_CHECKS,
)
from src.dagster_pipeline.checks.germany_normalized import (
    GERMANY_NORMALIZED_CHECKS,
)
from src.dagster_pipeline.checks.germany_raw import GERMANY_RAW_CHECKS
from src.dagster_pipeline.checks.germany_sectors import GERMANY_SECTOR_CHECKS
from src.dagster_pipeline.germany_jobs import GERMANY_JOBS
from src.dagster_pipeline.sensors.ba_gemeindedaten import (
    ba_gemeindedaten_release_sensor,
)
from src.dagster_pipeline.sensors.ba_sectors import ba_sectors_release_sensor


defs = dg.Definitions(
    assets=[
        *SPATIAL_ASSETS,
        *RAW_ICON_D2_RUC_ASSETS,
        *GERMANY_RAW_ASSETS,
        *GERMANY_NORMALIZED_ASSETS,
        *GERMANY_FORECAST_ASSETS,
        *GERMANY_EMPLOYMENT_ASSETS,
        *GERMANY_SECTOR_ASSETS,
    ],
    asset_checks=[
        *SPATIAL_CHECKS,
        *GERMANY_RAW_CHECKS,
        *GERMANY_NORMALIZED_CHECKS,
        *GERMANY_FORECAST_CHECKS,
        *GERMANY_EMPLOYMENT_CHECKS,
        *GERMANY_SECTOR_CHECKS,
    ],
    jobs=[*GERMANY_JOBS],
    sensors=[
        ba_gemeindedaten_release_sensor,
        ba_sectors_release_sensor,
    ],
)
