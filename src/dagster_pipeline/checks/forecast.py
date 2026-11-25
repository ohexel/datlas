"""Germany checks 4-6. Thresholds are documented in docs/germany-layer.md."""

import dagster as dg

from src.database.connection import database_connection
from src.dagster_pipeline.assets.forecast import (
    ANALYTICAL_DE_CURRENT_FORECAST_KEY,
    NORMALIZED_DE_ICON_BRIDGE_KEY,
)
from src.ingestion.contract import GEOGRAPHY_VERSION
from src.database.forecast import SOURCE_GRID_ID


# Check 4 (handover): Σ intersection / Gemeinde area >= 0.999.
MIN_BRIDGE_COVERAGE = 0.999
# Check 6: physical plausibility bounds, °C.
TEMPERATURE_BOUNDS_C = (-50.0, 50.0)
APPARENT_TEMPERATURE_BOUNDS_C = (-70.0, 60.0)
MAX_LISTED = 50


@dg.asset_check(asset=NORMALIZED_DE_ICON_BRIDGE_KEY, name="de_bridge_coverage")
def de_bridge_coverage() -> dg.AssetCheckResult:
    """Check 4: every Gemeinde is covered by ICON cells."""
    with database_connection(application_name="lwr_germany_check4") as connection:
        exceptions = connection.execute(
            "SELECT * FROM normalized.check_de_bridge_coverage(%s, %s, %s)",
            (GEOGRAPHY_VERSION, SOURCE_GRID_ID, MIN_BRIDGE_COVERAGE),
        ).fetchall()
        low, high, gemeinden = connection.execute(
            """
            SELECT MIN(s), MAX(s), COUNT(*) FROM (
                SELECT SUM(fraction_of_gemeinde) AS s
                FROM normalized.de_icon_cell_gemeinde_bridge
                WHERE geography_version = %s AND source_grid_id = %s
                GROUP BY ars
            ) AS coverage
            """,
            (GEOGRAPHY_VERSION, SOURCE_GRID_ID),
        ).fetchone()
    return dg.AssetCheckResult(
        passed=not exceptions and int(gemeinden) > 0,
        metadata={
            "min_coverage": MIN_BRIDGE_COVERAGE,
            "gemeinden_in_bridge": int(gemeinden),
            "observed_min_coverage": float(low or 0),
            "observed_max_coverage": float(high or 0),
            "exceptions": [f"{r[0]} {r[1]}: {r[2]:.6f}" for r in exceptions[:MAX_LISTED]],
            "exception_count": len(exceptions),
        },
        description="Σ cell intersection area / Gemeinde area is within [0.999, 1].",
    )


@dg.asset_check(asset=ANALYTICAL_DE_CURRENT_FORECAST_KEY, name="de_forecast_completeness")
def de_forecast_completeness() -> dg.AssetCheckResult:
    """Check 5: the served run is the newest loaded run.

    The served run is complete by definition (de_current_run), so the check
    looks for what that rule hides: a newer run that never completed, for
    example after a failed download or a refused partition. Warning only, as
    a newer run may still be loading."""
    with database_connection(application_name="lwr_germany_check5") as connection:
        runs = connection.execute(
            """
            SELECT run_time_utc, lead_time_count, gemeinde_lead_row_count,
                   expected_row_count, is_complete
            FROM normalized.de_forecast_run_completeness
            WHERE geography_version = %s
            ORDER BY run_time_utc DESC
            """,
            (GEOGRAPHY_VERSION,),
        ).fetchall()
        current = connection.execute(
            "SELECT run_time_utc FROM analytical.de_current_run"
        ).fetchone()
    served = None if current is None else current[0]
    passed = served is not None and runs[0][0] == served
    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.WARN,
        metadata={
            "current_run_time_utc": None if served is None else served.isoformat(),
            "runs": [
                f"{r[0].isoformat()}: {r[1]}/25 leads, {r[2]}/{r[3]} rows, "
                f"{'complete' if r[4] else 'incomplete'}"
                for r in runs
            ],
        },
        description=(
            "The served run (all Gemeinden × 25 lead times) is the newest "
            "loaded run; a newer incomplete run is listed and fails the check."
        ),
    )


@dg.asset_check(asset=ANALYTICAL_DE_CURRENT_FORECAST_KEY, name="de_forecast_plausibility")
def de_forecast_plausibility() -> dg.AssetCheckResult:
    """Check 6: physical bounds and no NULLs, for Gemeinden and cells."""
    t_low, t_high = TEMPERATURE_BOUNDS_C
    a_low, a_high = APPARENT_TEMPERATURE_BOUNDS_C
    with database_connection(application_name="lwr_germany_check6") as connection:
        row = connection.execute(
            """
            WITH cur AS (SELECT * FROM analytical.de_current_run),
            g AS (
                SELECT f.* FROM normalized.de_gemeinde_forecast AS f, cur
                WHERE f.run_time_utc = cur.run_time_utc
                  AND f.geography_version = cur.geography_version
            ),
            c AS (
                SELECT w.* FROM normalized.de_icon_cell_value AS w
                JOIN normalized.de_forecast_run AS r USING (run_time_utc)
                JOIN cur ON cur.run_time_utc = r.run_time_utc
                        AND cur.geography_version = r.geography_version
            )
            SELECT
                (SELECT COUNT(*) FROM g),
                (SELECT COUNT(*) FROM g WHERE temperature_c IS NULL
                    OR apparent_temperature_shade_c IS NULL),
                (SELECT COUNT(*) FROM g WHERE temperature_c NOT BETWEEN %s AND %s
                    OR apparent_temperature_shade_c NOT BETWEEN %s AND %s),
                (SELECT COUNT(*) FROM c),
                (SELECT COUNT(*) FROM c WHERE temperature_c IS NULL
                    OR apparent_temperature_shade_c IS NULL),
                (SELECT COUNT(*) FROM c WHERE temperature_c NOT BETWEEN %s AND %s
                    OR apparent_temperature_shade_c NOT BETWEEN %s AND %s),
                (SELECT MIN(temperature_c) FROM g), (SELECT MAX(temperature_c) FROM g),
                (SELECT MIN(apparent_temperature_shade_c) FROM g),
                (SELECT MAX(apparent_temperature_shade_c) FROM g)
            """,
            (t_low, t_high, a_low, a_high, t_low, t_high, a_low, a_high),
        ).fetchone()
    g_rows, g_null, g_out, c_rows, c_null, c_out, t_min, t_max, a_min, a_max = row
    passed = g_rows > 0 and c_rows > 0 and not (g_null or g_out or c_null or c_out)
    return dg.AssetCheckResult(
        passed=passed,
        metadata={
            "temperature_bounds_c": list(TEMPERATURE_BOUNDS_C),
            "apparent_temperature_bounds_c": list(APPARENT_TEMPERATURE_BOUNDS_C),
            "gemeinde_rows": int(g_rows),
            "gemeinde_null_rows": int(g_null),
            "gemeinde_out_of_bounds_rows": int(g_out),
            "cell_rows": int(c_rows),
            "cell_null_rows": int(c_null),
            "cell_out_of_bounds_rows": int(c_out),
            "observed_temperature_c": [t_min, t_max],
            "observed_apparent_temperature_c": [a_min, a_max],
        },
        description="Current run: no NULLs, values within physical bounds.",
    )


GERMANY_FORECAST_CHECKS = [
    de_bridge_coverage,
    de_forecast_completeness,
    de_forecast_plausibility,
]
