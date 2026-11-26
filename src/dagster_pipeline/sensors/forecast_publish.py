"""Publish each forecast run once it is complete, then export the map.

Every minute the sensor asks the database for the newest run with all 25
lead times for every Gemeinde. A run gets the forecast_publish job
(retention, checks 5-6, map export) once; a failed publish is retried up to
five attempts in total, like a forecast partition. Older complete runs are
never published again: the newest one supersedes them.
"""

from datetime import timezone

import dagster as dg

from src.database.connection import database_connection
from src.database.forecast import newest_complete_run
from src.dagster_pipeline.jobs import PUBLISH_JOB
from src.dagster_pipeline.sensors.dwd_forecast import next_attempt
from src.forecast_key import RUN_LABEL_FORMAT


PUBLISH_SENSOR_MINIMUM_INTERVAL_SECONDS = 60
PUBLISH_RUN_SCOPE_TAG = "publish_run_scope"
PUBLISH_RUN_SCOPE = "forecast_publish"


@dg.sensor(
    job=PUBLISH_JOB,
    minimum_interval_seconds=PUBLISH_SENSOR_MINIMUM_INTERVAL_SECONDS,
    default_status=dg.DefaultSensorStatus.STOPPED,
    description=(
        "Publish the newest complete forecast run once (retention, checks 5-6 "
        "and the map export)."
    ),
)
def forecast_publish_sensor(context: dg.SensorEvaluationContext):
    with database_connection(application_name="datlas_publish_sensor") as connection:
        run_time = newest_complete_run(connection)
    if run_time is None:
        return dg.SkipReason("No complete forecast run yet.")

    run_label = run_time.astimezone(timezone.utc).strftime(RUN_LABEL_FORMAT)
    runs = context.instance.get_runs(
        filters=dg.RunsFilter(
            tags={"forecast_run_time": run_label, PUBLISH_RUN_SCOPE_TAG: PUBLISH_RUN_SCOPE}
        )
    )
    attempt = next_attempt(runs)
    if attempt is None:
        return dg.SkipReason(
            f"Run {run_label} is published, being published, or out of attempts."
        )

    return dg.RunRequest(
        run_key=f"forecast_publish:{run_label}:attempt_{attempt}",
        tags={
            "forecast_run_time": run_label,
            "attempt": str(attempt),
            PUBLISH_RUN_SCOPE_TAG: PUBLISH_RUN_SCOPE,
        },
    )
