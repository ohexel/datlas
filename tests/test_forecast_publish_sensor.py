"""The publish sensor: one publish per newest complete run, retried on failure."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import dagster as dg
import pytest

from src.dagster_pipeline.definitions import defs
from src.dagster_pipeline.sensors import dwd_forecast, forecast_publish


RUN = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def instance():
    with dg.DagsterInstance.ephemeral() as dagster_instance:
        yield dagster_instance


def _patch_database(monkeypatch, run_time):
    @contextmanager
    def fake_connection(*, application_name):
        yield None

    monkeypatch.setattr(forecast_publish, "database_connection", fake_connection)
    monkeypatch.setattr(forecast_publish, "newest_complete_run", lambda connection: run_time)


def _patch_previous_runs(monkeypatch, statuses, observed=None):
    def get_runs(self, *args, **kwargs):
        if observed is not None:
            observed.update(kwargs["filters"].tags)
        return [SimpleNamespace(status=status) for status in statuses]

    monkeypatch.setattr(dg.DagsterInstance, "get_runs", get_runs)


def _tick(instance):
    context = dg.build_sensor_context(
        instance=instance, repository_def=defs.get_repository_def()
    )
    return forecast_publish.forecast_publish_sensor.evaluate_tick(context)


def test_no_complete_run_skips(monkeypatch, instance) -> None:
    _patch_database(monkeypatch, None)
    tick = _tick(instance)
    assert tick.run_requests == []
    assert "No complete forecast run" in tick.skip_message


def test_newest_complete_run_is_published_once(monkeypatch, instance) -> None:
    # A run time from a session in another zone names the same UTC run.
    _patch_database(monkeypatch, RUN.astimezone(timezone(timedelta(hours=1))))
    observed: dict = {}
    _patch_previous_runs(monkeypatch, [], observed)

    (request,) = _tick(instance).run_requests

    assert request.run_key == "forecast_publish:20261125T1500:attempt_1"
    assert request.tags["forecast_run_time"] == "20261125T1500"
    assert observed == {
        "forecast_run_time": "20261125T1500",
        "publish_run_scope": "forecast_publish",
    }


@pytest.mark.parametrize(
    "statuses",
    [
        [dg.DagsterRunStatus.SUCCESS],
        [dg.DagsterRunStatus.STARTED],
        [dg.DagsterRunStatus.FAILURE] * dwd_forecast.SENSOR_MAX_ATTEMPTS,
    ],
)
def test_published_running_or_exhausted_run_gets_no_request(
    monkeypatch, instance, statuses
) -> None:
    _patch_database(monkeypatch, RUN)
    _patch_previous_runs(monkeypatch, statuses)

    tick = _tick(instance)

    assert tick.run_requests == []
    assert "20261125T1500" in tick.skip_message


def test_both_forecast_sensors_start_stopped() -> None:
    sensors = {sensor.name: sensor for sensor in defs.sensors}
    for name in ("dwd_forecast_availability_sensor", "forecast_publish_sensor"):
        assert sensors[name].default_status == dg.DefaultSensorStatus.STOPPED
    assert sensors["forecast_publish_sensor"].job_name == "forecast_publish"
    assert sensors["dwd_forecast_availability_sensor"].job_name == "forecast"
