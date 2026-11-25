import dagster as dg

from src.dagster_pipeline.assets.database_spatial import SPATIAL_ASSETS
from src.dagster_pipeline.assets.employment import (
    EMPLOYMENT_ASSETS,
)
from src.dagster_pipeline.assets.forecast import (
    FORECAST_ASSETS,
)
from src.dagster_pipeline.assets.normalized import (
    NORMALIZED_ASSETS,
)
from src.dagster_pipeline.assets.raw import RAW_ASSETS
from src.dagster_pipeline.assets.sectors import SECTOR_ASSETS
from src.dagster_pipeline.assets.icon_d2_ruc import RAW_ICON_D2_RUC_ASSETS
from src.dagster_pipeline.checks.database_spatial import SPATIAL_CHECKS
from src.dagster_pipeline.checks.employment import (
    EMPLOYMENT_CHECKS,
)
from src.dagster_pipeline.checks.forecast import (
    FORECAST_CHECKS,
)
from src.dagster_pipeline.checks.normalized import (
    NORMALIZED_CHECKS,
)
from src.dagster_pipeline.checks.raw import RAW_CHECKS
from src.dagster_pipeline.checks.sectors import SECTOR_CHECKS
from src.dagster_pipeline.jobs import JOBS
from src.dagster_pipeline.sensors.ba_gemeindedaten import (
    ba_gemeindedaten_release_sensor,
)
from src.dagster_pipeline.sensors.ba_sectors import ba_sectors_release_sensor


defs = dg.Definitions(
    assets=[
        *SPATIAL_ASSETS,
        *RAW_ICON_D2_RUC_ASSETS,
        *RAW_ASSETS,
        *NORMALIZED_ASSETS,
        *FORECAST_ASSETS,
        *EMPLOYMENT_ASSETS,
        *SECTOR_ASSETS,
    ],
    asset_checks=[
        *SPATIAL_CHECKS,
        *RAW_CHECKS,
        *NORMALIZED_CHECKS,
        *FORECAST_CHECKS,
        *EMPLOYMENT_CHECKS,
        *SECTOR_CHECKS,
    ],
    jobs=[*JOBS],
    sensors=[
        ba_gemeindedaten_release_sensor,
        ba_sectors_release_sensor,
    ],
)
