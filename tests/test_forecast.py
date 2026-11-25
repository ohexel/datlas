"""Germany layer, forecast: SQL aggregation, refusal of missing model values
and retention, the tie rule of the 24-hour summaries."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import psycopg
import pytest


# ---------------------------------------------------------------------------
# Integration: fixture geography inside a rolled-back transaction.
# ---------------------------------------------------------------------------
FIXTURE = "fixture-m3"
GRID = "fixture_grid"


def _square(x: float, y: float, size: float = 1000.0) -> str:
    return (
        f"SRID=3035;POLYGON(({x} {y},{x + size} {y},{x + size} {y + size},"
        f"{x} {y + size},{x} {y}))"
    )


@pytest.mark.integration
def test_partition_aggregation_and_retention_keeps_two_runs() -> None:
    from src.database.connection import database_connection
    from src.database.load import copy_rows
    from src.database.forecast import apply_forecast_schema

    x, y = 4_500_000.0, 3_200_000.0
    land = f"SRID=3035;MULTIPOLYGON((({x} {y},{x + 2000} {y},{x + 2000} {y + 1000},{x} {y + 1000},{x} {y})))"
    gem_a = f"SRID=3035;MULTIPOLYGON((({x} {y},{x + 1000} {y},{x + 1000} {y + 1000},{x} {y + 1000},{x} {y})))"
    gem_b = f"SRID=3035;MULTIPOLYGON((({x + 1000} {y},{x + 2000} {y},{x + 2000} {y + 1000},{x + 1000} {y + 1000},{x + 1000} {y})))"
    # Cell 1 covers A; cells 2 and 3 split B 50/50 (fractions of Gemeinde).
    bridge_rows = [(1, "990010000001", 1.0), (2, "990010000002", 0.5), (3, "990010000002", 0.5)]
    stage = {  # cell -> (T K, RH %, U, V)
        1: (293.15, 50.0, 3.0, 4.0),
        2: (283.15, 80.0, 0.0, 1.0),
        3: (288.15, 60.0, 1.0, 0.0),
    }
    base = datetime(2099, 1, 1, tzinfo=timezone.utc)

    with database_connection(application_name="lwr_germany_m3_test") as connection:
        with connection.transaction(force_rollback=True):
            apply_forecast_schema(connection)
            connection.execute(
                "INSERT INTO normalized.de_land VALUES (%s,'99','Fixland',%s,2e6,'f')",
                (FIXTURE, land),
            )
            connection.execute(
                "INSERT INTO normalized.de_kreis VALUES (%s,'99001','99','Fixkreis','Kreis',NULL,%s,2e6,'f')",
                (FIXTURE, land),
            )
            for ars, ags, geometry in (
                ("990010000001", "99001001", gem_a),
                ("990010000002", "99001002", gem_b),
            ):
                connection.execute(
                    "INSERT INTO normalized.de_gemeinde VALUES "
                    "(%s,%s,%s,'99001','99','G','Gemeinde',false,%s,1e6,'f')",
                    (FIXTURE, ars, ags, geometry),
                )
            for cell in (1, 2, 3):
                connection.execute(
                    "INSERT INTO normalized.de_icon_cell VALUES (%s,%s,%s,%s,1e6)",
                    (FIXTURE, GRID, cell, _square(x + 500 * (cell - 1), y)),
                )
            for cell, ars, fraction in bridge_rows:
                connection.execute(
                    "INSERT INTO normalized.de_icon_cell_gemeinde_bridge VALUES "
                    "(%s,%s,%s,%s,%s,1e6,%s)",
                    (FIXTURE, GRID, cell, ars, fraction * 1e6, fraction),
                )

            def load_partition(run_time: datetime, hour: int, rows: list[tuple]) -> None:
                connection.execute(
                    "CREATE TEMP TABLE de_cell_stage (cell_index integer PRIMARY KEY, "
                    "temperature_k double precision, relative_humidity_percent "
                    "double precision, wind_u_10m_ms double precision, "
                    "wind_v_10m_ms double precision)"
                )
                copy_rows(
                    connection, schema="pg_temp", table="de_cell_stage",
                    columns=("cell_index", "temperature_k",
                             "relative_humidity_percent", "wind_u_10m_ms",
                             "wind_v_10m_ms"),
                    rows=rows,
                )
                connection.execute(
                    "SELECT * FROM normalized.refresh_de_forecast_partition(%s,%s,%s,%s,%s)",
                    (run_time, f"PT{hour:03d}H00M", run_time + timedelta(hours=hour),
                     FIXTURE, GRID),
                )
                connection.execute("DROP TABLE pg_temp.de_cell_stage")

            def load_run(run_time: datetime, leads: int) -> None:
                for hour in range(leads):
                    load_partition(run_time, hour, [(c, v[0] + hour, *v[1:]) for c, v in stage.items()])

            runs = [base + timedelta(hours=h) for h in range(4)]
            for run_time in runs[:3]:
                load_run(run_time, 25)
            load_run(runs[3], 3)  # newer run still loading

            # A missing model value (NaN, staged as NULL) refuses the partition
            # instead of averaging B over cell 2 alone.
            with pytest.raises(psycopg.errors.RaiseException, match="1 staged cells have missing values"):
                with connection.transaction():
                    load_partition(runs[3], 3, [(1, 293.15, 50.0, 3.0, 4.0),
                                                (2, 283.15, 80.0, 0.0, 1.0),
                                                (3, 288.15, None, 1.0, 0.0)])

            # Gemeinde values: A = cell 1, B = mean of cells 2 and 3. Expected
            # values are hand-computed from the formula
            # T + 0.33 e - 0.70 v - 4.00 with e = RH/100 * 6.105 * exp(17.27 T / (237.7 + T));
            # they equal normalized.calculate_apparent_temperature_shade_c(20, 50, 5) and
            # the mean of (10, 80, 1) and (15, 60, 1), queried on 2026-11-14.
            sql_values = dict(
                connection.execute(
                    "SELECT ars, apparent_temperature_shade_c FROM normalized.de_gemeinde_forecast "
                    "WHERE geography_version = %s AND run_time_utc = %s AND lead_time = 'PT000H00M'",
                    (FIXTURE, runs[0]),
                ).fetchall()
            )
            assert sql_values["990010000001"] == pytest.approx(16.348242312858147, abs=1e-12)
            assert sql_values["990010000002"] == pytest.approx(11.103011743711562, abs=1e-12)

            current = connection.execute(
                "SELECT run_time_utc FROM normalized.de_forecast_run_completeness "
                "WHERE geography_version = %s AND is_complete ORDER BY 1 DESC LIMIT 1",
                (FIXTURE,),
            ).fetchone()[0]
            assert current == runs[2]  # incomplete newer run is not current

            kept, cells, gemeinden = connection.execute(
                "SELECT * FROM normalized.prune_de_forecast(%s, 2)", (FIXTURE,)
            ).fetchone()
            assert kept == runs[1]
            assert gemeinden == 2 * 25
            assert cells == 3 * 25
            remaining = [
                r[0] for r in connection.execute(
                    "SELECT DISTINCT run_time_utc FROM normalized.de_gemeinde_forecast "
                    "WHERE geography_version = %s ORDER BY 1",
                    (FIXTURE,),
                )
            ]
            assert remaining == runs[1:]


@pytest.mark.integration
def test_summaries_take_the_earliest_hour_on_a_tie() -> None:
    """24-hour maximum and minimum: highest or lowest value, earliest time on
    a tie, at all four levels. Real values almost never tie (none on
    14 Nov 2026), so the rule is tested with a constructed run: a one-Gemeinde
    geography with a complete run in 2099, which is the current run inside
    this rolled-back transaction only."""
    from src.database.connection import database_connection
    from src.database.forecast import apply_forecast_schema

    version, ars = "fixture-tie", "990010000001"
    square = (
        "SRID=3035;MULTIPOLYGON(((4500000 3200000,4501000 3200000,"
        "4501000 3201000,4500000 3201000,4500000 3200000)))"
    )
    run = datetime(2099, 6, 1, tzinfo=timezone.utc)
    temperature = {3: 9.0, 7: 9.0, 10: 1.0, 20: 1.0}   # max at 3 and 7, min at 10 and 20
    apparent = {5: 4.0, 6: 4.0, 0: -3.0, 24: -3.0}     # max at 5 and 6, min at 0 and 24
    expected = {"max_temperature": 3, "min_temperature": 10,
                "max_apparent_temperature_shade": 5, "min_apparent_temperature_shade": 0}

    def berlin(hour: int) -> datetime:
        return (run + timedelta(hours=hour)).astimezone(ZoneInfo("Europe/Berlin")).replace(tzinfo=None)

    with database_connection(application_name="lwr_germany_tie_test") as connection:
        with connection.transaction(force_rollback=True):
            apply_forecast_schema(connection)
            connection.execute(
                "INSERT INTO normalized.de_land VALUES (%s,'99','Fixland',%s,1e6,'f')", (version, square)
            )
            connection.execute(
                "INSERT INTO normalized.de_kreis VALUES (%s,'99001','99','Fixkreis','Kreis',NULL,%s,1e6,'f')",
                (version, square),
            )
            connection.execute(
                "INSERT INTO normalized.de_gemeinde VALUES "
                "(%s,%s,'99001001','99001','99','Fixdorf','Gemeinde',false,%s,1e6,'f')",
                (version, ars, square),
            )
            connection.execute(
                "INSERT INTO normalized.de_gemeinde_population VALUES "
                "(%s,%s,100,'census_value','100','2022-05-15','fixture','f')",
                (version, ars),
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO normalized.de_gemeinde_forecast VALUES (%s,%s,%s,%s,'fixture_grid',%s,%s,%s)",
                    [
                        (run, f"PT{hour:03d}H00M", run + timedelta(hours=hour), version, ars,
                         temperature.get(hour, 5.0), apparent.get(hour, 2.0))
                        for hour in range(25)
                    ],
                )
            assert connection.execute(
                "SELECT run_time_utc FROM analytical.de_current_run"
            ).fetchone()[0] == run

            gemeinde = connection.execute(
                """
                SELECT max_temperature_at_berlin, min_temperature_at_berlin,
                       max_apparent_temperature_shade_at_berlin,
                       min_apparent_temperature_shade_at_berlin
                FROM analytical.de_current_gemeinde_summary WHERE ars = %s
                """,
                (ars,),
            ).fetchone()
            # lead-hour column of each Kreis/Land/Bund summary -> expected key
            columns = {
                f"{extreme}_{measure}_{weighting}_weighted_lead_hour": f"{extreme}_{measure}"
                for extreme in ("max", "min")
                for measure in ("temperature", "apparent_temperature_shade")
                for weighting in ("area", "population")
            }
            hours = {
                level: dict(zip(columns, connection.execute(
                    f"SELECT {', '.join(columns)} FROM analytical.de_current_{level}_summary"
                ).fetchone()))
                for level in ("kreis", "land", "bund")
            }

    assert gemeinde == tuple(berlin(expected[key]) for key in expected)
    for level, by_column in hours.items():
        for column, hour in by_column.items():
            assert hour == expected[columns[column]], (level, column)
