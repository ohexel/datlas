import dagster as dg

from src.database.connection import database_connection
from src.dagster_pipeline.assets.database_spatial import (
    NORMALIZED_ICON_CELL_KEY,
    RAW_ICON_GRID_KEY,
)
from src.icon_grid_contract import (
    ICON_D2_GRID_CONTRACT,
)


@dg.asset_check(
    asset=NORMALIZED_ICON_CELL_KEY,
    additional_deps=[RAW_ICON_GRID_KEY],
    name="icon_cell_geometry_quality",
)
def icon_cell_geometry_quality(
    context: dg.AssetCheckExecutionContext,
) -> dg.AssetCheckResult:
    with database_connection(
        application_name="datlas_icon_geometry_check"
    ) as connection:
        result = connection.execute(
            """
            SELECT
                quality.passed,
                quality.raw_vertex_count,
                quality.raw_cell_count,
                quality.topology_row_count,
                quality.normalized_cell_count,
                quality.rejected_cell_count,
                quality.invalid_normalized_geometry_count,
                quality.wrong_srid_count,
                quality.non_triangle_count,
                quality.rejection_reasons
            FROM normalized.check_icon_geometry_quality(
                %s::TEXT,
                %s::INTEGER,
                %s::INTEGER
            )
                AS quality
            """,
            (
                ICON_D2_GRID_CONTRACT.source_grid_id,
                ICON_D2_GRID_CONTRACT.vertex_count,
                ICON_D2_GRID_CONTRACT.cell_count,
            ),
        ).fetchone()

    if result is None:
        return dg.AssetCheckResult(
            passed=False,
            description=(
                "ICON geometry SQL quality function "
                "returned no result."
            ),
        )

    return dg.AssetCheckResult(
        passed=bool(result[0]),
        metadata={
            "source_grid_id": ICON_D2_GRID_CONTRACT.source_grid_id,
            "raw_vertex_count": int(
                result[1]
            ),
            "raw_cell_count": int(
                result[2]
            ),
            "topology_row_count": int(
                result[3]
            ),
            "normalized_cell_count": int(
                result[4]
            ),
            "rejected_cell_count": int(
                result[5]
            ),
            "invalid_geometry_count": int(
                result[6]
            ),
            "wrong_srid_count": int(
                result[7]
            ),
            "non_triangle_count": int(
                result[8]
            ),
            "rejection_reasons": result[9],
        },
        description=(
            "PostgreSQL validates ICON grid cardinality, "
            "three-vertex topology, geometry validity, "
            "quarantine state, and EPSG:3035."
        ),
    )


SPATIAL_CHECKS = [
    icon_cell_geometry_quality,
]
