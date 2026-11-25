# datlas
Öffentliche Daten in Karteform

# Germany by region: temperature forecast, employment and industry

> **Built on the Berlin capstone.** The Germany layer grew out of the capstone
> project *24h temperature forecast for Berlin neighborhoods* (tag
> `v1.0-capstone-submitted`) and is built on top of it. It runs on the
> capstone's installation, database, ICON grid, DWD forecast download and
> Dagster set-up, and it carries over what the capstone established: raw,
> normalized and analytical layers; versioned, area-weighted spatial bridges;
> source contracts pinned by checksum; Dagster asset checks as quality gates;
> sensors that stay off until switched on. The capstone itself is described at
> the end of this file: [Berlin capstone](#berlin-capstone).

The Germany layer covers every administrative level of Germany: Bund → 16
Länder → 400 Kreise → 10,990 Gemeinden, with three themes on one map:

- **Temperatur** (v2.0): for each Gemeinde the current 24-hour DWD
  ICON-D2-RUC forecast (air temperature and shade apparent temperature,
  area-weighted from the model grid) with Zensus 2022 total population, rolled
  up to Kreis, Land and Bund with both an area and a population weighting.
- **Beschäftigung** (v2.1): employment per Gemeinde from the Statistik der
  Bundesagentur für Arbeit (BA): employees by place of residence and of work,
  commuters and establishments, loaded into a theme-independent indicator
  model and checked against the BA's own published totals.
- **Industrie** (v2.2): employees by sector per Kreis and Land, quarterly, from
  two further BA products, so the share of jobs in the metal, electrical and
  steel industries and, per Land, in motor vehicles, mechanical engineering,
  chemicals and steel can be compared.

The results are checked against the sources and shown on a static MapLibre
map. Germany objects carry the prefix `de_`; the capstone's Berlin tables,
views, sensor and dashboard are unchanged.

![Germany map, Kreise: share of employees in the metal, electrical and steel industries, 31 March 2026, on a fixed scale from 0 to 40 %.](docs/images/germany-sectors-map.png)

*Sector theme: share of employees at place of work in the metal, electrical
and steel industries (WZ 2008 divisions 24–30, 32, 33), by Kreis (BA
Regionalreport, 31 March 2026; own calculation). Grey: hidden by the BA
(Wolfsburg, Ingolstadt, Passau). There are no sector figures per Gemeinde,
and per Kreis motor vehicles, mechanical engineering and steel exist only
inside this group; per Land they are published separately.*

![Germany map, Kreise: employees at place of work per employee at place of residence, BA reference date 30 June 2025, on a fixed logarithmic scale from 1/4 to 4.](docs/images/germany-employment-map.png)

*Employment theme: employees subject to social insurance at their place of
work per employee living there, by Kreis (BA, 30 June 2025; own
calculation). Orange: more employed residents than jobs; purple: more jobs
than employed residents.*

![Germany map, Kreise: highest shade apparent temperature in the next 24 hours, area-weighted, on a fixed scale from -20 to +30 °C. Forecast run 2026-11-14 09:00 UTC.](docs/images/germany-map.png)

*Temperature theme: highest shade apparent temperature over the next 24 hours
by Kreis, area-weighted (forecast run 2026-11-14 09:00 UTC). The page is in
German; a switch shows the lowest values instead (Höchstwerte / Tiefstwerte).
The colours are fixed from -20 to +30 °C, so a colour means the same
temperature on every day; the legend shows only the range the map currently
uses.*

## Start here

| Document | Use it when you want to... |
| --- | --- |
| [docs/germany-layer.md](docs/germany-layer.md) | Operate the Germany layer: data flow, checks and thresholds, map, the three themes. |
| [docs/germany-layer-facts.md](docs/germany-layer-facts.md) | Look up measured numbers: counts, sizes, run times, storage. |
| [runbook.md](runbook.md) | Install, operate, inspect, troubleshoot, or reset the pipeline. |
| [architecture.md](architecture.md) | Understand data sources, layers, spatial joins, orchestration, and the serving contracts. |
| [docs/data-sources.md](docs/data-sources.md) | Check source contracts, acquisition behavior, licenses, and attribution. |
| [docs/adr/README.md](docs/adr/README.md) | Review the principal architectural decisions and their tradeoffs. |
| [docs/testing.md](docs/testing.md) | Choose the small set of tests appropriate to your environment. |
| Release notes [v2.0](docs/release-notes-v2.0-germany.md), [v2.1](docs/release-notes-v2.1-germany-employment.md), [v2.2](docs/release-notes-v2.2-germany-sectors.md) | See what each Germany release added. |

Documents that concern only the Berlin capstone are listed in
[its section](#berlin-capstone-documents).

## Install

The Germany layer is installed on top of the capstone's base installation:
the capstone bootstrap loads the ICON grid that the Germany layer reuses, and
it requires the capstone's HOSTRADA reference archive.

What you need:

- Linux or another environment that can run Docker and Docker Compose.
- Python 3.11, installed or managed by `uv`; `uv`, Docker Engine and the
  Docker Compose plugin.
- Internet access to Python packages, the PostGIS image, the DWD Open Data
  server, Berlin Open Data, BKG, the Zensus database and the BA statistics
  portal.
- The separately distributed HOSTRADA reference archive,
  [`hostrada-reference-1995-2025.pgcustom`](https://www.ohexel.com/files/hostrada-reference-1995-2025.pgcustom)
  (232 MB).
- A free Zensus 2022 API token (`ZENSUS2022_TOKEN` in `.env`), only while the
  Zensus files are not yet under `data/raw/germany/`.
- `tippecanoe`, once, to build the map's boundary tiles.
- Disk space for PostgreSQL, the 201 MB compressed ICON grid, the reference
  archive and the resulting tables; the Germany per-cell forecast values of
  the two retained runs take about 588 MB.

```bash
git clone <repository-url> lwr
cd lwr
cp .env.example .env            # set POSTGRES_PASSWORD; ZENSUS2022_TOKEN if needed
uv sync --frozen
docker compose --env-file .env -f docker/postgres.yml up -d
export DAGSTER_HOME="$PWD/.dagster_home"

# base installation (the capstone bootstrap, about ten minutes)
uv run --env-file .env python -m src.bootstrap \
  --reference-archive /path/to/hostrada-reference-1995-2025.pgcustom
```

A successful bootstrap reports `"status": "ready"`. Options for an offline
installation and what the bootstrap installs are described under
[Berlin capstone: install and initialize](#install-and-initialize) and in the
[runbook](runbook.md#base-installation).

## Run it

```bash
# once: VG250 and Zensus raw loads, hierarchy, population, grid subset, bridge
uv run --env-file .env python -m src.germany.run_static

# per forecast run (UTC label; DWD keeps runs for about 24 hours)
uv run --env-file .env python -m src.germany.run_forecast \
  --run-time "$(date -u -d '3 hours ago' +%Y%m%dT%H00)"

# employment theme: download, load and check the BA Gemeindedaten (yearly)
uv run --env-file .env python -m src.germany.run_employment

# sector theme: 434 BA files per quarter, one request at a time (~22 minutes);
# if the BA throttles (HTTP 429), it stops, says when to run again, and resumes
uv run --env-file .env python -m src.germany.run_sectors

# export the map and open a local preview (http://127.0.0.1:8766/)
uv run --env-file .env python -m src.export_germany_dashboard --serve

# acceptance tests on the installed data (read-only)
uv run --env-file .env python -m pytest -m acceptance tests/test_germany_acceptance.py
```

The map opens with the Industrie theme at Kreis level. Details and
measurements: [docs/germany-layer.md](docs/germany-layer.md) and
[docs/germany-layer-facts.md](docs/germany-layer-facts.md); day-to-day
operation: [runbook](runbook.md#germany-layer-operation).

## Example queries

The Kreise with the highest share of jobs in metal, electrical and steel
(BA, 31 March 2026):

```sql
SELECT region_name, metal_electrical_steel, employees_total,
       ROUND(100 * metal_electrical_steel_share::numeric, 1) AS share_percent
FROM analytical.de_current_sectors
WHERE level = 'krs' AND metal_electrical_steel_share_status = 'value'
ORDER BY metal_electrical_steel_share DESC
LIMIT 10;
```

Tuttlingen leads with 50.4 %, then Dingolfing-Landau (49.9 %) and Salzgitter
(47.5 %).

The ten Kreise with the most jobs per employed resident (BA, 30 June 2025):

```sql
SELECT region_name, employees_workplace, employees_residence,
       ROUND(jobs_ratio::numeric, 2) AS jobs_ratio
FROM analytical.de_current_employment
WHERE level = 'krs'
ORDER BY jobs_ratio DESC
LIMIT 10;
```

Schweinfurt leads with 2.45 (54,018 jobs, 22,087 employed residents), then
Wolfsburg with 2.16.

The five Kreise with the highest 24-hour maximum of shade apparent temperature,
weighted by population:

```sql
SELECT kreis_name, land_name,
       max_apparent_temperature_shade_population_weighted_c,
       max_apparent_temperature_shade_population_weighted_at_berlin
FROM analytical.de_current_kreis_summary
ORDER BY 3 DESC
LIMIT 5;
```

## Checks against the sources

| # | Check | What it tests |
| --- | --- | --- |
| 1 | `de_key_coverage` | every VG250 Gemeinde has a Zensus record and the reverse; exceptions are listed |
| 2 | `de_hierarchy_integrity` | what foreign keys cannot guarantee: no empty parents, consistent Land, key parts agree with VG250, areas add up |
| 3 | `de_source_totals` | sums of Gemeinde population equal the published Kreis and Land totals; the Germany total differs by the documented 8,258 |
| 4 | `de_bridge_coverage` | each Gemeinde is covered by grid cells (sum of intersection areas / area ≥ 0.999) |
| 5 | `de_forecast_completeness` | the current views serve the newest loaded run; warns when a newer run never completed (for example a partition refused because a model field has missing values) |
| 6 | `de_forecast_plausibility` | temperatures within physical bounds, no NULLs |
| 7 | `de_berlin_cross_layer_consistency` | Berlin as one Gemeinde agrees with the roll-up of its 542 planning areas (tolerance 0.01 °C, warning) |

Two more checks verify that the raw VG250 and Zensus files match their pinned
checksums and counts. The employment theme adds:

| # | Check | What it tests |
| --- | --- | --- |
| 8 | `de_ba_source_contract` | the BA file's structure: 16 Länder in both sheets, a Germany and an unassigned row, only numbers or `*` (suppressed), `*` only for Gemeinden; checksum and row counts for a pinned vintage |
| 9 | `de_ba_column_identities` | in every row: residence = men + women, and Germans + foreigners and the commuter counts within their bounds |
| 10 | `de_ba_key_coverage` | BA Gemeinde keys against VG250: only unincorporated areas and the mergers listed for the vintage |
| 11 | `de_ba_source_totals` | Gemeinden add up to their Kreis (exactly where nothing is suppressed), Kreise to their Land, Länder plus the unassigned row to Germany |

The sector theme adds:

| # | Check | What it tests |
| --- | --- | --- |
| 12 | `de_ba_sector_source_contract` | one complete Regionalreport per Kreis and one WZ booklet per Land and Germany |
| 13 | `de_ba_sector_identities` | sections, manufacturing groups and sector rows of each Kreis add up |
| 14 | `de_ba_sector_source_totals` | Kreise to Land; Regionalreport to WZ booklets; Germany to Länder plus employees not assignable to a Land; Kreis totals to the Gemeindedaten; reviewed discrepancies only at their documented size |
| 15 | `de_ba_sector_key_coverage` | all Kreise, Länder and Germany have values for the newest quarter |

The checks found one discrepancy in the BA's own figures: on 31 March 2026
the Kreise of Hessen fall 47,649 short of the Land, because Main-Kinzig-Kreis
drops by a third in one quarter. The values are shown as published, with a
note on the map (ADR 020).

## Key tests

The Germany tests were cut to the ones that protect a decision or an observed
property of the data (test triage of 14 Nov 2026: 69 functions, 100 cases →
38 functions, 49 cases). These are the essential ones:

| Test | What it proves |
| --- | --- |
| `test_germany_ddl_only_adds_de_objects` | every Germany SQL file only adds `de_` objects; Berlin is never altered |
| `test_berlin_sensor_does_not_target_germany_jobs` | the Berlin sensor starts none of the five Germany jobs |
| `test_zensus_token_never_leaves_the_request_header` | the Zensus API echoes the token; it is sent only as a header and never appears in an error |
| `test_parse_zensus_flat_csv_keeps_signs_and_leading_zeroes` | Zensus "-" (exactly zero) and 12-digit keys with leading zeros survive into raw |
| `test_refresh_and_checks_classify_every_case` | population statuses, NULL never 0, and checks 1–3 on a synthetic geography |
| `test_static_hierarchy_is_safe_to_repeat` | `run_static` can run again: same VG250 file unchanged, another file refused |
| `test_partition_aggregation_and_retention_keeps_two_runs` | area weighting with hand-computed values, switching only to complete runs, retention |
| `test_summaries_take_the_earliest_hour_on_a_tie` | the 24-hour maximum and minimum take the earliest hour on a tie, at all four levels |
| `test_public_page_shows_the_required_attribution` | BKG, Zensus, DWD and BA attribution, the BA link and "eigene Berechnung" on the page |
| `test_read_workbook_classifies_levels_and_keeps_suppression_signs`, `test_read_workbook_refuses_layout_changes` | BA Gemeindedaten: suppressed values kept as `*`; a changed layout stops the load (future vintages load without a checksum) |
| `test_refresh_serves_published_values_with_explicit_status` | published Kreis and Land values, kreisfreie Städte, statuses with reasons, checks 8–11 |
| `test_regionalreport_parser_reads_five_quarters_and_keeps_suppression`, `test_regionalreport_parser_refuses_layout_changes` | Regionalreport: five quarters, suppression kept; rows are mapped by position, so a changed order stops the load |
| `test_ba_client_is_considerate_and_stops_on_rate_limits` | one request at a time, waits of minutes on HTTP 429, a shared cool-down, a request budget |
| `test_sector_totals_accept_only_documented_gaps_and_unassigned_employees` | a reviewed source discrepancy passes only at its documented size; Germany exceeds the Länder only by unassigned employees |
| `test_sector_refresh_and_checks_on_a_fixture_land` | Kreis and Land routes, Land-only indicators, checks 12–14 on synthetic workbooks |
| `test_all_germany_checks_pass_on_installed_data` | all 15 asset checks pass on the installed data |
| `test_current_views_are_complete_at_all_four_levels`, `test_rollups_are_consistent_across_levels` | every Gemeinde × 25 hours; Länder roll up to the Bund value with both weightings |
| `test_map_values_export_is_complete_for_the_current_run` | the map's temperature file is complete, including the minima |
| `test_employment_view_covers_every_region_with_an_explicit_status`, `test_sector_view_covers_every_kreis_and_land_with_an_explicit_status` | every region with a status; documented exceptions only; shares and ratios only from published values |

Run them with `uv run python -m pytest` (contract and unit tests),
`-m integration tests/test_germany_*.py` (synthetic data in rolled-back
transactions) and `-m acceptance tests/test_germany_acceptance.py` (installed
data, about 100 s).

## Adding a further theme

The hierarchy does not change when a theme is added. A theme whose source
publishes values per region goes into the indicator tables
([ADR 019](docs/adr/019-indicator-model-and-ba-gemeindedaten.md)): catalogue
rows (`de_indicator_source`, `de_indicator`), a raw table as delivered, a
refresh that writes `de_indicator_value` with an explicit status for every
region (value, suppressed, not reported), a serving view, a source contract
and checks against the source's own totals. The BA Gemeindedaten are the
first source built this way. Candidates for the next step are the BA's
quarterly reports per Kreis (employees by sector groups) and its pay
statistics per Kreis. The sector theme ([ADR 020](docs/adr/020-sector-data-kreis-groups-and-land-divisions.md))
uses the same tables for two sources at the levels they publish.

## Limitations

- Forecast only. There is no Germany-wide historical reference; HOSTRADA history
  stays Berlin-only.
- Population is Zensus 2022 (reference date 15 May 2022, Gebietsstand 15 May
  2022); VG250 boundaries have the status of 31 Dec 2022.
- VG250 is a generalised 1:250,000 geometry.
- Shade apparent temperature does not include solar radiation (as in Berlin).
- Employment: only employees subject to social insurance (no civil servants,
  self-employed or marginal jobs). The BA suppresses small values: 1,261
  Gemeinden have no ratio. The BA uses the territorial status of its
  reference date, the map that of 2022: 38 Gemeinden merged since then have
  no value, and a Gemeinde that absorbed another shows its larger 2025 value
  on its 2022 outline.
- Sectors: no figures per Gemeinde. Per Kreis the BA publishes only groups:
  motor vehicles, mechanical engineering and steel are part of "metal,
  electrical and steel", chemicals part of "intermediate goods" (with paper,
  glass and plastics). The four industries are separate only per Land and for
  Germany. Land values of the groups are sums (own calculation).
- The values are measurements: no thresholds, classes or exposure scores.
- A portfolio project run on a local machine, not an operated service.

## Licences and attribution

Boundaries: © GeoBasis-DE / BKG 2022 (Daten verändert), dl-de/by-2-0.
Population: Zensus 2022, © Statistische Ämter des Bundes und der Länder,
Deutschland, 2026, dl-de/by-2-0. Forecast: Deutscher Wetterdienst (DWD),
ICON-D2-RUC, CC BY 4.0. Employment: Statistik der Bundesagentur für Arbeit,
Gemeindedaten der sozialversicherungspflichtig Beschäftigten nach Wohn- und
Arbeitsort, Stichtag 30.6.2025 (<https://statistik.arbeitsagentur.de/>); the
ratio of place of work to place of residence is this project's own
calculation. Sectors: Statistik der Bundesagentur für Arbeit, Regionalreport
über Beschäftigte (Quartalszahlen) and Beschäftigte nach Wirtschaftszweigen
(WZ 2008) (Quartalszahlen); shares and Land sums of the groups are this
project's own calculations. Aggregation by this project; not an official
publication. Sources, checksums and licences are listed in
[docs/data-sources.md](docs/data-sources.md).

## Decisions

[ADR 014](docs/adr/014-equal-area-projection-for-germany.md) (equal-area
projection),
[ADR 015](docs/adr/015-rollup-weighting.md) (roll-up weighting),
[ADR 016](docs/adr/016-map-pmtiles-and-json-values.md) (map: PMTiles and JSON),
[ADR 017](docs/adr/017-zensus-2022-population-and-source-checks.md) (Zensus
and source checks),
[ADR 018](docs/adr/018-sql-aggregation-and-cell-storage.md) (SQL aggregation
and cell storage),
[ADR 019](docs/adr/019-indicator-model-and-ba-gemeindedaten.md) (indicator
model and BA Gemeindedaten),
[ADR 020](docs/adr/020-sector-data-kreis-groups-and-land-divisions.md) (sector
data). The earlier ADRs in [docs/adr/](docs/adr/README.md) record the
capstone's decisions, which the Germany layer builds on.

---

## Berlin capstone

*24h temperature forecast for Berlin neighborhoods* is the original capstone
project (tag `v1.0-capstone-submitted`) from which the Germany layer grew. It
remains part of the repository, and its installation is the base the Germany
layer runs on.

A reproducible geospatial data pipeline that combines current DWD temperature
forecasts, 31 years of historical temperature, and official population data for
Berlin's 542 planning areas.

The final PostgreSQL view gives analysts named neighborhoods, neighborhood-level
temperature and shade apparent temperature, comparable neighborhood and
citywide historical reference values, and the number of residents aged 65 or
older.

- heterogeneous source formats and grains transformed into one traceable PLR-level serving grain
- different forecast, historical, and administrative geometries are reconciled using versioned PostGIS intersection bridges with area weighting
- condensing large nationwide and multi-decade inputs: filter early, join on bridges, aggregate monthly, and delete validated monthly source files
- replicable and quick startup: clean installation in ten minutes thanks to validated checksum-verified artefacts (instead of several-hours full historical rebuild)

**The pipeline at a glance:**  
- Partitioned batch pipeline (multi-dimensional: run_time × lead_time)
- persistent source data in `raw`, 3NF tables in `normalized`, one fully denormalized OBT view served to analysts
- Dagster software-defined assets with asset lineage, asset checks as data-quality gates, and a sensor-based trigger
- PostGIS geospatial ETL:area-weighted spatial joins, reusable intersection bridge tables, CRS reprojection
- SQL-based data contracts plus pytest "contract" tests
- checksum-verified, manifest-driven snapshot distribution for the historical reference (~220MB analysis-ready artefact instead of reprocessing 220GB source data)

### Run a forecast and inspect the result

After completing the [one-time installation and bootstrap](#install-and-initialize),
run these two commands from the project root. On GNU/Linux, the first processes
a forecast from approximately two hours ago:

```bash
uv run --env-file .env python -m src.run_forecast \
  --run-time "$(date -u -d '2 hours ago' +%Y%m%dT%H00)"
```

The second queries the final analytical view using the PostgreSQL credentials
already configured inside the database container:

```bash
docker compose --env-file .env -f docker/postgres.yml \
  exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
    SELECT
      plr_id,
      plr_name,
      valid_time_berlin,
      ROUND(temperature_c::numeric, 1) AS temperature_c,
      ROUND(apparent_temperature_shade_c::numeric, 1)
        AS apparent_temperature_c,
      ROUND(plr_temperature_median_c::numeric, 1)
        AS historical_median_c,
      population_65plus
    FROM analytical.current_plr_weather_context
    ORDER BY plr_id
    LIMIT 10;
  "'
```

Example result:

| PLR ID | Neighborhood | Berlin-local time | Temperature °C | Apparent °C | Historical median °C | Residents 65+ |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `01100101` | Stülerstraße | 2026-08-24 18:00 | 20.8 | 19.5 | 22.6 | 700 |
| `01100102` | Großer Tiergarten | 2026-08-24 18:00 | 20.8 | 19.6 | 22.7 | 291 |
| `01100103` | Lützowstraße | 2026-08-24 18:00 | 20.8 | 19.5 | 22.7 | 1,106 |

Forecast run labels use UTC; very recent runs may not yet be published and
older runs may have left DWD's rolling availability window. A complete
partition contains all 542 planning areas. The Dagster UI is not required.

### Run the complete 25-point temperature forecast

This feature branch also supports a complete 24-hour horizon: lead hours 0
through 24 produce **25 hourly observations for each of Berlin's 542 PLRs**.
For an existing installation, install the additive serving views once:

```bash
bash scripts/bootstrap_database.sh
```

Run all forecast partitions sequentially, automatically skipping any that are
already complete:

```bash
uv run --env-file .env python -m src.run_forecast_horizon \
  --run-time "$(date -u -d '2 hours ago' +%Y%m%dT%H00)"
```

Inspect the compact neighborhood summary:

```bash
docker compose --env-file .env -f docker/postgres.yml \
  exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "
    SELECT
      plr_name,
      ROUND(max_forecast_temperature_c::numeric, 1) AS maximum_c,
      max_forecast_temperature_at_berlin AS maximum_at,
      ROUND(max_temperature_difference_c::numeric, 1)
        AS maximum_above_historical_median_c,
      ROUND(sum_temperature_difference_c::numeric, 1)
        AS sum_of_hourly_differences_c,
      population_65plus
    FROM analytical.current_plr_temperature_summary_25h
    ORDER BY max_temperature_difference_c DESC
    LIMIT 10;
  "'
```

The separate `analytical.current_plr_temperature_forecast_25h` view provides
all 13,550 plotting points, including forecast temperatures, corresponding
PLR-specific historical medians, and signed differences. Both views switch to
a newer model run only after all 25 lead times are complete. These two views
require only the existing historical-reference snapshot.

If your database also contains the original HOSTRADA hourly observations,
optionally extract a separate historical line for every year from 1995 to
2025. This reuses the current complete forecast without contacting DWD:

```bash
uv run --env-file .env python -m src.historical_temperature_trajectories
```

The resulting `analytical.current_plr_temperature_history_25h` view contains
420,050 plotting observations: 542 neighborhoods, 25 lead hours, and 31
historical years. The compact reference archive alone cannot reconstruct these
individual observations, and ordinary installations do not need this feature.

### Explore the interactive Berlin map locally

After the 25-hour forecast and optional historical trajectories are ready,
export the current results and start a local preview:

```bash
uv run --env-file .env python -m src.export_temperature_dashboard --serve
```

Open <http://127.0.0.1:8765/>. Hover over a planning area to inspect its
25-hour summary and compare temperature or apparent-temperature forecasts with
their historical medians and each individual year from 1995 through 2025.
Search and click-to-pin also support keyboard and touch use.

The dashboard is plain HTML, CSS, SVG, JavaScript, and static JSON. It has no
frontend package, map-tile, CDN, or production database dependency. The same
folder can therefore be uploaded to a static website. See
[docs/static-temperature-dashboard.md](docs/static-temperature-dashboard.md)
for iteration, export, and deployment details.

### Berlin capstone documents

| Document | Use it when you want to... |
| --- | --- |
| [docs/static-temperature-dashboard.md](docs/static-temperature-dashboard.md) | Preview and publish the interactive PLR map as static files. |
| [docs/distribution.md](docs/distribution.md) | Obtain, verify, or publish the external installation archives. |
| [docs/historical-rebuild.md](docs/historical-rebuild.md) | Optionally reconstruct the HOSTRADA reference from original DWD data. |
| [docs/optional-dagster-container.md](docs/optional-dagster-container.md) | Run the Dagster interface in a background container. |

### What you need

- Linux or another environment that can run Docker and Docker Compose.
- Python 3.11, installed or managed by `uv`.
- `uv`, Docker Engine, and the Docker Compose plugin.
- Internet access to Python packages, the PostGIS image, Berlin Open Data, and
  the DWD Open Data server; an optional static snapshot can replace source
  downloads after dependencies and the container image are installed.
- The separately distributed HOSTRADA reference archive,
  `hostrada-reference-1995-2025.pgcustom`.
- Sufficient local disk space for PostgreSQL, the 201 MB compressed ICON grid,
  the 232 MB reference archive, and the resulting database tables and indexes.

Python dependencies are declared in `pyproject.toml`, locked in `uv.lock`, and
installed together with the `ecCodes`, PostGIS-client, and geospatial bindings
needed by the project. PostgreSQL and PostGIS run in Docker; application code
runs in the locked Python environment.

### Install and initialize

Clone the repository and enter its root:

```bash
git clone <repository-url> berlin-temperature-context
cd berlin-temperature-context
```

Create the local configuration and choose a PostgreSQL password:

```bash
cp .env.example .env
```

Install the exact locked Python environment:

```bash
uv sync --frozen
```

Start PostgreSQL/PostGIS:

```bash
docker compose --env-file .env -f docker/postgres.yml up -d
```

Use persistent project-local Dagster state:

```bash
export DAGSTER_HOME="$PWD/.dagster_home"
```

Download the compressed HOSTRADA reference file: [link](https://www.ohexel.com/files/hostrada-reference-1995-2025.pgcustom)

Initialize the complete operational pipeline:

```bash
uv run --env-file .env python -m src.bootstrap \
  --reference-archive /path/to/hostrada-reference-1995-2025.pgcustom
```

If you also have the optional static-source archive, provide it as a verified
fallback for unavailable geography, population, or ICON-grid downloads:

```bash
uv run --env-file .env python -m src.bootstrap \
  --reference-archive /path/to/hostrada-reference-1995-2025.pgcustom \
  --static-snapshot /path/to/static-inputs.tar.xz
```

Add `--offline` to use that snapshot directly instead of attempting static
source downloads. The initial clean-room bootstrap took approximately ten
minutes on the development laptop. Subsequent runs preserve existing data,
validate completed static inputs, and do not reimport an already valid
historical reference.

A successful bootstrap reports `"status": "ready"`. It does not download the
1995–2025 historical HOSTRADA archive.
The official 542-PLR name directory is acquired automatically; a verified,
64 KB workbook included in the repository supplies its offline fallback.

### Orchestration and tests

Inspect the registered jobs and assets:

```bash
uv run --env-file .env dg list defs
```

Start the Dagster interface:

```bash
uv run --env-file .env dagster dev \
  -m src.dagster_pipeline.definitions
```

The forecast availability sensor is intentionally **stopped by default**. Start
`dwd_icon_d2_ruc_availability_sensor` manually in the Dagster interface when
automated ingestion is desired. It checks whether all required forecast fields
are available before launching a run.

For an optional background interface on this branch, see
[containerized Dagster](docs/optional-dagster-container.md). The normal
host-based commands and PostgreSQL installation remain unchanged.

Run the default database-independent test suite:

```bash
uv run python -m pytest
```

After completing the operational bootstrap and processing at least one
forecast, run the end-to-end acceptance checks:

```bash
uv run --env-file .env python -m pytest \
  -m "acceptance and not historical_rebuild"
```

See [docs/testing.md](docs/testing.md) for focused data contracts, database
integration checks, and the optional historical-rebuild suite.

### What is distributed separately

| Artifact | Required? | Size | Purpose |
| --- | --- | ---: | --- |
| `hostrada-reference-1995-2025.pgcustom` | Yes | 231,645,982 bytes | Precomputed PLR and Berlin historical references. |
| `static-inputs.tar.xz` | Optional | 198,011,500 bytes | Verified fallback copies of LOR geography, population, and the ICON grid. |

Expected archive checksums and contents are recorded under `snapshots/`; see
[docs/distribution.md](docs/distribution.md). Neither archive belongs in Git.

### Scope and data interpretation

The pipeline provides **shade apparent temperature**, derived from air
temperature, relative humidity, and wind. It does not incorporate solar
radiation and therefore does not claim to calculate comprehensive heat stress.

The HOSTRADA reference uses the current 542-PLR geography, the years 1995–2025,
Berlin-local calendar hours, and median/p90/maximum values. Historical February
29 is excluded. Daylight-saving gaps and repeated hours are preserved according
to the `Europe/Berlin` timezone rules.

Geography-version identifiers, population reference dates, source provenance,
and quality diagnostics remain available below the serving layer. Analysts
receive measurements and essential time/geographic context rather than
predefined thresholds, classifications, or exposure estimates.
