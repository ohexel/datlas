# Testing

The tests protect operational contracts, not a coverage percentage. Each one
should be able to say in one sentence which goal, decision or observed
property of the data it protects, and fail if that broke. Tests that compared
constants with the same constants typed again, searched source text, or
duplicated another test were removed (triage of 14 Nov 2026 for the theme
tests, review of 25 Nov 2026 for the rest): 98 cases in 22 files.

Run them with `uv run python -m pytest` (plain `uv run pytest` cannot import
`src`).

| Level | Command | Needs | Cases | Time |
| --- | --- | --- | ---: | ---: |
| Default | `uv run python -m pytest` | nothing: no database, no network | 81 | about 6 s |
| Database | `uv run --env-file .env python -m pytest -m integration` | a running PostgreSQL/PostGIS; nothing loaded | 8 | about 10 s |
| Acceptance | `uv run --env-file .env python -m pytest -m acceptance` | the [first build](runbook.md#first-build) and one complete forecast run | 9 | about 45 s |
| All | `uv run --env-file .env python -m pytest -m ""` | as acceptance | 98 | about 75 s |

Markers are set in each test module (`pytestmark`) or on single tests; their
definitions and the default selection are in `pyproject.toml`. The `contract`
marker labels tests of a data, pipeline or serving contract;
`-m "contract and not integration and not acceptance"` selects the database-free
ones.

## Database tests

They need a database but no loaded data. Each applies the schema it needs and
loads small synthetic geographies, cells or workbooks inside a transaction
that is always rolled back, so nothing is left behind. One test creates and
drops a throwaway database of its own.

| Test | What it proves |
| --- | --- |
| `test_schema_files_build_the_database_from_empty_twice` | on a database without PostGIS, the schema files applied twice give exactly the 39 tables and views, 24 functions and 9 indexes they declare |
| `test_postgis_builds_icon_cells_in_epsg_3035` | cells are triangles in EPSG:3035 whose area equals the projection of their vertices; the grid check passes |
| `test_refresh_and_checks_classify_every_case` | population statuses, NULL never 0, and checks 1–3 on a synthetic geography |
| `test_static_hierarchy_is_safe_to_repeat` | `run_static` can run again: same VG250 file unchanged, another file refused |
| `test_partition_aggregation_and_retention_keeps_two_runs` | area weighting with hand-computed values, refusal of a field with missing values, switching only to complete runs, retention of two runs |
| `test_summaries_take_the_earliest_hour_on_a_tie` | the 24-hour maximum and minimum take the earliest hour on a tie, at all four levels |
| `test_refresh_serves_published_values_with_explicit_status` | published Kreis and Land values, kreisfreie Städte, statuses with reasons, checks 8–11 |
| `test_sector_refresh_and_checks_on_a_fixture_land` | Kreis and Land routes, Land-only indicators, checks 12–14 on synthetic workbooks |

## Acceptance tests

They read the installed database and write nothing. They check that all 17
asset checks pass (and that the test runs every registered check), that the
current views are complete at all four levels and roll up consistently, that
the employment and sector views cover every region with an explicit status,
that the Regionalreport counts employees at their place of work, and that the
map exports for all three themes can be built completely.

## Contracts in the default suite

| Concern | Tests | Protected assumption |
| --- | --- | --- |
| Zensus source | `test_raw.py` | The Zensus token is sent only as a header and never appears in an error; "-" (exactly zero) and 12-digit keys with leading zeros survive into raw. |
| DWD source | `test_dwd_icon_d2_ruc_helpers.py`, `test_dwd_weather_availability.py`, `test_icon_d2_ruc_field.py` | The DWD URL scheme; missing values marked in the GRIB bitmap become NaN; availability is checked newest run first, an incomplete newest run does not block an older complete one, and the checks stop after a bounded batch; a field that fails to decode or has the wrong number of points is quarantined and refused. |
| Forecast identity | `test_forecast_key.py`, `test_dagster_partitions.py` | Valid time = run + lead; the file layout of retained GRIB files; partition keys round-trip; the partition window holds at most 24 runs. |
| Runners | `test_run_forecast.py` | Run labels are UTC and checked before DWD is contacted; retained files are reprocessed without DWD; errors are short and without a traceback; `run_static --help` prints help and starts no job. |
| Sensors | `test_dwd_forecast_sensor.py`, `test_forecast_publish_sensor.py` | At most ten new partitions per check, newest first; partitions with a run are left out before the cap; failed partitions are retried up to five attempts, running or finished ones never duplicated; each complete run is published once, named by its UTC run time; both sensors start stopped. |
| GRIB retention | `test_grib_retention.py` | Expired files go with their sidecar and empty directories; the 24-hour boundary is kept; a dry run deletes nothing; the window is 1–24 hours; files of a run still in the database stay. |
| Definitions | `test_definitions.py` | One asset group per theme, run by exactly its jobs; the 17 checks are registered; only the forecast jobs keep the 300 s run limit. |
| Employment theme | `test_employment.py` | Suppressed values are kept as `*`, a changed BA layout stops the load, the release sensor asks only for the next vintage, missing values stay explicit in the map file. |
| Sector theme | `test_sectors.py` | Parsers read five quarters and refuse changed layouts; the BA client is considerate and stops on rate limits; reviewed discrepancies pass only at their documented size; each level shows only what it publishes. |
| Map | `test_contracts.py`, `test_dashboard.py` | Required attribution, pinned map libraries without a basemap, no data in Git, maxima and minima kept apart, Range requests in the preview. |
| Set-up | `test_docker_setup.py`, `test_lint.py` | Own Compose project, container and port; Dagster on the Compose database; no `data/` in the image build; the ruff rules (no `from __future__ import annotations`, which Dagster cannot read). |

## Why some tests use `monkeypatch`

`monkeypatch` is a pytest fixture that temporarily replaces an external
boundary for a single test and restores it afterward. Here it replaces a
network request, database connector, clock or Dagster instance when the test
needs to verify the project's control flow without calling the real service.
For example, the BA client test replaces the network and the clock with small
fakes and asserts that HTTP 429 leads to waits, a shared cool-down and a stop;
the sensor tests replace DWD and the run history and assert which runs are
requested. A fabricated value that merely reproduces an expected answer
without calling project code does not test anything and is not kept.

Real PostgreSQL/PostGIS behaviour belongs in database tests; live external
services are checked in operation, not in the test suite.
