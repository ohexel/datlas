"""Run one complete 25-point forecast (lead hours 0-24) without the sensor.

Usage:
    uv run --env-file .env python -m src.run_forecast \\
        --run-time "$(date -u -d '3 hours ago' +%Y%m%dT%H00)"

Each lead time is one Dagster partition of the `forecast` job
(the four raw DWD fields plus the aggregation to Gemeinden). Partitions
already complete for every Gemeinde are skipped. Afterwards the
`forecast_publish` job publishes the run, applies retention and
runs checks 5-6.
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

import requests

from src.dagster_home import ensure_dagster_home, execute_job
from src.database.connection import database_connection
from src.dagster_pipeline.partitions import (
    WEATHER_LEAD_TIMES,
    weather_partition_key,
)
from src.dwd_icon_d2_ruc import field_url, make_session
from src.dwd_weather_availability import (
    REQUIRED_WEATHER_INDICATORS,
    check_forecast_availability,
)
from src.forecast_key import (
    ForecastKey,
    ProjectPaths,
    RUN_LABEL_FORMAT,
    parse_lead_time,
)
from src.ingestion.contract import GEOGRAPHY_VERSION
from src.retention.forecast_policy import (
    forecast_partition_window_start,
    forecast_retention_hours,
)


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ForecastUnavailableError(RuntimeError):
    """The requested partition cannot be acquired or materialized."""


def ensure_forecast_sources_available(
    forecast: ForecastKey,
    *,
    project_root: Path = PROJECT_ROOT,
    session_factory: Callable[[], requests.Session] = make_session,
) -> None:
    """Check only source fields that have not already been retained locally."""
    paths = ProjectPaths(project_root=project_root)
    remote_indicators = tuple(
        indicator
        for indicator in REQUIRED_WEATHER_INDICATORS
        if not paths.raw_icon_field(
            indicator=indicator,
            forecast=forecast,
        ).is_file()
    )

    # Retained raw GRIB files remain reprocessable after DWD removes a run.
    if not remote_indicators:
        return

    with session_factory() as session:
        availability = check_forecast_availability(
            session,
            forecast=forecast,
            indicators=remote_indicators,
        )

    if availability.complete:
        return

    first_missing = availability.missing_indicators[0]
    unavailable_fields = ", ".join(availability.missing_indicators)
    raise ForecastUnavailableError(
        f"Forecast run {forecast.run_time:%Y-%m-%d %H:%M} UTC "
        f"with lead time {forecast.lead_time_label} is unavailable from DWD.\n"
        "Recent runs may not yet be published; older runs may no longer "
        "be retained by DWD.\n"
        f"Unavailable fields: {unavailable_fields}.\n"
        f"Example source: {field_url(first_missing, forecast)}"
    )


def parse_forecast_request(
    run_time_label: str,
    lead_time_label: str,
) -> ForecastKey:
    """Validate one public forecast request before accessing DWD or PostgreSQL."""
    if lead_time_label not in WEATHER_LEAD_TIMES:
        raise ValueError(
            "Unsupported project lead time: "
            f"{lead_time_label}; choose one of {', '.join(WEATHER_LEAD_TIMES)}"
        )

    try:
        run_time = datetime.strptime(run_time_label, RUN_LABEL_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise ValueError(
            "Run time must use YYYYMMDDTHHMM in UTC, "
            "for example 20260824T1600."
        ) from exc

    if run_time.minute != 0:
        raise ValueError("Forecast run time must begin on a full UTC hour.")
    oldest_supported_run = forecast_partition_window_start()
    if run_time < oldest_supported_run:
        raise ForecastUnavailableError(
            f"Forecast run {run_time:%Y-%m-%d %H:%M} UTC is outside the "
            f"configured {forecast_retention_hours()}-hour retention window. "
            f"Choose a run at or after "
            f"{oldest_supported_run:%Y-%m-%d %H:%M} UTC."
        )
    if run_time > datetime.now(timezone.utc):
        raise ForecastUnavailableError(
            f"Forecast run {run_time:%Y-%m-%d %H:%M} UTC is in the future. "
            "Run labels use UTC, not Berlin-local time."
        )

    return ForecastKey(
        run_time=run_time,
        lead_time=parse_lead_time(lead_time_label),
    )


def partition_complete(forecast) -> bool:
    with database_connection(application_name="datlas_run_state") as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM normalized.gemeinde_forecast
                 WHERE run_time_utc = %s AND lead_time = %s
                   AND geography_version = %s
                   AND temperature_c IS NOT NULL
                   AND apparent_temperature_shade_c IS NOT NULL),
                (SELECT COUNT(*) FROM normalized.gemeinde
                 WHERE geography_version = %s)
            """,
            (forecast.run_time, forecast.lead_time_label, GEOGRAPHY_VERSION, GEOGRAPHY_VERSION),
        ).fetchone()
    return row is not None and row[1] > 0 and row[0] == row[1]


def run_forecast(
    run_time_label: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    # Validate the label before touching PostgreSQL, Dagster or DWD.
    run_time_utc = parse_forecast_request(run_time_label, WEATHER_LEAD_TIMES[0]).run_time
    ensure_dagster_home(project_root)
    materialized: list[str] = []
    skipped: list[str] = []
    started = perf_counter()

    for index, lead_time in enumerate(WEATHER_LEAD_TIMES, start=1):
        forecast = parse_forecast_request(run_time_label, lead_time)
        if partition_complete(forecast):
            skipped.append(lead_time)
            LOGGER.info("[%02d/25] %s already complete; skipping", index, lead_time)
            continue
        ensure_forecast_sources_available(forecast, project_root=project_root)
        LOGGER.info("[%02d/25] Materializing lead %s", index, lead_time)
        result = execute_job(
            "forecast",
            partition_key=weather_partition_key(forecast),
        )
        if not result.success:
            raise RuntimeError(
                f"Partition {lead_time} failed; inspect Dagster run {result.run_id}"
            )
        materialized.append(lead_time)

    partitions_seconds = perf_counter() - started
    publish_started = perf_counter()
    publish = execute_job("forecast_publish")
    if not publish.success:
        raise RuntimeError(f"Publishing failed; inspect Dagster run {publish.run_id}")
    checks = {
        evaluation.check_name: {
            "passed": evaluation.passed,
            "severity": evaluation.severity.value,
        }
        for evaluation in publish.get_asset_check_evaluations()
    }

    return {
        "status": "ready",
        "run_time_utc": run_time_utc.isoformat(),
        "materialized_lead_times": len(materialized),
        "already_complete_lead_times": len(skipped),
        "partitions_wall_seconds": round(partitions_seconds, 1),
        "publish_wall_seconds": round(perf_counter() - publish_started, 1),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one complete forecast (lead hours 0-24) directly without "
            "starting the sensor. Recent runs may not yet be published; older "
            "runs may no longer be available from DWD."
        )
    )
    parser.add_argument(
        "--run-time",
        required=True,
        help=(
            "Model run label in UTC, not Berlin-local time; "
            "for example 20260824T1600."
        ),
    )
    arguments = parser.parse_args(argv)
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.INFO,
    )
    try:
        result = run_forecast(arguments.run_time)
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        parser.exit(status=1, message=f"error: {exc}\n")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
