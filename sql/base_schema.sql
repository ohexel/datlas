-- Base schema: schemas, PostGIS, the ICON-D2 grid and the apparent
-- temperature formula. Idempotent; applied before every other schema file
-- (src/database/schema.py).
--
-- Grid cells are built directly in EPSG:3035 (ETRS89-LAEA), the equal-area
-- projection used for all area weights. The earlier route through
-- EPSG:25833 gave the same cells to within a relative difference of
-- 5e-12 (docs/germany-layer-facts.md).

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS normalized;
CREATE SCHEMA IF NOT EXISTS analytical;

-- ---------------------------------------------------------------------------
-- Raw ICON grid: one source row, its vertices and the three vertices of
-- each cell, as decoded from the DWD grid file (src/ingestion/icon_grid.py).
-- Deleting the source row removes its vertices and topology.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.icon_grid_source (
    source_grid_id text PRIMARY KEY,
    source_path text NOT NULL,
    source_sha256 text NOT NULL,
    source_url text NOT NULL,
    vertex_count integer NOT NULL CHECK (vertex_count > 0),
    cell_count integer NOT NULL CHECK (cell_count > 0),
    loaded_at_utc timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.icon_grid_vertex (
    source_grid_id text NOT NULL
        REFERENCES raw.icon_grid_source (source_grid_id) ON DELETE CASCADE,
    vertex_index integer NOT NULL,
    longitude_deg double precision NOT NULL,
    latitude_deg double precision NOT NULL,
    loaded_at_utc timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (source_grid_id, vertex_index)
);

CREATE TABLE IF NOT EXISTS raw.icon_grid_cell_vertex (
    source_grid_id text NOT NULL,
    cell_index integer NOT NULL,
    vertex_order smallint NOT NULL,
    vertex_index integer NOT NULL,
    loaded_at_utc timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (source_grid_id, cell_index, vertex_order),
    FOREIGN KEY (source_grid_id, vertex_index)
        REFERENCES raw.icon_grid_vertex (source_grid_id, vertex_index)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS icon_grid_cell_vertex_vertex_idx
    ON raw.icon_grid_cell_vertex (source_grid_id, vertex_index);

-- ---------------------------------------------------------------------------
-- Normalized ICON cells: every cell of the grid as a triangle in EPSG:3035,
-- with its area. Cells that fail validation are listed in
-- icon_geometry_rejected instead.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS normalized.icon_cell (
    source_grid_id text NOT NULL,
    cell_index integer NOT NULL,
    geometry public.geometry(Polygon, 3035) NOT NULL
        CONSTRAINT icon_cell_geometry_valid CHECK (public.ST_IsValid(geometry)),
    icon_cell_area_m2 double precision NOT NULL CHECK (icon_cell_area_m2 > 0),
    PRIMARY KEY (source_grid_id, cell_index)
);

CREATE INDEX IF NOT EXISTS icon_cell_geometry_idx
    ON normalized.icon_cell USING gist (geometry);

CREATE TABLE IF NOT EXISTS normalized.icon_geometry_rejected (
    source_grid_id text NOT NULL
        REFERENCES raw.icon_grid_source (source_grid_id) ON DELETE CASCADE,
    cell_index integer NOT NULL,
    rejection_reason text NOT NULL,
    rejected_at_utc timestamp with time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (source_grid_id, cell_index)
);

-- ---------------------------------------------------------------------------
-- Functions
-- ---------------------------------------------------------------------------
-- Shade apparent temperature (°C) from air temperature (°C), relative
-- humidity (%) and 10 m wind speed (m/s):
-- T + 0.33 e - 0.70 v - 4.00, e = RH/100 * 6.105 * exp(17.27 T / (237.7 + T)).
CREATE OR REPLACE FUNCTION normalized.calculate_apparent_temperature_shade_c(p_temperature_c double precision, p_relative_humidity_percent double precision, p_wind_speed_10m_ms double precision) RETURNS double precision
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $$
    SELECT
        p_temperature_c
        + 0.33 * (
            (p_relative_humidity_percent / 100.0)
            * 6.105
            * EXP(
                17.27 * p_temperature_c
                / (237.7 + p_temperature_c)
            )
        )
        - 0.70 * p_wind_speed_10m_ms
        - 4.00;
$$;

CREATE OR REPLACE FUNCTION normalized.refresh_icon_cell_geometry(p_source_grid_id text, p_expected_vertex_count integer DEFAULT 272089, p_expected_cell_count integer DEFAULT 542040) RETURNS TABLE(raw_vertex_count bigint, raw_cell_count bigint, normalized_cell_count bigint, rejected_cell_count bigint, rejection_reasons jsonb)
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_vertex_count BIGINT;
    v_cell_count BIGINT;
    v_normalized_count BIGINT;
    v_rejected_count BIGINT;
    v_reasons JSONB;
BEGIN
    SELECT COUNT(*)
    INTO v_vertex_count
    FROM raw.icon_grid_vertex AS vertex
    WHERE vertex.source_grid_id = p_source_grid_id;

    SELECT COUNT(DISTINCT topology.cell_index)
    INTO v_cell_count
    FROM raw.icon_grid_cell_vertex AS topology
    WHERE topology.source_grid_id = p_source_grid_id;

    IF v_vertex_count = 0 OR v_cell_count = 0 THEN
        RAISE EXCEPTION
            'ICON grid % has no raw vertex/topology data',
            p_source_grid_id;
    END IF;

    DROP TABLE IF EXISTS pg_temp.icon_cell_candidates;

    CREATE TEMP TABLE icon_cell_candidates
    ON COMMIT DROP
    AS
    WITH grouped AS (
        SELECT
            topology.source_grid_id,
            topology.cell_index,
            COUNT(*) AS vertex_count,
            COUNT(DISTINCT topology.vertex_index)
                AS distinct_vertex_count,

            MAX(vertex.longitude_deg)
                FILTER (WHERE topology.vertex_order = 0) AS lon_0,
            MAX(vertex.latitude_deg)
                FILTER (WHERE topology.vertex_order = 0) AS lat_0,

            MAX(vertex.longitude_deg)
                FILTER (WHERE topology.vertex_order = 1) AS lon_1,
            MAX(vertex.latitude_deg)
                FILTER (WHERE topology.vertex_order = 1) AS lat_1,

            MAX(vertex.longitude_deg)
                FILTER (WHERE topology.vertex_order = 2) AS lon_2,
            MAX(vertex.latitude_deg)
                FILTER (WHERE topology.vertex_order = 2) AS lat_2
        FROM raw.icon_grid_cell_vertex AS topology
        JOIN raw.icon_grid_vertex AS vertex
          ON vertex.source_grid_id = topology.source_grid_id
         AND vertex.vertex_index = topology.vertex_index
        WHERE topology.source_grid_id = p_source_grid_id
        GROUP BY
            topology.source_grid_id,
            topology.cell_index
    ),
    preliminary AS (
        SELECT
            grouped.*,
            CASE
                WHEN grouped.vertex_count <> 3
                    THEN 'invalid_vertex_count'
                WHEN grouped.distinct_vertex_count <> 3
                    THEN 'repeated_vertex'
                WHEN grouped.lon_0 IS NULL
                  OR grouped.lat_0 IS NULL
                  OR grouped.lon_1 IS NULL
                  OR grouped.lat_1 IS NULL
                  OR grouped.lon_2 IS NULL
                  OR grouped.lat_2 IS NULL
                    THEN 'missing_vertex_coordinate'
                WHEN grouped.lon_0 NOT BETWEEN -180 AND 180
                  OR grouped.lon_1 NOT BETWEEN -180 AND 180
                  OR grouped.lon_2 NOT BETWEEN -180 AND 180
                  OR grouped.lat_0 NOT BETWEEN -90 AND 90
                  OR grouped.lat_1 NOT BETWEEN -90 AND 90
                  OR grouped.lat_2 NOT BETWEEN -90 AND 90
                    THEN 'invalid_vertex_coordinate'
                ELSE NULL
            END AS preliminary_rejection_reason
        FROM grouped
    ),
    geometry_built AS (
        SELECT
            preliminary.source_grid_id,
            preliminary.cell_index,
            CASE
                WHEN preliminary.preliminary_rejection_reason IS NULL
                THEN ST_Transform(
                    ST_SetSRID(
                        ST_MakePolygon(
                            ST_MakeLine(
                                ARRAY[
                                    ST_MakePoint(
                                        preliminary.lon_0,
                                        preliminary.lat_0
                                    ),
                                    ST_MakePoint(
                                        preliminary.lon_1,
                                        preliminary.lat_1
                                    ),
                                    ST_MakePoint(
                                        preliminary.lon_2,
                                        preliminary.lat_2
                                    ),
                                    ST_MakePoint(
                                        preliminary.lon_0,
                                        preliminary.lat_0
                                    )
                                ]
                            )
                        ),
                        4326
                    ),
                    3035
                )::geometry(Polygon, 3035)
                ELSE NULL
            END AS geometry,
            preliminary.preliminary_rejection_reason
        FROM preliminary
    )
    SELECT
        geometry_built.source_grid_id,
        geometry_built.cell_index,
        geometry_built.geometry,
        CASE
            WHEN geometry_built.preliminary_rejection_reason IS NOT NULL
                THEN geometry_built.preliminary_rejection_reason
            WHEN geometry_built.geometry IS NULL
                THEN 'geometry_construction_failed'
            WHEN ST_IsEmpty(geometry_built.geometry)
                THEN 'empty_geometry'
            WHEN NOT ST_IsValid(geometry_built.geometry)
                THEN 'invalid_geometry'
            WHEN ST_Area(geometry_built.geometry) <= 0
                THEN 'non_positive_area'
            WHEN ST_NPoints(
                ST_ExteriorRing(geometry_built.geometry)
            ) <> 4
                THEN 'not_triangular'
            ELSE NULL
        END AS rejection_reason
    FROM geometry_built;

    DELETE FROM normalized.icon_geometry_rejected AS rejected
    WHERE rejected.source_grid_id = p_source_grid_id;

    INSERT INTO normalized.icon_geometry_rejected (
        source_grid_id,
        cell_index,
        rejection_reason
    )
    SELECT
        candidate.source_grid_id,
        candidate.cell_index,
        candidate.rejection_reason
    FROM icon_cell_candidates AS candidate
    WHERE candidate.rejection_reason IS NOT NULL;

    GET DIAGNOSTICS v_rejected_count = ROW_COUNT;

    INSERT INTO normalized.icon_cell (
        source_grid_id,
        cell_index,
        geometry,
        icon_cell_area_m2
    )
    SELECT
        candidate.source_grid_id,
        candidate.cell_index,
        candidate.geometry,
        ST_Area(candidate.geometry)
    FROM icon_cell_candidates AS candidate
    WHERE candidate.rejection_reason IS NULL
    ON CONFLICT (
        source_grid_id,
        cell_index
    )
    DO UPDATE SET
        geometry = EXCLUDED.geometry,
        icon_cell_area_m2 = EXCLUDED.icon_cell_area_m2;

    SELECT COUNT(*)
    INTO v_normalized_count
    FROM normalized.icon_cell AS normalized_cell
    WHERE normalized_cell.source_grid_id = p_source_grid_id;

    SELECT COALESCE(
        JSONB_OBJECT_AGG(
            reason_counts.rejection_reason,
            reason_counts.reason_count
        ),
        '{}'::JSONB
    )
    INTO v_reasons
    FROM (
        SELECT
            rejected.rejection_reason,
            COUNT(*) AS reason_count
        FROM normalized.icon_geometry_rejected AS rejected
        WHERE rejected.source_grid_id = p_source_grid_id
        GROUP BY rejected.rejection_reason
    ) AS reason_counts;

    RETURN QUERY
    SELECT
        v_vertex_count,
        v_cell_count,
        v_normalized_count,
        v_rejected_count,
        v_reasons;
END
$$;

CREATE OR REPLACE FUNCTION normalized.check_icon_geometry_quality(p_source_grid_id text, p_expected_vertex_count integer DEFAULT 272089, p_expected_cell_count integer DEFAULT 542040) RETURNS TABLE(passed boolean, raw_vertex_count bigint, raw_cell_count bigint, topology_row_count bigint, normalized_cell_count bigint, rejected_cell_count bigint, invalid_normalized_geometry_count bigint, wrong_srid_count bigint, non_triangle_count bigint, rejection_reasons jsonb)
    LANGUAGE sql STABLE
    AS $$
WITH raw_summary AS (
    SELECT
        (
            SELECT COUNT(*)
            FROM raw.icon_grid_vertex AS vertex
            WHERE vertex.source_grid_id = p_source_grid_id
        ) AS raw_vertex_count,
        (
            SELECT COUNT(DISTINCT topology.cell_index)
            FROM raw.icon_grid_cell_vertex AS topology
            WHERE topology.source_grid_id = p_source_grid_id
        ) AS raw_cell_count,
        (
            SELECT COUNT(*)
            FROM raw.icon_grid_cell_vertex AS topology
            WHERE topology.source_grid_id = p_source_grid_id
        ) AS topology_row_count
),
normalized_summary AS (
    SELECT
        COUNT(*) AS normalized_cell_count,
        COUNT(*) FILTER (
            WHERE NOT ST_IsValid(cell.geometry)
               OR ST_IsEmpty(cell.geometry)
               OR ST_Area(cell.geometry) <= 0
        ) AS invalid_normalized_geometry_count,
        COUNT(*) FILTER (
            WHERE ST_SRID(cell.geometry) <> 3035
        ) AS wrong_srid_count,
        COUNT(*) FILTER (
            WHERE ST_NPoints(ST_ExteriorRing(cell.geometry)) <> 4
        ) AS non_triangle_count
    FROM normalized.icon_cell AS cell
    WHERE cell.source_grid_id = p_source_grid_id
),
rejected_summary AS (
    SELECT COUNT(*) AS rejected_cell_count
    FROM normalized.icon_geometry_rejected AS rejected
    WHERE rejected.source_grid_id = p_source_grid_id
),
reason_summary AS (
    SELECT COALESCE(
        JSONB_OBJECT_AGG(
            reason_counts.rejection_reason,
            reason_counts.reason_count
        ),
        '{}'::JSONB
    ) AS rejection_reasons
    FROM (
        SELECT
            rejected.rejection_reason,
            COUNT(*) AS reason_count
        FROM normalized.icon_geometry_rejected AS rejected
        WHERE rejected.source_grid_id = p_source_grid_id
        GROUP BY rejected.rejection_reason
    ) AS reason_counts
)
SELECT
    (
        raw_summary.raw_vertex_count = p_expected_vertex_count
        AND raw_summary.raw_cell_count = p_expected_cell_count
        AND raw_summary.topology_row_count
            = p_expected_cell_count * 3
        AND normalized_summary.normalized_cell_count
            = p_expected_cell_count
        AND rejected_summary.rejected_cell_count = 0
        AND normalized_summary.invalid_normalized_geometry_count = 0
        AND normalized_summary.wrong_srid_count = 0
        AND normalized_summary.non_triangle_count = 0
    ) AS passed,
    raw_summary.raw_vertex_count,
    raw_summary.raw_cell_count,
    raw_summary.topology_row_count,
    normalized_summary.normalized_cell_count,
    rejected_summary.rejected_cell_count,
    normalized_summary.invalid_normalized_geometry_count,
    normalized_summary.wrong_srid_count,
    normalized_summary.non_triangle_count,
    reason_summary.rejection_reasons
FROM raw_summary
CROSS JOIN normalized_summary
CROSS JOIN rejected_summary
CROSS JOIN reason_summary
$$;
