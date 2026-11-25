"""Launch forecast partitions as soon as DWD has published all four fields.

Ported from the capstone (lwr) with its PR #21 behaviour: the newest run
times and, within them, the newest lead times first; partitions that are
complete or already have a run are left out before the per-tick cap, so
the cap counts only new run requests; at most five attempts per partition.
"Complete" means every Gemeinde has both values for the lead time.
"""

import requests
import dagster as dg

from src.database.forecast import partition_complete
from src.dagster_pipeline.jobs import FORECAST_JOB
from src.dagster_pipeline.partitions import (
    WEATHER_LEAD_TIMES,
    weather_partition_key,
)
from src.dwd_icon_d2_ruc import (
    advertised_run_times,
    make_session,
)
from src.dwd_weather_availability import (
    dwd_polling_window_open,
    find_ready_weather_forecasts,
)
from src.retention.forecast_policy import forecast_partition_window_start


RUN_DISCOVERY_INDICATOR = "T_2M"
SENSOR_MAX_RUN_TIMES = 3
SENSOR_MINIMUM_INTERVAL_SECONDS = 300
SENSOR_MAX_ATTEMPTS = 5
SENSOR_MAX_RUN_REQUESTS_PER_TICK = 10

WEATHER_RUN_SCOPE_TAG = "weather_run_scope"
FORECAST_PIPELINE_RUN_SCOPE = "forecast_pipeline"

# A partition whose latest run has one of these statuses gets no new run.
NO_NEW_RUN_STATUSES = frozenset(
    {
        dg.DagsterRunStatus.NOT_STARTED,
        dg.DagsterRunStatus.QUEUED,
        dg.DagsterRunStatus.STARTING,
        dg.DagsterRunStatus.STARTED,
        dg.DagsterRunStatus.CANCELING,
        dg.DagsterRunStatus.SUCCESS,
    }
)

def next_attempt(runs) -> int | None:
    """
    Attempt number for a new run, or None when there must not be one
    (a run is in progress or succeeded, or all attempts are used up).

    `runs` is newest first, as DagsterInstance.get_runs returns them.
    """
    if runs and runs[0].status in NO_NEW_RUN_STATUSES:
        return None

    attempt = len(runs) + 1
    if attempt > SENSOR_MAX_ATTEMPTS:
        return None

    return attempt


def weather_sensor_run_key(
    forecast,
    attempt: int,
) -> str:
    """
    Stable idempotency key for one forecast-pipeline attempt.

    This namespace is distinct from historical acquisition-only runs,
    so earlier run keys cannot suppress a current full-pipeline request.
    """
    return (
        "dwd_icon_d2_ruc_forecast:"
        f"{forecast.run_label}:"
        f"{forecast.lead_time_label}:"
        f"attempt_{attempt}"
    )


def _skip_reason_for_decision(
    decision,
) -> dg.SkipReason:
    if decision.latest_incomplete is not None:
        availability = decision.latest_incomplete
        forecast = availability.forecast
        missing = ", ".join(
            availability.missing_indicators
        )

        return dg.SkipReason(
            "No complete pending DWD weather partition is ready. "
            f"Latest incomplete candidate: "
            f"{forecast.run_label} × "
            f"{forecast.lead_time_label}; "
            f"missing: {missing}."
        )

    if decision.already_complete_forecasts > 0:
        return dg.SkipReason(
            "No pending weather partition found in the recent "
            "DWD run window; checked candidates are already complete "
            "for every Gemeinde or already have a pipeline run."
        )

    return dg.SkipReason(
        "No eligible DWD weather forecast candidate was found."
    )


@dg.sensor(
    job=FORECAST_JOB,
    minimum_interval_seconds=SENSOR_MINIMUM_INTERVAL_SECONDS,
    default_status=dg.DefaultSensorStatus.STOPPED,
    description=(
        "Poll DWD ICON D2 RUC and launch forecast partitions "
        "after all four required fields are available."
    ),
)
def dwd_forecast_availability_sensor(
    context,
):
    if not dwd_polling_window_open():
        return dg.SkipReason(
            "Outside DWD polling window (:30-:59 each hour)"
        )

    runs_by_forecast: dict = {}

    def forecast_runs(forecast):
        key = (forecast.run_label, forecast.lead_time_label)
        if key not in runs_by_forecast:
            runs_by_forecast[key] = context.instance.get_runs(
                filters=dg.RunsFilter(
                    tags={
                        "forecast_run_time": forecast.run_label,
                        "forecast_lead_time": forecast.lead_time_label,
                        WEATHER_RUN_SCOPE_TAG: FORECAST_PIPELINE_RUN_SCOPE,
                    }
                )
            )
        return runs_by_forecast[key]

    def nothing_to_submit(forecast) -> bool:
        # Leave partitions with a run out before the per-tick cap,
        # so the cap counts only new run requests.
        return (
            partition_complete(forecast)
            or next_attempt(forecast_runs(forecast)) is None
        )
    try:
        with make_session() as session:
            run_times = advertised_run_times(
                session,
                RUN_DISCOVERY_INDICATOR,
            )

            if not run_times:
                return dg.SkipReason(
                    "DWD advertised no "
                    f"{RUN_DISCOVERY_INDICATOR} "
                    "forecast runs."
                )

            decision = find_ready_weather_forecasts(
                session,
                advertised_run_times=run_times,
                already_complete_fn=nothing_to_submit,
                lead_time_labels=WEATHER_LEAD_TIMES,
                minimum_run_time=forecast_partition_window_start(),
                max_run_times=SENSOR_MAX_RUN_TIMES,
                max_ready_forecasts=SENSOR_MAX_RUN_REQUESTS_PER_TICK,
            )

            context.log.info(
                "Availability helper found ready forecasts: %s",
                [
                    (
                        item.forecast.run_label,
                        item.forecast.lead_time_label,
                    )
                    for item in decision.ready
                ],
            )

    except requests.RequestException as exc:
        context.log.warning(
            "DWD availability check failed: %s",
            exc,
        )
        return dg.SkipReason(
            "Could not read DWD availability because of a "
            f"network/HTTP error: {exc}"
        )

    if not decision.ready:
        return _skip_reason_for_decision(decision)

    run_requests = []

    for availability in decision.ready[:SENSOR_MAX_RUN_REQUESTS_PER_TICK]:
        forecast = availability.forecast

        runs = forecast_runs(forecast)
        attempt = next_attempt(runs)

        latest_run = runs[0] if runs else None

        context.log.info(
            "Forecast %s × %s has %d prior pipeline runs; "
            "latest status = %s",
            forecast.run_label,
            forecast.lead_time_label,
            len(runs),
            (
                latest_run.status.value
                if latest_run
                else "NONE"
            ),
        )

        if attempt is None:
            continue

        run_requests.append(
            dg.RunRequest(
                run_key=weather_sensor_run_key(
                    forecast,
                    attempt,
                ),
                partition_key=weather_partition_key(
                    forecast
                ),
                tags={
                    "source": "dwd_icon_d2_ruc",
                    "forecast_run_time": forecast.run_label,
                    "forecast_lead_time": (
                        forecast.lead_time_label
                    ),
                    "attempt": str(attempt),
                    WEATHER_RUN_SCOPE_TAG: (
                        FORECAST_PIPELINE_RUN_SCOPE
                    ),
                },
            )
        )

    context.log.info(
        "Submitting %d weather run requests: %s",
        len(run_requests),
        [
            request.partition_key
            for request in run_requests
        ],
    )

    return dg.SensorResult(
        run_requests=run_requests
    )
