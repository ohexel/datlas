# datlas
Öffentliche Daten in Kartenform

**Germany by region: temperature forecast, employment and industry.** datlas
covers every administrative level of Germany, Bund → 16 Länder → 400 Kreise →
10,990 Gemeinden, with three themes on one map:

- **Temperatur:** for each Gemeinde the current 24-hour DWD ICON-D2-RUC
  forecast (air temperature and shade apparent temperature, area-weighted from
  the model grid) with Zensus 2022 total population, rolled up to Kreis, Land
  and Bund with both an area and a population weighting. Updated hourly by
  itself once its sensors are on.
- **Beschäftigung:** employment per Gemeinde from the Statistik der
  Bundesagentur für Arbeit (BA): employees by place of residence and of work,
  commuters and establishments, loaded into a theme-independent indicator
  model and checked against the BA's own published totals.
- **Industrie:** employees by sector per Kreis and Land, quarterly, from two
  further BA products, so the share of jobs in the metal, electrical and steel
  industries and, per Land, in motor vehicles, mechanical engineering,
  chemicals and steel can be compared.

The results are checked against the sources and shown on a static MapLibre
map: <https://www.ohexel.com/germany-dashboard/>.

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
| [docs/runbook.md](docs/runbook.md) | Install, run, inspect, troubleshoot or reset datlas. |
| [docs/pipeline.md](docs/pipeline.md) | Understand the data flow, the checks and their thresholds, the map and the three themes. |
| [docs/architecture.md](docs/architecture.md) | See the sources, layers, schema, orchestration and failure boundaries at a glance. |
| [docs/facts.md](docs/facts.md) | Look up measured numbers: counts, sizes, run times, storage. |
| [docs/data-sources.md](docs/data-sources.md) | Check source contracts, acquisition behaviour, licences and attribution. |
| [docs/testing.md](docs/testing.md) | Run the tests and see what each protects. |
| [docs/adr/README.md](docs/adr/README.md) | Review the decisions and their trade-offs. |

## Quick start

You need Docker with the Compose plugin, `uv` and Python 3.11, network access
to DWD, BKG, the Zensus database and the BA, and a free Zensus 2022 API token
while the Zensus files are not yet under `data/raw/germany/`.

```bash
git clone https://github.com/ohexel/datlas.git && cd datlas
cp .env.example .env            # set POSTGRES_PASSWORD, DAGSTER_UID/GID (id -u, id -g); ZENSUS2022_TOKEN if needed
uv sync --frozen

# PostgreSQL/PostGIS (127.0.0.1:5433) and Dagster (http://127.0.0.1:3001)
docker compose --env-file .env -f docker/postgres.yml -f docker/dagster.yml up -d --build

# once: ICON grid and cells, VG250, Zensus, hierarchy, population, bridge (~4 min)
uv run --env-file .env python -m src.run_static
# employment (yearly) and sectors (quarterly; ~22 minutes on first download)
uv run --env-file .env python -m src.run_employment
uv run --env-file .env python -m src.run_sectors
```

Then switch on `forecast_publish_sensor` and `dwd_forecast_availability_sensor`
in the Dagster interface (Automation). From then on every DWD run is
processed, published and exported to `web/germany-dashboard/` without anyone
starting it. A single run can also be processed by hand:

```bash
uv run --env-file .env python -m src.run_forecast \
  --run-time "$(date -u -d '3 hours ago' +%Y%m%dT%H00)"

# local preview of the map (http://127.0.0.1:8766/)
uv run --env-file .env python -m src.export_germany_dashboard --serve
```

Details, the sensors and day-to-day operation: [docs/runbook.md](docs/runbook.md).

## Example queries

The Kreise with the highest share of jobs in metal, electrical and steel
(BA, 31 March 2026):

```sql
SELECT region_name, metal_electrical_steel, employees_total,
       ROUND(100 * metal_electrical_steel_share::numeric, 1) AS share_percent
FROM analytical.current_sectors
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
FROM analytical.current_employment
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
FROM analytical.current_kreis_summary
ORDER BY 3 DESC
LIMIT 5;
```

(`_at_berlin` is the time in Europe/Berlin.)

## Checks against the sources

Seventeen Dagster asset checks. Besides the numbered ones below, three check
the inputs: the ICON grid file and its 542,040 cells, and the raw VG250 and
Zensus files against their pinned checksums and counts.

| # | Check | What it tests |
| --- | --- | --- |
| 1 | `key_coverage` | every VG250 Gemeinde has a Zensus record and the reverse; exceptions are listed |
| 2 | `hierarchy_integrity` | what foreign keys cannot guarantee: no empty parents, consistent Land, key parts agree with VG250, areas add up |
| 3 | `source_totals` | sums of Gemeinde population equal the published Kreis and Land totals; the Germany total differs by the documented 8,258 |
| 4 | `bridge_coverage` | each Gemeinde is covered by grid cells (sum of intersection areas / area ≥ 0.999) |
| 5 | `forecast_completeness` | the current views serve the newest loaded run; warns when a newer run never completed (for example a partition refused because a model field has missing values) |
| 6 | `forecast_plausibility` | temperatures within physical bounds, no NULLs |

The employment theme adds:

| # | Check | What it tests |
| --- | --- | --- |
| 8 | `ba_source_contract` | the BA file's structure: 16 Länder in both sheets, a Germany and an unassigned row, only numbers or `*` (suppressed), `*` only for Gemeinden; checksum and row counts for a pinned vintage |
| 9 | `ba_column_identities` | in every row: residence = men + women, and Germans + foreigners and the commuter counts within their bounds |
| 10 | `ba_key_coverage` | BA Gemeinde keys against VG250: only unincorporated areas and the mergers listed for the vintage |
| 11 | `ba_source_totals` | Gemeinden add up to their Kreis (exactly where nothing is suppressed), Kreise to their Land, Länder plus the unassigned row to Germany |

The sector theme adds:

| # | Check | What it tests |
| --- | --- | --- |
| 12 | `ba_sector_source_contract` | one complete Regionalreport per Kreis and one WZ booklet per Land and Germany |
| 13 | `ba_sector_identities` | sections, manufacturing groups and sector rows of each Kreis add up |
| 14 | `ba_sector_source_totals` | Kreise to Land; Regionalreport to WZ booklets; Germany to Länder plus employees not assignable to a Land; Kreis totals to the Gemeindedaten; reviewed discrepancies only at their documented size |
| 15 | `ba_sector_key_coverage` | all Kreise, Länder and Germany have values for the newest quarter |

Check 7 compared Berlin with its planning areas while datlas was part of the
Berlin capstone; it was removed with the separation (ADR 021).

The checks found one discrepancy in the BA's own figures: on 31 March 2026
the Kreise of Hessen fall 47,649 short of the Land, because Main-Kinzig-Kreis
drops by a third in one quarter. The values are shown as published, with a
note on the map (ADR 020).

## Key tests

98 tests, each protecting a decision or an observed property of the data
([docs/testing.md](docs/testing.md)). The essential ones:

| Test | What it proves |
| --- | --- |
| `test_schema_files_build_the_database_from_empty_twice` | the schema files build the whole database on an empty one, can be applied again, and create exactly the objects they declare |
| `test_zensus_token_never_leaves_the_request_header` | the Zensus API echoes the token; it is sent only as a header and never appears in an error |
| `test_parse_zensus_flat_csv_keeps_signs_and_leading_zeroes` | Zensus "-" (exactly zero) and 12-digit keys with leading zeros survive into raw |
| `test_refresh_and_checks_classify_every_case` | population statuses, NULL never 0, and checks 1–3 on a synthetic geography |
| `test_static_hierarchy_is_safe_to_repeat` | `run_static` can run again: same VG250 file unchanged, another file refused |
| `test_partition_aggregation_and_retention_keeps_two_runs` | area weighting with hand-computed values, switching only to complete runs, retention |
| `test_summaries_take_the_earliest_hour_on_a_tie` | the 24-hour maximum and minimum take the earliest hour on a tie, at all four levels |
| `test_sensor_leaves_partitions_with_runs_out_before_the_cap`, `test_newest_complete_run_is_published_once` | the forecast sensor's cap counts only new runs; each complete run is published once |
| `test_old_run_still_in_the_database_keeps_its_files` | GRIB files of a run still in the database are kept past 24 hours |
| `test_public_page_shows_the_required_attribution` | BKG, Zensus, DWD and BA attribution, the BA link and "eigene Berechnung" on the page |
| `test_read_workbook_classifies_levels_and_keeps_suppression_signs`, `test_read_workbook_refuses_layout_changes` | BA Gemeindedaten: suppressed values kept as `*`; a changed layout stops the load (future vintages load without a checksum) |
| `test_refresh_serves_published_values_with_explicit_status` | published Kreis and Land values, kreisfreie Städte, statuses with reasons, checks 8–11 |
| `test_regionalreport_parser_reads_five_quarters_and_keeps_suppression`, `test_regionalreport_parser_refuses_layout_changes` | Regionalreport: five quarters, suppression kept; rows are mapped by position, so a changed order stops the load |
| `test_ba_client_is_considerate_and_stops_on_rate_limits` | one request at a time, waits of minutes on HTTP 429, a shared cool-down, a request budget |
| `test_sector_totals_accept_only_documented_gaps_and_unassigned_employees` | a reviewed source discrepancy passes only at its documented size; Germany exceeds the Länder only by unassigned employees |
| `test_sector_refresh_and_checks_on_a_fixture_land` | Kreis and Land routes, Land-only indicators, checks 12–14 on synthetic workbooks |
| `test_all_checks_pass_on_installed_data` | all 17 asset checks pass on the installed data |
| `test_current_views_are_complete_at_all_four_levels`, `test_rollups_are_consistent_across_levels` | every Gemeinde × 25 hours; Länder roll up to the Bund value with both weightings |
| `test_map_values_export_is_complete_for_the_current_run` | the map's temperature file is complete, including the minima |
| `test_employment_view_covers_every_region_with_an_explicit_status`, `test_sector_view_covers_every_kreis_and_land_with_an_explicit_status` | every region with a status; documented exceptions only; shares and ratios only from published values |

## Adding a further theme

The hierarchy does not change when a theme is added. A theme whose source
publishes values per region goes into the indicator tables
([ADR 019](docs/adr/019-indicator-model-and-ba-gemeindedaten.md)): catalogue
rows (`indicator_source`, `indicator`), a raw table as delivered, a refresh
that writes `indicator_value` with an explicit status for every region (value,
suppressed, not reported), a serving view, a source contract and checks
against the source's own totals, and its own asset group and job. The BA
Gemeindedaten were the first source built this way; the sector theme
([ADR 020](docs/adr/020-sector-data-kreis-groups-and-land-divisions.md)) uses
the same tables for two sources at the levels they publish. A candidate for
the next step is the BA's pay statistics per Kreis.

## Limitations

- Forecast only: there is no Germany-wide historical reference.
- Population is Zensus 2022 (reference date 15 May 2022, Gebietsstand 15 May
  2022); VG250 boundaries have the status of 31 Dec 2022.
- VG250 is a generalised 1:250,000 geometry.
- Shade apparent temperature does not include solar radiation.
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

Code: AGPL-3.0 ([LICENSE](LICENSE)).

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

## Origin and versions

datlas grew out of the capstone project *24h temperature forecast for Berlin
neighborhoods* ([ohexel/lwr](https://github.com/ohexel/lwr), release v1.0). It
started as a "Germany layer" on top of the capstone's database and Dagster
project and kept its architecture: raw, normalized and analytical layers;
versioned, area-weighted spatial bridges; source contracts pinned by checksum;
Dagster asset checks as quality gates. Since v3.0 it runs on its own
([ADR 021](docs/adr/021-separation-from-the-capstone.md)).

| Version | Content |
| --- | --- |
| v2.0 | Temperature theme, as a layer of the capstone ([notes](docs/release-notes-v2.0-germany.md)) |
| v2.1 | Employment theme ([notes](docs/release-notes-v2.1-germany-employment.md)) |
| v2.2 | Sector theme ([notes](docs/release-notes-v2.2-germany-sectors.md)) |
| v3.0 | Standalone: own installation, plain names, sensors and map export for unattended operation ([notes](docs/release-notes-v3.0-standalone.md)) |

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
data),
[ADR 021](docs/adr/021-separation-from-the-capstone.md) (separation from the
capstone). The capstone decisions that still hold are listed in
[docs/adr/README.md](docs/adr/README.md).
