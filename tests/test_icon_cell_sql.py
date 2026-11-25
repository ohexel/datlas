"""PostGIS builds ICON cells directly in EPSG:3035 and validates them."""

import pytest

from src.database.connection import database_connection
from src.database.load import copy_rows
from src.database.schema import apply_base_schema


VERTICES = [(0, 13.40, 52.50), (1, 13.41, 52.50), (2, 13.405, 52.51)]


def test_postgis_builds_icon_cells_in_epsg_3035() -> None:
    grid_id = "icon_cell_fixture"

    with database_connection(application_name="datlas_icon_cell_test") as connection:
        with connection.transaction(force_rollback=True):
            apply_base_schema(connection)
            connection.execute(
                """
                INSERT INTO raw.icon_grid_source (
                    source_grid_id, source_path, source_sha256, source_url,
                    vertex_count, cell_count
                )
                VALUES (%s, 'fixture.nc', 'fixture_grid_hash', 'fixture', 3, 1)
                """,
                (grid_id,),
            )
            copy_rows(
                connection,
                schema="raw",
                table="icon_grid_vertex",
                columns=("source_grid_id", "vertex_index", "longitude_deg", "latitude_deg"),
                rows=[(grid_id, *vertex) for vertex in VERTICES],
            )
            copy_rows(
                connection,
                schema="raw",
                table="icon_grid_cell_vertex",
                columns=("source_grid_id", "cell_index", "vertex_order", "vertex_index"),
                rows=[(grid_id, 0, order, order) for order in range(3)],
            )

            summary = connection.execute(
                """
                SELECT raw_vertex_count, raw_cell_count,
                       normalized_cell_count, rejected_cell_count
                FROM normalized.refresh_icon_cell_geometry(%s, 3, 1)
                """,
                (grid_id,),
            ).fetchone()
            assert summary == (3, 1, 1, 0)

            srid, geometry_type, valid, points, area, expected_area = connection.execute(
                """
                SELECT
                    ST_SRID(cell.geometry),
                    GeometryType(cell.geometry),
                    ST_IsValid(cell.geometry),
                    ST_NPoints(ST_ExteriorRing(cell.geometry)),
                    cell.icon_cell_area_m2,
                    ST_Area(ST_Transform(
                        ST_GeomFromText(
                            'POLYGON((13.40 52.50,13.41 52.50,13.405 52.51,13.40 52.50))',
                            4326
                        ),
                        3035
                    ))
                FROM normalized.icon_cell AS cell
                WHERE cell.source_grid_id = %s AND cell.cell_index = 0
                """,
                (grid_id,),
            ).fetchone()

            assert srid == 3035
            assert geometry_type == "POLYGON"
            assert valid is True
            assert points == 4
            # The triangle of the three vertices projected to EPSG:3035.
            assert area == pytest.approx(expected_area, rel=1e-12)

            passed = connection.execute(
                "SELECT passed FROM normalized.check_icon_geometry_quality(%s, 3, 1)",
                (grid_id,),
            ).fetchone()[0]
            assert passed is True


@pytest.mark.parametrize(
    "lon, lat",
    [(6.0, 51.0), (10.0, 51.0), (15.0, 51.0), (7.5, 47.6), (9.5, 54.8)],
)
def test_direct_3035_cells_equal_the_former_route_through_25833(lon: float, lat: float) -> None:
    """Only vertices are projected, so building a cell through EPSG:25833
    (the capstone's route) or directly gives the same triangle up to
    rounding, also far west of UTM zone 33 (split-plan D4)."""
    with database_connection(application_name="datlas_icon_cell_test") as connection:
        area_direct, area_via, distance = connection.execute(
            """
            WITH cell AS (
                SELECT ST_SetSRID(ST_MakePolygon(ST_MakeLine(ARRAY[
                    ST_MakePoint(%(lon)s, %(lat)s),
                    ST_MakePoint(%(lon)s + 0.02, %(lat)s),
                    ST_MakePoint(%(lon)s + 0.01, %(lat)s + 0.015),
                    ST_MakePoint(%(lon)s, %(lat)s)
                ])), 4326) AS geometry
            ), built AS (
                SELECT ST_Transform(geometry, 3035) AS direct,
                       ST_Transform(ST_Transform(geometry, 25833), 3035) AS via
                FROM cell
            )
            SELECT ST_Area(direct), ST_Area(via), ST_HausdorffDistance(direct, via)
            FROM built
            """,
            {"lon": lon, "lat": lat},
        ).fetchone()

    assert area_via == pytest.approx(area_direct, rel=1e-9)
    assert distance < 1e-6  # metres
