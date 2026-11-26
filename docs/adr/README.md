# Architecture decision records

The records describe why datlas is built as it is. ADRs 001–013 come from the
Berlin capstone (`ohexel/lwr`); only those that still hold or were superseded
by a later record are kept here. ADRs 014–020 were written while datlas was
the capstone's "Germany layer" and use the names of that time: database
objects with the prefix `de_` (`normalized.de_gemeinde` is now
`normalized.gemeinde`), code in `src.germany`, jobs named `germany_*`.
[ADR 021](021-separation-from-the-capstone.md) records the separation and the
renaming.

## From the capstone

- ADR 001: [Python, PostGIS and Dagster have distinct responsibilities](001-python-postgis-dagster-boundaries.md)
- ADR 003: [Forecast partitions reflect DWD publication and retention](003-source-aware-forecast-partitions.md)
- ADR 004: [Preserve population quality failures instead of inventing values](004-population-quality-and-explicit-rejection.md)
- ADR 007: [Serve observations and reference facts, not analyst decisions](007-lean-analyst-owned-serving-contract.md)
- ADR 008: [Initialize from one canonical schema and restart safely](008-canonical-schema-and-safe-restart.md) (superseded by ADR 021)
- ADR 013: [Scope forecast storage to Berlin and limit retention to 24 hours](adr_013_weather_storage_scope_and_retention.md) (superseded by ADR 018 and ADR 021)
- Notes: [Architectural scope](002_architectural_scope.md), [Why Dagster](003_why_dagster.md)

## Temperature (v2.0)

- ADR 014: [Equal-area projection for Germany-wide area weights](014-equal-area-projection-for-germany.md) (amended by ADR 021)
- ADR 015: [Roll-up weighting for Kreis, Land and Bund](015-rollup-weighting.md)
- ADR 016: [Germany map: PMTiles outlines and a JSON values file](016-map-pmtiles-and-json-values.md)
- ADR 017: [Zensus 2022 population and the checks against the source](017-zensus-2022-population-and-source-checks.md)
- ADR 018: [SQL aggregation of the forecast, and per-cell storage](018-sql-aggregation-and-cell-storage.md) (amended by ADR 021)

## Employment (v2.1)

- ADR 019: [A theme-independent indicator model, filled first with the BA Gemeindedaten](019-indicator-model-and-ba-gemeindedaten.md)

## Sectors (v2.2)

- ADR 020: [Sector data from two BA products, Kreis groups and Land divisions](020-sector-data-kreis-groups-and-land-divisions.md)

## Standalone (v3.0)

- ADR 021: [Separation from the capstone](021-separation-from-the-capstone.md)

Operating commands are in the [runbook](../runbook.md).
