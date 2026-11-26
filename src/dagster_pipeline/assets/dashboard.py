"""The map's data files, exported after every publish."""

import dagster as dg

from src.dagster_pipeline.assets.forecast import ANALYTICAL_CURRENT_FORECAST_KEY
from src.dagster_pipeline.groups import FORECAST_GROUP
from src.export_germany_dashboard import export_germany_dashboard


GERMANY_DASHBOARD_KEY = dg.AssetKey(["web", "germany_dashboard"])


@dg.asset(
    key=GERMANY_DASHBOARD_KEY,
    deps=[ANALYTICAL_CURRENT_FORECAST_KEY],
    group_name=FORECAST_GROUP,
    description=(
        "Writes web/germany-dashboard/data: values.json (the current forecast "
        "run), employment.json and sectors.json (when loaded), and the boundary "
        "tiles once per geography version. Copying the folder to the web host "
        "is not part of the pipeline."
    ),
)
def web_germany_dashboard(context: dg.AssetExecutionContext) -> None:
    result = export_germany_dashboard()
    context.add_output_metadata(
        {
            "run_time_utc": result["run_time_utc"],
            "output_directory": result["output_directory"],
            "values_bytes": result["values_bytes"],
            "tiles": result["tiles"],
            "tiles_built": result["tiles_built"],
            "employment": str(result["employment"]),
            "sectors": str(result["sectors"]),
        }
    )


DASHBOARD_ASSETS = [web_germany_dashboard]
