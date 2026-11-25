# ADR 021: Separation from the capstone

Status: Accepted (25 Nov 2026). Supersedes ADR 008 and ADR 013.

## Context

The Germany map started as a layer on top of the Berlin capstone (*24h
temperature forecast for Berlin neighborhoods*, repository `ohexel/lwr`,
releases v2.0–v2.2). It ran in the capstone's database and Dagster project
and depended on capstone objects: the base schema and ICON grid from the
capstone bootstrap, Berlin's ICON cells in EPSG:25833, the apparent
temperature function, and the capstone's forecast download. To keep Berlin
untouched, every Germany object carried the prefix `de_`, the code lived in
`src.germany`, and one check compared Berlin with its 542 planning areas.

The capstone release v1.0 had to stay what it was when it was submitted, while
the Germany work had outgrown being a layer: it needs its own installation, a
forecast that runs without anyone starting it, and room to grow.

## Decision

1. **Own repository.** The Germany work moved to `ohexel/datlas` with its full
   history, including the tags v2.0–v2.2. The capstone repository went back to
   v1.0; capstone-applicable improvements are on a branch there.
2. **No capstone code or limits.** The Berlin modules, tests, SQL, data files
   and dashboard are removed. The capstone's 5,785-line schema dump is replaced
   by `sql/base_schema.sql`, which holds only what datlas uses (schemas,
   PostGIS, the raw ICON grid tables, the cell table, the cell build, the grid
   check and the apparent temperature formula) and is applied before every
   other schema file, so a run builds an empty database by itself.
3. **Plain names (split decision D2).** The `de_` prefix is dropped from all
   database objects, asset keys and checks; `src.germany` is distributed over
   the existing packages (`ingestion`, `database`, `src`). Jobs and asset groups
   are named after their theme: `static`, `forecast`, `employment`,
   `sectors`.
4. **No Berlin comparison (D3).** Check 7 compared Berlin with its planning
   areas; without the planning areas it is removed. An independent
   replacement can follow.
5. **Cells built directly in EPSG:3035 (D4).** One `normalized.icon_cell`
   holds every ICON cell in the equal-area projection of ADR 014. Only the
   vertices are projected, so the former route through EPSG:25833 gave the same
   triangles up to rounding (relative difference of cell area at most
   4.85 × 10⁻¹²). The separate Germany copy of the cells is gone; the cells of a
   forecast are the cells of the cell-Gemeinde bridge.
6. **GRIB retention by run (D5).** A retained GRIB file is deleted only when
   its run is older than the rolling window (at most 24 hours) and no longer in
   the database, which keeps the newest two complete runs (ADR 018). Applied by
   the publish step.
7. **A forecast that runs by itself (P2-D2).** A DWD availability sensor,
   ported from the capstone with its corrections, starts forecast partitions;
   a publish sensor publishes each complete run once; the map export is an
   asset of the publish job. Both sensors start stopped.
8. **Publishing stays outside (P2-D3).** The pipeline writes the map's files
   to `web/germany-dashboard/`; copying them to the web host is done by the
   host, not by the pipeline.
9. **Own Docker names.** Compose project `datlas`, container `datlas_postgres`
   on port 5433, Dagster UI on port 3001, so datlas and the capstone can run on
   the same machine without acting on each other's containers.

## Consequences

- A fresh installation needs no capstone, no HOSTRADA archive and no Berlin
  sources. It was compared with the last capstone-based installation for the
  same forecast run and data vintages (25 Nov 2026): all row counts equal; cell
  values identical; Gemeinde values within 6.3 × 10⁻¹² °C; employment and
  sector values identical; the three map files identical apart from one key
  removed on purpose earlier.
- ADR 008 (one canonical bootstrap schema) is replaced by decision 2. ADR 013
  (Berlin-only forecast storage, 24-hour retention of rows and files) is
  replaced by ADR 018 for rows and decision 6 for files.
- The capstone ADRs that concern only Berlin (planning areas, the HOSTRADA
  reference, the Berlin calendar, the median summary, the Berlin dashboard)
  were removed from this repository; they remain in `ohexel/lwr`. ADRs 001,
  003, 004 and 007 still hold; their examples refer to Berlin.
- Differences in the code base between datlas and the capstone will grow.
  Deduplicating shared code (forecast download, GRIB decoding, partitions) is
  left for later.
