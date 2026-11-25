import dagster as dg

from src.database.connection import database_connection
from src.database.schema import apply_base_schema
from src.icon_grid_contract import (
    ICON_D2_GRID_CONTRACT,
)
from src.ingestion.icon_grid import (
    load_icon_grid_raw,
)


RAW_ICON_GRID_KEY = dg.AssetKey(
    ["raw", "icon_grid"]
)

NORMALIZED_ICON_CELL_KEY = dg.AssetKey(
    ["normalized", "icon_cell"]
)


@dg.asset(
    key=RAW_ICON_GRID_KEY,
    group_name="raw",
    description=(
        "Decoded DWD ICON D2 grid vertices and "
        "cell topology loaded into PostgreSQL."
    ),
)
def raw_icon_grid(
    context: dg.AssetExecutionContext,
) -> None:
    result = load_icon_grid_raw()

    context.add_output_metadata(
        {
            "source_grid_id": (
                result.source_grid_id
            ),
            "source_path": result.source_path,
            "source_sha256": (
                result.source_sha256
            ),
            "vertex_count": (
                result.vertex_count
            ),
            "cell_count": (
                result.cell_count
            ),
            "topology_row_count": (
                result.topology_row_count
            ),
            "vertex_load_seconds": (
                result.vertex_load_seconds
            ),
            "topology_load_seconds": (
                result.topology_load_seconds
            ),
        }
    )


@dg.asset(
    key=NORMALIZED_ICON_CELL_KEY,
    deps=[RAW_ICON_GRID_KEY],
    group_name="normalized",
    description=(
        "Every ICON grid cell as a triangle in EPSG:3035, "
        "constructed and validated by PostGIS."
    ),
)
def normalized_icon_cell(
    context: dg.AssetExecutionContext,
) -> None:
    with database_connection(
        application_name="datlas_icon_cell_normalize"
    ) as connection:
        apply_base_schema(connection)
        summary = connection.execute(
            """
            SELECT
                result.raw_vertex_count,
                result.raw_cell_count,
                result.normalized_cell_count,
                result.rejected_cell_count,
                result.rejection_reasons
            FROM normalized.refresh_icon_cell_geometry(
                %s::TEXT,
                %s::INTEGER,
                %s::INTEGER
            )
                AS result
            """,
            (
                ICON_D2_GRID_CONTRACT.source_grid_id,
                ICON_D2_GRID_CONTRACT.vertex_count,
                ICON_D2_GRID_CONTRACT.cell_count,
            ),
        ).fetchone()

        if summary is None:
            raise RuntimeError(
                "ICON cell SQL normalization "
                "returned no summary"
            )

    context.add_output_metadata(
        {
            "source_grid_id": ICON_D2_GRID_CONTRACT.source_grid_id,
            "raw_vertex_count": int(
                summary[0]
            ),
            "raw_cell_count": int(
                summary[1]
            ),
            "normalized_cell_count": int(
                summary[2]
            ),
            "rejected_cell_count": int(
                summary[3]
            ),
            "rejection_reasons": (
                summary[4]
            ),
            "target_srid": 3035,
        }
    )


SPATIAL_ASSETS = [
    raw_icon_grid,
    normalized_icon_cell,
]
