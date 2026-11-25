"""Germany layer, M2/M4: normalized hierarchy, population and checks 1-3."""

import pytest


# ---------------------------------------------------------------------------
# Integration: synthetic sources inside a rolled-back transaction.
# ---------------------------------------------------------------------------
FIXTURE_VG250 = "fixture_de_vg250_m2"
FIXTURE_ZENSUS = "fixture_de_zensus_m2"
FIXTURE_VERSION = "fixture-m2"


def _square(x0: float, y0: float, size: float = 1000.0) -> str:
    x1, y1 = x0 + size, y0 + size
    return (
        f"SRID=25832;MULTIPOLYGON((({x0} {y0},{x1} {y0},{x1} {y1},"
        f"{x0} {y1},{x0} {y0})))"
    )


VG250_COLUMNS = (
    "level", "gf", "ars", "ags", "gen", "bez", "sn_l", "sn_r", "sn_k",
    "geometry_source", "vintage", "source_layer", "source_path",
    "source_sha256", "source_url", "publisher", "license",
)


def _vg250(level, ars, name, bez, geometry, ags=None, sha=FIXTURE_VG250):
    return (
        level, 4, ars, ags, name, bez, ars[:2], ars[2:3] or None,
        ars[3:5] or None, geometry, "2022-12-31", f"vg250_{level}",
        "fixture.gpkg", sha, "fixture", "fixture", "fixture",
    )


def _zensus(variable, key, value, label="x"):
    return (
        "1000A-1003", variable, "1000A", "fixture", "STAG", "Stichtag",
        "2022-05-15", variable, "fixture", key, label, None, None, None,
        None, value, "Anzahl", "PRS", "Personen", "fixture.csv",
        FIXTURE_ZENSUS, "fixture", "fixture", "fixture",
    )


@pytest.mark.integration
def test_refresh_and_checks_classify_every_case() -> None:
    from src.database.connection import database_connection
    from src.database.load import copy_rows
    from src.database.normalize import apply_normalized_schema

    x, y = 500_000.0, 5_800_000.0
    vg250_rows = [
        _vg250("lan", "99", "Fixland", "Land", _square(x, y, 10_000)),
        _vg250("krs", "99001", "Fixkreis", "Kreis", _square(x, y, 4000)),
        _vg250("krs", "99002", "Leerkreis", "Kreis", _square(x + 5000, y)),
        # census value / '-' / unincorporated without record /
        # populated without record / rejected value
        _vg250("gem", "990010000001", "Eins", "Gemeinde", _square(x, y), "99001001"),
        _vg250("gem", "990010000002", "Zwei", "Gemeinde", _square(x + 1000, y), "99001002"),
        _vg250("gem", "990019501501", "Forst", "Gemeindefreies Gebiet", _square(x + 2000, y), "99001501"),
        _vg250("gem", "990010000004", "Vier", "Gemeinde", _square(x + 3000, y), "99001004"),
        _vg250("gem", "990010000006", "Sechs", "Gemeinde", _square(x, y + 1000), "99001006"),
    ]
    zensus_rows = [
        _zensus("GEODL1", "DG", "999"),
        _zensus("GEOBL1", "99", "500"),
        _zensus("GEOLK4", "99001", "500"),
        _zensus("GEOLK4", "99002", "0"),
        _zensus("GEOGM4", "990010000001", "100"),
        _zensus("GEOGM4", "990010000002", "-"),
        _zensus("GEOGM4", "990010000006", "x"),
        _zensus("GEOGM4", "990010000099", "7", "Phantom"),
    ]

    with database_connection(application_name="lwr_germany_m2_test") as connection:
        with connection.transaction(force_rollback=True):
            apply_normalized_schema(connection)
            copy_rows(
                connection, schema="raw", table="de_vg250", columns=VG250_COLUMNS, rows=vg250_rows
            )
            copy_rows(
                connection, schema="raw", table="de_zensus2022_population",
                columns=(
                    "table_code", "requested_regional_variable",
                    "statistics_code", "statistics_label", "time_code",
                    "time_label", "time_value", "variable_1_code",
                    "variable_1_label", "variable_1_attribute_code",
                    "variable_1_attribute_label", "variable_2_code",
                    "variable_2_label", "variable_2_attribute_code",
                    "variable_2_attribute_label", "value", "value_unit",
                    "value_variable_code", "value_variable_label",
                    "source_path", "source_sha256", "source_url", "publisher",
                    "license",
                ),
                rows=zensus_rows,
            )

            hierarchy = connection.execute(
                "SELECT * FROM normalized.refresh_de_hierarchy(%s, %s)",
                (FIXTURE_VG250, FIXTURE_VERSION),
            ).fetchone()
            assert hierarchy == (1, 2, 5, 1)

            connection.execute(
                "SELECT * FROM normalized.refresh_de_population(%s, %s, %s)",
                (FIXTURE_VERSION, [FIXTURE_ZENSUS], "2022-05-15"),
            ).fetchone()

            population = dict(
                (ars, (total, status))
                for ars, total, status in connection.execute(
                    """
                    SELECT ars, population_total, population_status
                    FROM normalized.de_gemeinde_population
                    WHERE geography_version = %s
                    """,
                    (FIXTURE_VERSION,),
                )
            )
            assert population == {
                "990010000001": (100, "census_value"),
                "990010000002": (0, "census_zero_or_set_to_zero"),
                "990019501501": (None, "no_census_record_unincorporated"),
                "990010000004": (None, "no_census_record"),
                "990010000006": (None, "rejected_source_value"),
            }

            coverage = {
                (issue, key, blocking)
                for _, issue, key, _, blocking in connection.execute(
                    "SELECT * FROM normalized.check_de_key_coverage(%s, %s)",
                    (FIXTURE_VERSION, [FIXTURE_ZENSUS]),
                )
            }
            assert coverage == {
                ("unincorporated_area_without_census_record", "990019501501", False),
                ("geometry_without_census_record", "990010000004", True),
                ("census_record_without_geometry", "990010000099", True),
                ("rejected_census_value", "990010000006", True),
            }

            hierarchy_issues = set(
                connection.execute(
                    "SELECT issue, region_key FROM normalized.check_de_hierarchy(%s)",
                    (FIXTURE_VERSION,),
                ).fetchall()
            )
            assert hierarchy_issues == {("kreis_without_gemeinde", "99002")}

            # Check 3: Σ Gemeinden (100 + 0; NULL populations are skipped,
            # never counted as 0) vs. the published Kreis/Land/Bund totals.
            totals = {
                (level, key): (gemeinde_sum, published, difference)
                for level, key, _, gemeinde_sum, published, difference in connection.execute(
                    "SELECT * FROM normalized.check_de_source_totals(%s, %s)",
                    (FIXTURE_VERSION, [FIXTURE_ZENSUS]),
                )
            }
            assert totals == {
                ("krs", "99001"): (100, 500, 400),
                ("krs", "99002"): (None, 0, None),  # no Gemeinde with a value
                ("lan", "99"): (100, 500, 400),
                ("sta", "DG"): (100, 999, 899),
            }


@pytest.mark.integration
def test_static_hierarchy_is_safe_to_repeat() -> None:
    """Decision Q1 (14 Nov 2026): run_static may run again. Forecasts and the
    bridge reference the Gemeinden, so an existing geography version is never
    rebuilt in place: the same VG250 file leaves it unchanged, another file
    under the same version is refused."""
    import psycopg

    from src.database.connection import database_connection
    from src.database.load import copy_rows
    from src.database.forecast import apply_forecast_schema

    version = "fixture-repeat"
    x, y = 500_000.0, 5_800_000.0

    def rows(sha: str, name: str) -> list[tuple]:
        return [
            _vg250("lan", "99", "Fixland", "Land", _square(x, y, 10_000), sha=sha),
            _vg250("krs", "99001", "Fixkreis", "Kreis", _square(x, y, 4000), sha=sha),
            _vg250("gem", "990010000001", name, "Gemeinde", _square(x, y), "99001001", sha=sha),
            _vg250("gem", "990010000002", "Zwei", "Gemeinde", _square(x + 1000, y), "99001002", sha=sha),
        ]

    def refresh(sha: str) -> tuple:
        return connection.execute(
            "SELECT * FROM normalized.refresh_de_hierarchy(%s, %s)", (sha, version)
        ).fetchone()

    def gemeinden() -> list[tuple]:
        return connection.execute(
            "SELECT ars, gemeinde_name, source_sha256 FROM normalized.de_gemeinde "
            "WHERE geography_version = %s ORDER BY ars",
            (version,),
        ).fetchall()

    with database_connection(application_name="lwr_germany_repeat_test") as connection:
        with connection.transaction(force_rollback=True):
            apply_forecast_schema(connection)
            copy_rows(connection, schema="raw", table="de_vg250", columns=VG250_COLUMNS,
                      rows=rows("fixture_vg250_a", "Eins"))
            first = refresh("fixture_vg250_a")
            built = gemeinden()
            # A forecast row now references a Gemeinde, as after a forecast run.
            connection.execute(
                "INSERT INTO normalized.de_gemeinde_forecast VALUES "
                "('2099-01-01T00:00Z','PT000H00M','2099-01-01T00:00Z',%s,'fixture_grid',"
                "'990010000001',1.0,1.0)",
                (version,),
            )

            # Same file again: no error, nothing rebuilt, the forecast survives.
            assert refresh("fixture_vg250_a") == first == (1, 1, 2, 0)
            assert gemeinden() == built
            assert connection.execute(
                "SELECT COUNT(*) FROM normalized.de_gemeinde_forecast WHERE geography_version = %s",
                (version,),
            ).fetchone()[0] == 1

            # Another file under the same version: refused, hierarchy unchanged.
            copy_rows(connection, schema="raw", table="de_vg250", columns=VG250_COLUMNS,
                      rows=rows("fixture_vg250_b", "Eins (umbenannt)"))
            with pytest.raises(psycopg.errors.RaiseException, match="another VG250 file"):
                with connection.transaction():
                    refresh("fixture_vg250_b")
            assert gemeinden() == built
