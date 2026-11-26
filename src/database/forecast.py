"""Forecast aggregation for one (run_time, lead_time) partition.

The four raw indicators of all bridge cells are staged in a temporary table.
PostgreSQL converts units, computes shade apparent temperature with
normalized.calculate_apparent_temperature_shade_c, stores the cell
values and area-weights them to Gemeinden
(normalized.refresh_forecast_partition). Why SQL and not numpy: ADR 018.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from psycopg import Connection

from src.database.connection import database_connection
from src.database.load import copy_rows
from src.forecast_key import ForecastKey, ProjectPaths
from src.ingestion.contract import GEOGRAPHY_VERSION
from src.database.normalize import apply_normalized_schema
from src.icon_grid_contract import ICON_D2_GRID_CONTRACT
from src.ingestion.icon_d2_ruc_field import prepare_field


FORECAST_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "sql" / "forecast_schema.sql"
)
SOURCE_GRID_ID = ICON_D2_GRID_CONTRACT.source_grid_id
INDICATOR_COLUMNS = {
    "T_2M": "temperature_k",
    "RELHUM_2M": "relative_humidity_percent",
    "U_10M": "wind_u_10m_ms",
    "V_10M": "wind_v_10m_ms",
}


def apply_forecast_schema(connection: Connection) -> None:
    apply_normalized_schema(connection)
    connection.execute(FORECAST_SCHEMA_PATH.read_text(encoding="utf-8"))


def load_cell_indices(
    connection: Connection,
    geography_version: str = GEOGRAPHY_VERSION,
) -> np.ndarray:
    """Cell indices in the cell-Gemeinde bridge, ascending."""
    cells = np.array(
        [
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT cell_index
                FROM normalized.icon_cell_gemeinde_bridge
                WHERE geography_version = %s AND source_grid_id = %s
                ORDER BY cell_index
                """,
                (geography_version, SOURCE_GRID_ID),
            )
        ],
        dtype=np.int64,
    )
    if cells.size == 0:
        raise RuntimeError(
            "Cell-Gemeinde bridge is empty; materialize "
            "normalized/icon_gemeinde_bridge first"
        )
    return cells


def partition_complete(
    forecast: ForecastKey,
    geography_version: str = GEOGRAPHY_VERSION,
) -> bool:
    """True when every Gemeinde has both values for this run and lead time."""
    with database_connection(application_name="datlas_partition_state") as connection:
        row = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM normalized.gemeinde_forecast
                 WHERE run_time_utc = %s AND lead_time = %s
                   AND geography_version = %s
                   AND temperature_c IS NOT NULL
                   AND apparent_temperature_shade_c IS NOT NULL),
                (SELECT COUNT(*) FROM normalized.gemeinde
                 WHERE geography_version = %s)
            """,
            (forecast.run_time, forecast.lead_time_label, geography_version, geography_version),
        ).fetchone()
    return row is not None and row[1] > 0 and row[0] == row[1]


def newest_complete_run(
    connection: Connection,
    geography_version: str = GEOGRAPHY_VERSION,
) -> datetime | None:
    """The newest run with all 25 lead times for every Gemeinde, if any."""
    row = connection.execute(
        """
        SELECT run_time_utc FROM normalized.forecast_run_completeness
        WHERE geography_version = %s AND is_complete
        ORDER BY run_time_utc DESC
        LIMIT 1
        """,
        (geography_version,),
    ).fetchone()
    return None if row is None else row[0]


@dataclass
class PartitionResult:
    run_time_utc: str
    lead_time: str
    cell_row_count: int = 0
    gemeinde_row_count: int = 0
    timings: dict[str, float] = field(default_factory=dict)


def _decode_fields(
    forecast: ForecastKey,
    paths: ProjectPaths,
    cell_indices: np.ndarray,
) -> dict[str, np.ndarray]:
    values: dict[str, np.ndarray] = {}
    for indicator in INDICATOR_COLUMNS:
        prepared = prepare_field(paths=paths, forecast=forecast, indicator=indicator)
        values[indicator] = prepared.values[cell_indices]
        del prepared
    return values


def _none_if_nan(value: float) -> float | None:
    return None if np.isnan(value) else float(value)


def process_partition(
    forecast: ForecastKey,
    *,
    paths: ProjectPaths | None = None,
    geography_version: str = GEOGRAPHY_VERSION,
) -> PartitionResult:
    project_paths = paths if paths is not None else ProjectPaths()
    result = PartitionResult(
        run_time_utc=forecast.run_time.isoformat(),
        lead_time=forecast.lead_time_label,
    )
    timings = result.timings

    with database_connection(application_name="datlas_forecast") as connection:
        apply_forecast_schema(connection)
        # Commit the DDL at once: CREATE OR REPLACE VIEW locks the served views,
        # and the data transaction below runs for several seconds.
        connection.commit()

        started = perf_counter()
        cells = load_cell_indices(connection, geography_version)
        timings["load_cells"] = perf_counter() - started

        started = perf_counter()
        fields = _decode_fields(forecast, project_paths, cells)
        timings["decode_grib"] = perf_counter() - started

        started = perf_counter()
        connection.execute(
            """
            CREATE TEMP TABLE cell_stage (
                cell_index integer PRIMARY KEY,
                temperature_k double precision,
                relative_humidity_percent double precision,
                wind_u_10m_ms double precision,
                wind_v_10m_ms double precision
            ) ON COMMIT DROP
            """
        )
        copy_rows(
            connection,
            schema="pg_temp",
            table="cell_stage",
            columns=("cell_index", *INDICATOR_COLUMNS.values()),
            rows=(
                (
                    int(cell),
                    *(_none_if_nan(fields[name][position]) for name in INDICATOR_COLUMNS),
                )
                for position, cell in enumerate(cells)
            ),
        )
        timings["stage_copy"] = perf_counter() - started

        started = perf_counter()
        counts = connection.execute(
            "SELECT * FROM normalized.refresh_forecast_partition(%s, %s, %s, %s, %s)",
            (
                forecast.run_time,
                forecast.lead_time_label,
                forecast.valid_time,
                geography_version,
                SOURCE_GRID_ID,
            ),
        ).fetchone()
        timings["compute_and_store"] = perf_counter() - started
        result.cell_row_count, result.gemeinde_row_count = int(counts[0]), int(counts[1])

    return result
