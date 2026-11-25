"""Acceptance: run after `python -m src.run_static` and at least one
complete `python -m src.run_forecast`. Reads the installed database
only; writes nothing.

    uv run --env-file .env python -m pytest -m acceptance tests/test_acceptance.py
"""

import pytest

from src.database.connection import database_connection
from src.ingestion.contract import GEOGRAPHY_VERSION, VG250_CONTRACT


pytestmark = pytest.mark.acceptance

LEAD_TIMES = 25
LAENDER = VG250_CONTRACT.feature_counts["lan"][1]
KREISE = VG250_CONTRACT.feature_counts["krs"][1]
GEMEINDEN = VG250_CONTRACT.feature_counts["gem"][1]
# Roll-up identities: floating-point summation order only.
ROLLUP_TOLERANCE_C = 1e-9


def _one(sql: str, params: tuple | dict = ()) -> tuple:
    with database_connection(application_name="datlas_acceptance") as connection:
        return connection.execute(sql, params).fetchone()


def _all(sql: str, params: tuple | dict = ()) -> list[tuple]:
    with database_connection(application_name="datlas_acceptance") as connection:
        return connection.execute(sql, params).fetchall()


def test_all_checks_pass_on_installed_data() -> None:
    from src.dagster_pipeline.checks.employment import EMPLOYMENT_CHECKS
    from src.dagster_pipeline.checks.forecast import FORECAST_CHECKS
    from src.dagster_pipeline.checks.normalized import NORMALIZED_CHECKS
    from src.dagster_pipeline.checks.sectors import SECTOR_CHECKS

    for check in (
        *NORMALIZED_CHECKS,
        *FORECAST_CHECKS,
        *EMPLOYMENT_CHECKS,
        *SECTOR_CHECKS,
    ):
        result = check.node_def.compute_fn.decorated_fn()
        assert result.passed, (check.check_key.name, result.metadata)


def test_current_views_are_complete_at_all_four_levels() -> None:
    row = _one(
        """
        SELECT
            (SELECT COUNT(*) FROM analytical.current_gemeinde_forecast_25h),
            (SELECT COUNT(DISTINCT ars) FROM analytical.current_gemeinde_forecast_25h),
            (SELECT COUNT(*) FROM analytical.current_kreis_forecast_25h),
            (SELECT COUNT(*) FROM analytical.current_land_forecast_25h),
            (SELECT COUNT(*) FROM analytical.current_bund_forecast_25h),
            (SELECT COUNT(*) FROM analytical.current_gemeinde_summary),
            (SELECT COUNT(DISTINCT run_time_utc) FROM analytical.current_kreis_forecast_25h),
            (SELECT COUNT(DISTINCT lead_hour) FROM analytical.current_bund_forecast_25h)
        """
    )
    assert row == (
        GEMEINDEN * LEAD_TIMES,
        GEMEINDEN,
        KREISE * LEAD_TIMES,
        LAENDER * LEAD_TIMES,
        LEAD_TIMES,
        GEMEINDEN,
        1,
        LEAD_TIMES,
    )


def test_rollups_are_consistent_across_levels() -> None:
    # Area: Σ over Länder of (Land mean × Land area) / Σ area = Bund mean.
    # Population: same identity with Land population weights.
    row = _one(
        """
        WITH land AS (
            SELECT lead_hour,
                   SUM(temperature_area_weighted_c * area_m2) / SUM(area_m2) AS t_area,
                   SUM(temperature_population_weighted_c * population_total)
                       / SUM(population_total) AS t_pop
            FROM analytical.current_land_forecast_25h
            GROUP BY lead_hour
        )
        SELECT MAX(ABS(land.t_area - b.temperature_area_weighted_c)),
               MAX(ABS(land.t_pop - b.temperature_population_weighted_c)),
               (SELECT SUM(population_total) FROM analytical.current_land_forecast_25h
                WHERE lead_hour = 0)
        FROM land
        JOIN analytical.current_bund_forecast_25h AS b USING (lead_hour)
        """
    )
    area_difference, population_difference, population = row
    assert area_difference < ROLLUP_TOLERANCE_C
    assert population_difference < ROLLUP_TOLERANCE_C
    # Population weights are the census Gemeinde values (Σ Länder, check 3).
    assert population == 82_711_282


def test_map_values_export_is_complete_for_the_current_run() -> None:
    from src.export_germany_dashboard import collect_values

    with database_connection(application_name="datlas_acceptance") as connection:
        values = collect_values(connection)  # raises on any gap
        current = connection.execute(
            "SELECT run_time_utc FROM analytical.current_run"
        ).fetchone()[0]
    assert values["run_time_utc"] == current.strftime("%Y-%m-%dT%H:%MZ")
    assert values["tiles"] == f"{GEOGRAPHY_VERSION}.pmtiles"
    assert len(values["valid_times_berlin"]) == LEAD_TIMES
    assert (len(values["lan"]), len(values["krs"]), len(values["gem"])) == (
        LAENDER, KREISE, GEMEINDEN,
    )
    assert values["bund"]["population_total"] == 82_711_282
    # Minima for the Höchst-/Tiefstwerte switch: present everywhere, never
    # above the maximum of the same measure.
    for level in ("gem", "krs", "lan"):
        for record in values[level].values():
            minima = [k for k in record if k.startswith("min_") and k.endswith("_c")]
            assert len(minima) == (2 if level == "gem" else 4)
            for k in minima:
                assert ("max_" + k[4:]) in record and (k.removesuffix("_c") + "_lead_hour") in record
                if record[k] is not None:
                    assert record[k] <= record["max_" + k[4:]]
    bund = values["bund"]
    for weighting in ("area", "population"):
        key = f"apparent_temperature_shade_{weighting}_weighted_c"
        assert bund[f"min_{key}"] <= bund[f"max_{key}"]


# ---------------------------------------------------------------------------
# Second theme: employment (BA Gemeindedaten), after python -m src.run_employment
# ---------------------------------------------------------------------------
def test_employment_view_covers_every_region_with_an_explicit_status() -> None:
    from src.ingestion.contract import BA_GEMEINDEDATEN_CONTRACT

    rows = dict(
        ((level, status), count)
        for level, status, count in _all(
            """
            SELECT level, jobs_ratio_status, COUNT(*)
            FROM analytical.current_employment GROUP BY 1, 2
            """
        )
    )
    reference_date = _one(
        "SELECT DISTINCT reference_date FROM analytical.current_employment"
    )[0]
    known = BA_GEMEINDEDATEN_CONTRACT.vintage(reference_date)
    assert sum(c for (level, _), c in rows.items() if level == "gem") == GEMEINDEN
    assert rows[("krs", "value")] == KREISE
    assert rows[("lan", "value")] == LAENDER
    assert rows[("sta", "value")] == 1
    if known is not None:
        # Not reported: the unincorporated areas without employees (204) and
        # the Gemeinden merged after the geography version.
        assert rows[("gem", "not_reported")] == 204 + len(known.geography_without_source)
    # The ratio is exactly the quotient of the two published values.
    mismatches = _one(
        """
        SELECT COUNT(*) FROM analytical.current_employment
        WHERE jobs_ratio_status = 'value'
          AND jobs_ratio IS DISTINCT FROM employees_workplace / employees_residence
        """
    )[0]
    assert mismatches == 0


def test_employment_export_is_complete() -> None:
    from src.export_germany_dashboard import collect_employment

    with database_connection(application_name="datlas_acceptance") as connection:
        employment = collect_employment(connection)
    assert employment is not None
    assert (len(employment["lan"]), len(employment["krs"]), len(employment["gem"])) == (
        LAENDER, KREISE, GEMEINDEN,
    )
    bund = employment["bund"]
    assert bund["jobs_ratio_status"] == "value"
    assert bund["employees_workplace"] >= sum(
        r["employees_workplace"] for r in employment["lan"].values()
    )


# ---------------------------------------------------------------------------
# Third theme: sectors, after python -m src.run_sectors
# ---------------------------------------------------------------------------
def test_sector_view_covers_every_kreis_and_land_with_an_explicit_status() -> None:
    rows = dict(
        ((level, status), count)
        for level, status, count in _all(
            """
            SELECT level, employees_total_status, COUNT(*)
            FROM analytical.current_sectors GROUP BY 1, 2
            """
        )
    )
    assert rows == {("krs", "value"): KREISE, ("lan", "value"): LAENDER, ("sta", "value"): 1}
    # Land groups are own calculations with a stated basis; Kreis groups are
    # published as they are.
    bases = {
        (level, basis)
        for level, basis in _all(
            "SELECT DISTINCT level, metal_electrical_steel_basis FROM analytical.current_sectors"
        )
    }
    assert {basis for level, basis in bases if level == "krs"} == {"published"}
    assert {basis for level, basis in bases if level != "krs"} <= {"sum_of_divisions", "sum_of_kreise"}
    # The four divisions exist only for Länder and Germany.
    statuses = {
        row[0]
        for row in _all(
            "SELECT DISTINCT motor_vehicles_status FROM analytical.current_sectors WHERE level = 'krs'"
        )
    }
    assert statuses == {"not_published_at_level"}
    # A share exists exactly where both values are published.
    mismatches = _one(
        """
        SELECT COUNT(*) FROM analytical.current_sectors
        WHERE (metal_electrical_steel_share_status = 'value')
              <> (metal_electrical_steel_status = 'value' AND employees_total_status = 'value')
           OR metal_electrical_steel_share IS DISTINCT FROM
              CASE WHEN metal_electrical_steel_share_status = 'value'
                   THEN metal_electrical_steel / employees_total END
        """
    )[0]
    assert mismatches == 0


def test_regionalreport_counts_employees_at_place_of_work() -> None:
    # Where both BA products have the same date (30 June), the Kreis totals of
    # the Regionalreport equal the Gemeindedaten's employees at place of work.
    compared, different = _one(
        """
        SELECT COUNT(*), COUNT(*) FILTER (WHERE r.value <> g.value)
        FROM normalized.indicator_value AS r
        JOIN normalized.indicator_value AS g
          ON g.level = 'krs' AND g.region_key = r.region_key
         AND g.reference_date = r.reference_date
         AND g.geography_version = r.geography_version
         AND g.indicator_code = 'employees_workplace' AND g.value_status = 'value'
        WHERE r.level = 'krs' AND r.indicator_code = 'sector_total' AND r.value_status = 'value'
        """
    )
    assert compared == KREISE
    assert different == 0


def test_sector_export_is_complete() -> None:
    from src.export_germany_dashboard import collect_sectors

    with database_connection(application_name="datlas_acceptance") as connection:
        sectors = collect_sectors(connection)
    assert sectors is not None
    assert (len(sectors["lan"]), len(sectors["krs"])) == (LAENDER, KREISE)
    bund = sectors["bund"]
    for measure in ("motor_vehicles", "machinery", "chemicals", "steel", "metal_electrical_steel"):
        assert bund[measure] is not None and bund[measure] < bund["employees_total"]
    assert all("motor_vehicles" not in record for record in sectors["krs"].values())
