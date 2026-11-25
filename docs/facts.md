# Measured facts

Only values measured on this project's data and runs; nothing here is
estimated. Re-measured on 25 Nov 2026 on the standalone installation
(PostgreSQL 16.9, PostGIS 3.5.2, container `datlas_postgres`, reached from the
sandbox): a database built from empty with `run_static`, `run_employment` and
`run_sectors`, the forecast run 2026-11-25 15:00 UTC, and the test runs of that
day. Values that depend only on the data were measured on 14 Nov on the
capstone database and reproduced identically on 25 Nov (comparison in
[ADR 021](adr/021-separation-from-the-capstone.md)); they are marked. Earlier
measurements are kept only where a decision rests on them; they are in the last
section, with their dates.

Sizes in MB are PostgreSQL's `pg_size_pretty` units (1 MB = 1,048,576 bytes);
file sizes are given in bytes.

## Sources

| Fact | Value |
| --- | ---: |
| VG250 vintage | 31.12.2022 |
| VG250 GeoPackage archive (`vg250_12-31.utm32s.gpkg.ebenen.zip`) | 72,214,199 bytes |
| VG250 delivered features, Staat / Länder / Kreise / Gemeinden | 11 / 35 / 430 / 11,119 |
| of which land parts (GF = 4) | 1 / 16 / 400 / 10,990 |
| Zensus 2022 table | 1000A-1003 |
| Zensus raw rows, Länder / Kreise / Gemeinden extract (`GEOBL1` / `GEOLK4` / `GEOGM4`) | 204 / 4,812 / 129,444 |
| Zensus Gemeinden with a record | 10,786 |

## Normalized model (geography version `vg250-2022-12-31`)

| Fact | Value |
| --- | ---: |
| Länder / Kreise / Gemeinden | 16 / 400 / 10,990 |
| Gemeinden with a census value | 10,786 |
| Unincorporated areas (*gemeindefreie Gebiete*) | 206 |
| of which without a census record (population NULL) | 204 |
| of which with census residents | 2 (Lohheide 747, Osterheide 2,042) |
| Total Gemeinde area, EPSG:3035 | 357,201 km² |
| Invalid geometries, Länder / Kreise / Gemeinden | 0 / 0 / 0 |
| Largest relative difference, Σ Gemeinde area vs. Kreis area | 5.0 × 10⁻¹⁵ |

## Checks (run 25 Nov 2026)

All 17 asset checks pass on the new database (current run 2026-11-25 15:00
UTC, BA reference date 30 June 2025, BA file date 31 March 2026).

| Check | Result |
| --- | --- |
| Grid | 272,089 vertices, 542,040 cells, 1,626,120 topology rows; 542,040 valid triangles in EPSG:3035; 0 rejected |
| VG250 and Zensus source contracts | 0 failures |
| 1 Key coverage | 204 non-blocking exceptions (unincorporated areas without a census record), 0 blocking |
| 2 Hierarchy integrity | 0 violations; 400 Kreise checked for the area partition, largest relative difference 5.0 × 10⁻¹⁵ (tolerance 10⁻⁹) |
| 3 Source totals | 400 of 400 Kreise and 16 of 16 Länder exact; Σ Gemeinden 82,711,282 against the published Germany total 82,719,540, difference 8,258 = expected |
| 4 Bridge coverage | 10,990 Gemeinden, coverage 0.999999999999769 … 1.0000000000001321, 0 exceptions (threshold 0.999) |
| 5 Forecast completeness | run 2026-11-25 15:00 UTC: 25 of 25 lead times, 274,750 of 274,750 rows |
| 6 Plausibility | 0 NULL and 0 out-of-bounds rows among 274,750 Gemeinde and 2,059,525 cell rows; observed −7.44 … 5.67 °C (temperature), −13.49 … 2.29 °C (apparent) |
| 8–11 BA Gemeindedaten | 0 failures; source totals: 3,110 comparisons, 2,620 exact, 490 with suppressed parts |
| 12–15 BA sectors | 0 failures; 400 Kreis files, 17 WZ booklets; Kreis totals = Gemeindedaten in 400 of 400 Kreise |

## Grid and bridge (ICON grid `icon_grid_0047_R19B07_L`)

| Fact | Value |
| --- | ---: |
| Grid file `icon_grid_0047_R19B07_L.nc.bz2` | 201,429,184 bytes |
| Cells in `normalized.icon_cell` (whole ICON-D2 domain, EPSG:3035) | 542,040 |
| Mean cell area, all cells / cells in the bridge | 4.438 / 4.442 km² |
| Cells in the bridge (= cells of a forecast) | 82,381 |
| Cells touching a Gemeinde without sharing area | 0 |
| Cell-Gemeinde bridge rows | 184,464 |
| Gemeinden in the bridge | 10,990 |
| Size `raw.icon_grid_vertex` / `raw.icon_grid_cell_vertex` (heap + indexes) | 35 MB / 240 MB |
| Size `normalized.icon_cell` (heap + indexes) | 139 MB (90 + 49) |
| Size `normalized.icon_cell_gemeinde_bridge` (heap + indexes) | 48 MB |

Cells built directly in EPSG:3035 against the capstone's route through
EPSG:25833 (14 Nov, on the 82,381 cells of the bridge): identical row sets;
largest absolute difference of `fraction_of_gemeinde` 4.05 × 10⁻¹²; largest
relative difference of cell area 4.85 × 10⁻¹²; relative difference of
intersection area up to 1.58 × 10⁻⁷, only for slivers (0.0026 m²), at most
5.7 × 10⁻¹⁰ for intersections of 1,000 m² or more. On the 25 Nov comparison
the largest difference of an intersection area was 2.1 × 10⁻⁵ m².

## Forecast runs and storage

| Fact | Value |
| --- | ---: |
| Cell rows per run (82,381 cells × 25 lead hours) | 2,059,525 |
| Gemeinde rows per run (10,990 × 25) | 274,750 |
| Serving rows, current run: Gemeinde / Kreis / Land / Bund | 274,750 / 10,000 / 400 / 25 |
| DWD GRIB files of one run (4 fields × 25 lead times), 2026-11-25 15:00 UTC | 81,516,384 bytes |
| `normalized.icon_cell_value`, one run, freshly written (heap + indexes) | 180 MB (118 + 62) |
| `normalized.gemeinde_forecast`, one run (heap + indexes) | 53 MB |
| Whole database: grid, hierarchy, one run, employment, sectors | 1,081 MB |

## Values of the run 2026-11-14 09:00 UTC

Measured 14 Nov on the capstone database; the standalone installation
reproduced this run on 25 Nov with Gemeinde values within 6.3 × 10⁻¹² °C and
an identical `values.json`.


| Fact | Value |
| --- | ---: |
| Germany, lead hour 0, air temperature, area- vs. population-weighted | 2.81 °C vs. 2.83 °C |
| Largest Kreis difference between the two weightings, apparent temperature | 2.35 °C (Reutlingen, lead hour 5) |
| Gemeinde 24-hour maxima of apparent temperature, range | −2.08 … 9.41 °C |
| Gemeinde 24-hour minima of apparent temperature, range | −8.73 … 0.06 °C |
| Germany, apparent temperature, area-weighted: 24-hour maximum / minimum | 2.93 °C (14 Nov 14:00) / −3.09 °C (15 Nov 05:00), Berlin time |
| Germany, apparent temperature, population-weighted: 24-hour maximum / minimum | 3.46 °C / −2.69 °C |

## Runtimes (25 Nov 2026, sandbox → PostgreSQL container on the host)

| Step | Duration |
| --- | ---: |
| `run_static` on an empty database, grid file on disk (7 checks pass) | 3 min 59 s |
| of which: raw grid load / cell build / bridge | 60 s / 45 s / 1 min 43 s |
| Same, before the bridge analyzed its tables first | bridge 8 min 33 s |
| Same with the grid download (201 MB) | 5 min 11 s |
| Forecast run 2026-11-25 15:00 UTC, 25 partitions incl. DWD download and decoding | 143.5 s (5.7 s per partition) |
| Forecast run 2026-11-14 09:00 UTC, 25 partitions, GRIB files on disk | 84.4 s (3.4 s per partition) |
| Publish (retention, checks 5–6), before the export was part of it | 18.4 s |
| Publish with map export (tiles exist) | 43.6 s |
| Map export with tile build into an empty folder | 42.7 s |

## Map export

| Fact | Value |
| --- | ---: |
| Boundary tiles `vg250-2022-12-31.pmtiles` (3 layers, zoom 4–10, tippecanoe v2.53.0) | 13,139,512 bytes; tile data identical to the 14 Nov build |
| `values.json`, run 2026-11-14 09:00 UTC / 2026-11-25 15:00 UTC | 5,259,619 / 5,288,497 bytes |
| `employment.json` (30 June 2025) / `sectors.json` (31 March 2026) | 2,242,571 / 170,876 bytes |

Measured 14 Nov on the page (headless Chromium, run 2026-11-14 09:00 UTC):

| Fact | Value |
| --- | ---: |
| Scripted session (load at Kreise, Gemeinden, three zoom steps, Länder, Tiefstwerte), requests to `data/` | 19 (values.json + 18 tile ranges), 8,382,022 bytes uncompressed; largest tile range 484,160 bytes |
| Console and page errors (1400 × 900 and 390 × 844; level and max/min switches, details panel) | 0 |
| Horizontal overflow at 390 px | none |
| HTTP Range on www.ohexel.com and ohexel.com (232 MB file), tested 2026-11-09 | 206 for first, middle and suffix ranges |
| Revalidation of `values.json` on www.ohexel.com with `If-None-Match`, tested 2026-11-25 | 304 |

## Tests (25 Nov 2026)

| Suite | Result |
| --- | ---: |
| Default suite `uv run python -m pytest` | 81 passed |
| Database tests `-m integration` | 8 passed in 10.5 s |
| Acceptance tests `-m acceptance` on the installed data | 9 passed in 40–48 s |
| All tests `-m ""` | 98 passed in 76.6 s |
| `ruff check` | all checks passed |

## Employment theme: BA Gemeindedaten (measured 14 Nov 2026, reproduced 25 Nov)

Vintage 30 June 2025, on geography version `vg250-2022-12-31`.

| Fact | Value |
| --- | ---: |
| xlsx file | 1,608,751 bytes |
| Rows in sheet `Gemeindedaten`: Gemeinden / Kreise / Regierungsbezirke / Länder | 10,752 / 294 / 20 / 16 |
| Rows in sheet `Länder`: Länder / unassigned / Germany | 16 / 1 / 1 |
| `raw.ba_gemeindedaten` rows | 11,100 |
| Suppressed cells (`*`), all in Gemeinde rows | 7,723 |
| Gemeinden without employees at place of work (suppressed) | 1,257 |
| BA Gemeinden without a VG250 key / incorporated VG250 Gemeinden without a BA row / unincorporated areas without a BA row | 4 / 38 / 204 |
| Kreise with a Kreis row / taken from their single Gemeinde row | 294 / 106 |
| `normalized.indicator_value` rows (13 indicators) | 148,291 |
| of which Gemeinden: value / suppressed / not reported | 132,002 / 7,722 / 3,146 |
| of which Kreise / Länder / Germany: value | 5,200 / 208 / 13 |
| Size `raw.ba_gemeindedaten` / `normalized.indicator_value` (heap + indexes) | 17 MB / 81 MB |
| `run_employment` (job `employment`: download skipped, raw load, refresh, 4 checks), 25 Nov on a new database | 11.0 s |
| Refresh `refresh_ba_indicators` | 5.3 s |
| Download, structural check and parse of the file | 5.2 s |

Checks on this vintage, all passing:

| Check | Result |
| --- | --- |
| Source totals, Gemeinden to Kreis (294 Kreise × 10 additive indicators) | exact in every comparison without a suppressed part; with suppressed parts the published value is never below the visible sum; largest gap: establishments 12.2 %, employees under 20 10.4 %, Germans 8.2 %, employees at place of work 7.4 % |
| Source totals, Kreise to Land (16 × 10) and Länder plus unassigned to Germany (10) | exact in all 170 comparisons |
| Column identities, all 11,100 rows | 0 violations |
| Key coverage | exactly the pinned exceptions |
| Unassigned row ("keine Angabe/keine Zuordnung möglich") | 2,160 employees at place of work: the difference between Σ Länder (34,883,328) and Germany (34,885,488) |

`jobs_ratio` (employees at place of work / employees at place of residence):

| Level | With a ratio | Minimum | Median | Maximum | Above 1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemeinden | 9,487 of 10,990 | 0.00 | 0.48 | 39.0 (Büttel) | 1,449 |
| Kreise | 400 | 0.41 | 0.90 | 2.45 (Schweinfurt) | 121 |
| Länder | 16 | 0.86 | 1.00 | 1.32 | 8 |
| Germany | 1 | | 1.007 | | |

Map export with the employment theme (tiles exist): 21.3 s;
`employment.json` 2,242,571 bytes, 247,945 gzip-compressed.

## Sector theme: BA Regionalreport and WZ booklets (measured 14 Nov 2026, reproduced 25 Nov)

Files for 31 Mar 2026 (Regionalreport, WZ booklets) and 31 Mar 2025 (WZ
booklets for the year-on-year change), on geography version
`vg250-2022-12-31`.

| Fact | Value |
| --- | ---: |
| Downloads for 31 Mar 2026: Kreis files + WZ booklets / requests / bytes / time (1.5 s pause) | 400 + 17 / 417 / 222,319,668 / 624.4 s |
| Downloads for 31 Mar 2025: WZ booklets / bytes / time | 17 / 10,337,979 / 24.4 s |
| Retries needed | 0 |
| Files on disk: Regionalreport / WZ booklets | 212,590,275 / 20,215,764 bytes |
| `raw.ba_regionalreport` rows: table 2.3 / table 2.1 (400 files × 5 quarters) | 52,000 / 120,000 |
| Suppressed cells in table 2.3 (all Kreise, five quarters) | 1,278 |
| `raw.ba_wz_heft` rows per quarter (17 booklets) / suppressed in column 1 | 6,120 / 915 (2026), 885 (2025) |
| Sector rows in `normalized.indicator_value`: Kreise value / suppressed; Länder value / suppressed; Germany value | 44,788 / 1,212; 2,720 / 192; 182 |
| Size `raw.ba_regionalreport` / `raw.ba_wz_heft` (heap + indexes), 14 Nov on the capstone database | 171 MB / 14 MB |
| `run_sectors` with files on disk (raw load of both quarters, refresh, 4 checks), 25 Nov on a new database | 69.5 s |
| Refresh `refresh_sectors` (catalogue, values, quality notes) | 3.1 s |

Checks, all passing for the file date 31 Mar 2026:

| Comparison | Result |
| --- | --- |
| Identities in table 2.3 (7 rules × 400 Kreise × 5 quarters) | 0 violations |
| Σ Kreise = Land (16 Länder × 5 quarters) | 79 exact; 1 documented discrepancy (Hessen, 31 Mar 2026: Kreise 47,649 below the Land; Main-Kinzig-Kreis -34 % in one quarter) |
| Land total, Regionalreport = WZ booklet (16 × 2 quarters) | 32 exact |
| Kreis groups vs WZ divisions per Land (4 groups × 16 × 2 quarters) | 37 exact; 74 within bounds (one side with suppressed parts); 13 not comparable (both sides); 4 documented (Hessen 2026) |
| Germany − Σ Länder (employees not assignable to a Land) | 2,285 (31 Mar 2025), 2,160 (30 Jun 2025), 1,979 (30 Sep 2025), 1,343 (31 Dec 2025), 2,140 (31 Mar 2026); WZ booklets the same for their quarters |
| Germany − Σ Länder on 30 Jun 2025 vs the Gemeindedaten's unassigned row | 2,160 = 2,160 |
| Kreis totals on 30 Jun 2025 vs Gemeindedaten employees at place of work | 400 of 400 exact |

Share of metal, electrical and steel (WZ 24–30, 32, 33), 31 Mar 2026:

| Level | With a share | Minimum | Median | Maximum | Above 40 % |
| --- | ---: | ---: | ---: | ---: | ---: |
| Kreise | 397 of 400 (suppressed: Wolfsburg, Ingolstadt, Passau) | 1.0 % | 11.2 % | 50.4 % (Tuttlingen) | 4 |
| Länder (13 as sums of divisions, 3 as sums of Kreise) | 16 | 3.9 % (Berlin) | 10.1 % | 19.8 % (Baden-Württemberg) | 0 |
| Germany | 1 | | 12.0 % | | |

Germany, 31 Mar 2026: 4,193,440 employees in metal, electrical and steel of
34,825,934; motor vehicles (29) 814,984, mechanical engineering (28)
1,011,219, chemicals (20) 326,138, steel (24.1) 82,440. Suppressed at Land
level: steel in 4 Länder, motor vehicles in 2, manufacturing as a whole in 4,
intermediate goods in 2, consumer goods in 3.

Map export: `sectors.json` 170,876 bytes; whole export with all three themes
(tiles exist) 21.4 s.

## Earlier measurements that decisions rest on

### SQL vs. Python aggregation

Measured 2026-11-09; basis for ADR 018. Both implementations ran on the same decoded fields: 102 partitions of four
runs (2026-11-09 16:00, 17:00, 18:00 and 19:00 UTC; lead 0 of the first run
measured three times). The runs 16:00–18:00 used the earlier wide cell table,
the run 19:00 the current slim layout. Raw rows: 714, exported to
`de_aggregation_benchmark-2026-11-09.csv` outside the repository before the
benchmark table was dropped. Seconds per partition:

| Stage | Implementation | Runs 16–18 (77 partitions): mean / median / max | Run 19 (25 partitions): mean / median / max |
| --- | --- | ---: | ---: |
| Load bridge from PostgreSQL | shared | 0.563 / 0.557 / 0.814 | 0.606 / 0.567 / 1.032 |
| Decode 4 GRIB fields, select Germany cells | shared | 0.125 / 0.120 / 0.605 | 0.127 / 0.124 / 0.158 |
| COPY 4 raw indicators of 82,381 cells | SQL | 0.946 / 0.942 / 1.166 | 0.953 / 0.952 / 1.065 |
| Units, apparent temperature, store cells, aggregate, store Gemeinden | SQL | 1.038 / 1.069 / 1.803 | 1.259 / 1.149 / 1.816 |
| Units, apparent temperature, aggregate (numpy) | Python | 0.007 / 0.007 / 0.022 | 0.008 / 0.008 / 0.013 |
| COPY 10,990 Gemeinde values | Python | 0.079 / 0.075 / 0.186 | 0.081 / 0.079 / 0.121 |
| COPY 82,381 cell values | Python | 0.477 / 0.474 / 0.580 | 0.493 / 0.489 / 0.556 |
| **Per partition, aggregation and storage** | SQL / Python | 1.98 / 0.56 | 2.21 / 0.58 |

Per run of 25 lead hours (one measurement per lead hour, without loading the
bridge): SQL 52.7, 48.1 and 47.2 s for the runs 16–18 and 55.3 s for the run
19; Python 14.3, 13.8, 14.1 and 14.5 s. Largest difference between the two
results over all 102 partitions: 1.4 × 10⁻¹⁴ °C (floating-point summation
order).

### Cell storage layouts

Measured 2026-11-09; basis for ADR 018.

| Layout, 2 retained runs | Size (heap + indexes) |
| --- | ---: |
| First layout `de_icon_cell_weather` (run, lead time and grid keys on every row) | 1,259 MB (743 + 516) |
| Slim layout `icon_cell_value`, freshly written | 361 MB (237 + 124) |
| Slim layout with `real` (float4) instead of `double precision` (not adopted) | 329 MB (205 + 124) |

On the capstone database on 14 Nov the same layout took 588 MB for two runs
after several retention cycles (541 MB on 9 Nov after one), because the space
of a pruned run is reused by PostgreSQL, not returned to the operating system.

### Weighting example

Measured 2026-11-09; cited in ADR 015. Germany, lead hour 0 of the run 2026-11-09 16:00 UTC (no longer retained),
air temperature: 5.25 °C area-weighted against 6.08 °C population-weighted.
