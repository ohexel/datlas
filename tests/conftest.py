"""Classify existing tests without moving files or weakening their assertions.

The Germany test modules set their own markers.
"""

from pathlib import Path

import pytest


DATABASE_TEST_FILES = {
    "test_apparent_temperature_sql.py",
    "test_database_boundary.py",
    "test_icon_cell_sql.py",
}

CONTRACT_TEST_FILES = {
    "test_apparent_temperature_sql.py",
    "test_forecast_key.py",
    "test_icon_grid_contract.py",
    "test_run_forecast.py",
    "test_weather_early_filtering.py",
    "test_weather_source_contract.py",
    "test_weather_raw_retention.py",
}


def pytest_ignore_collect(
    collection_path: Path,
    config: pytest.Config,
) -> bool | None:
    """Exclude optional workflows unavailable in the active project checkout."""
    del config
    if collection_path.name == "test_dagster_container.py":
        project_root = collection_path.parent.parent
        if not (project_root / "docker" / "dagster.yml").is_file():
            return True
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config

    for item in items:
        filename = item.path.name
        is_database_test = filename in DATABASE_TEST_FILES

        # This one configuration-boundary test is genuinely database-free.
        if item.name == "test_database_settings_reports_missing_variables":
            is_database_test = False

        if is_database_test:
            item.add_marker(pytest.mark.integration)
        if filename in CONTRACT_TEST_FILES:
            item.add_marker(pytest.mark.contract)
