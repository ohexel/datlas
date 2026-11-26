# v3.0: Standalone

## Summary

v3.0 is the first release of datlas on its own. Up to v2.2 the three themes
(temperature, employment, sectors) were a "Germany layer" of the Berlin
capstone: they ran in its database and Dagster project, reused its ICON grid,
cells and forecast download, and kept their objects apart with a `de_` prefix.
v3.0 needs no capstone, runs the forecast without anyone starting it, and uses
plain names. The data and the map are the same: a fresh installation reproduces
the last capstone-based one for the same forecast run and data vintages
(ADR 021).

## What is new

- **Own repository and installation.** `ohexel/datlas` with the full history
  and the tags v2.0–v2.2. The Berlin code, tests, SQL, data files and dashboard
  are gone. `sql/base_schema.sql` replaces the capstone's 5,785-line schema
  dump with what datlas uses; every job applies it first, so `run_static`
  builds everything from an empty database, including the download of the DWD
  ICON grid file.
- **Own Docker names.** Compose project `datlas`, container `datlas_postgres`
  on port 5433, Dagster UI on port 3001, so datlas and the capstone can run on
  one machine without acting on each other's containers. The Dagster image
  installs `tippecanoe` for the tile build.
- **Plain names.** No `de_` prefix on database objects, asset keys and checks;
  the code of `src.germany` is in the existing packages (`src/ingestion`,
  `src/database`, `src`); jobs and asset groups are named after their theme
  (`static`, `forecast`, `forecast_publish`, `employment`, `sectors`).
- **Cells in EPSG:3035.** One `normalized.icon_cell` holds every ICON cell,
  built directly in the equal-area projection instead of being transformed
  from Berlin's cells in EPSG:25833; the forecast takes its cells from the
  bridge.
- **Unattended forecast.** `dwd_forecast_availability_sensor` starts forecast
  partitions as soon as DWD has published their four fields (newest first, at
  most ten per check, five attempts each); `forecast_publish_sensor` publishes
  each complete run once; the map export is an asset of the publish job. Both
  sensors start stopped.
- **GRIB retention by run.** A GRIB file is deleted only when its run is older
  than 24 hours and no longer in the database; the publish job applies it
  (`python -m src.retention.grib_files` reports or applies it by hand).
- **Run limits.** Two runs at a time, 300 s per run; the static, employment and
  sector jobs get 30 minutes.

## Removed

- Check 7 (Berlin against its 542 planning areas): nothing to compare against
  without the capstone. An independent replacement can follow.
- The Berlin-only ADRs (planning areas, HOSTRADA reference, Berlin calendar,
  median summary, Berlin dashboard) and documents (historical rebuild, Berlin
  dashboard, archive distribution); they remain in `ohexel/lwr`.
- 26 test cases that compared constants with themselves, tested a helper in
  more depth than it deserves, or duplicated another test. One test was added
  for `run_static --help`, which used to start the job; 98 remain.

## Verified (25 Nov 2026)

- Fresh installation into an empty database, only through the runners:
  `run_static` 4 min (with the grid download 5 min), `run_employment` 11 s,
  `run_sectors` 70 s with the files on disk; all 17 checks pass.
- Compared with the last capstone-based installation for the forecast run
  2026-11-14 09:00 UTC, BA reference date 30 June 2025 and file date
  31 March 2026: all 20 tables have the same row counts; cell values
  identical; Gemeinde values within 6.3 × 10⁻¹² °C; areas, population and
  197,385 indicator values identical; seven SQL checks give identical output;
  `employment.json` and `sectors.json` identical; `values.json` identical except
  one key removed on purpose on 15 Nov; boundary tiles with identical tile data.
- A live run (2026-11-25 15:00 UTC): 25 lead hours in 2 min 24 s, publish with
  map export 44 s; both forecast checks pass. One live check of each sensor
  proposed the right partitions and the right run to publish.
- The publish job deleted the GRIB files of five old runs (414 MB) and kept
  those of the current run.
- Tests: 81 default, 8 database, 9 acceptance; all pass.

## Upgrading from v2.2

There is no in-place upgrade: install datlas into a new database
([runbook](runbook.md#install)) and run the first build. Files under
`data/raw/germany/` can be copied from the old checkout, so nothing is
downloaded twice. The `de_` objects in the capstone database are not used by
datlas and can be dropped there.

## Next steps

- An open-ended live test with the sensors on.
- A replacement for check 7 that does not need Berlin's planning areas.
- Later: deduplicating the code datlas still shares with the capstone, and
  further themes.
