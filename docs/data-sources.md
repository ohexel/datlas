# Source systems, contracts, and attribution

datlas combines the DWD forecast with official boundaries, population and
employment statistics. Source licences apply to source data and redistributed
derivatives; they do not automatically license this repository's software.

## DWD ICON forecast grid

- Publisher: Deutscher Wetterdienst.
- Grid: `icon_grid_0047_R19B07_L`.
- Source:
  `https://opendata.dwd.de/weather/lib/cdo/icon_grid_0047_R19B07_L.nc.bz2`.
- Compressed source size: 201,429,184 bytes.
- SHA-256:
  `985ae3f69611fa224c5506417520f6291d14f3135a73d5e88901a24e99dc6648`.
- Vertices: 272,089.
- Cells: 542,040.
- Cell-to-vertex topology rows: 1,626,120.

The static job downloads the grid file when it is missing, checks its counts
and builds every cell as a triangle in EPSG:3035 (`normalized.icon_cell`).
Forecast values are stored for the cells that share area with a Gemeinde
(82,381), for the two retained runs.

DWD's [Open Data FAQ](https://www.dwd.de/DE/leistungen/opendata/faqs_opendata.html)
states that DWD geodata may be reused under CC BY 4.0 with source attribution.
No separate, grid-file-specific license statement was located for
`icon_grid_0047_R19B07_L.nc.bz2`. This project therefore assumes that the grid,
which DWD distributes as supporting ICON model data, is covered by the same CC
BY 4.0 terms as the associated forecast geodata. That is an explicit project
assumption rather than a confirmed product-specific statement. Attribute the
source to Deutscher Wetterdienst and recheck the assumption before publicly
redistributing the grid file.

## DWD ICON-D2-RUC forecast fields

- Publisher: Deutscher Wetterdienst.
- Source root:
  `https://opendata.dwd.de/weather/nwp/v1/m/icon-d2-ruc/p`.
- Indicators: `T_2M`, `RELHUM_2M`, `U_10M`, and `V_10M`.
- Forecast identity: UTC model run plus lead time.
- File format: GRIB2.
- Availability: rolling publication and limited upstream retention.

The pipeline computes wind speed from its two horizontal components and uses
temperature, humidity, and wind to calculate shade apparent temperature.
Solar radiation is not included, so this measure is not presented as a full
heat-stress assessment.

The project applies the DWD Open Data FAQ's general CC BY 4.0 geodata terms to
these forecast fields. Attribute the source to Deutscher Wetterdienst and
recheck the current DWD terms before redistributing raw forecast files.

## BKG VG250 administrative boundaries

- Publisher: Bundesamt für Kartographie und Geodäsie (BKG).
- Product: Verwaltungsgebiete 1:250 000, levels ("Ebenen"), GeoPackage,
  UTM32s (EPSG:25832).
- Vintage: **Stand 31.12.2022** (`aktualitaet.txt` in the archive).
- Source:
  `https://daten.gdz.bkg.bund.de/produkte/vg/vg250_ebenen_1231/2022/vg250_12-31.utm32s.gpkg.ebenen.zip`.
- Archive size: 72,214,199 bytes.
- Archive SHA-256:
  `4a4d9590cac21028c3f120172d1ab3b026ac0a8b202d0f168e1304383ae44e59`.
- Extracted GeoPackage (`DE_VG250.gpkg`) SHA-256, for information:
  `12f0a8d27b40ed116e67c881cadc69dba4c5c6ad635df751305d18d3e9141144`.
- Retrieval: `uv run --env-file .env python -m src.ingestion.static_sources --only vg250`
  (verifies size and checksum, refuses to overwrite a different local file).
- Loaded into: `raw.vg250`, one row per delivered feature, column `level`
  in `sta`, `lan`, `krs`, `gem`.
- License: Datenlizenz Deutschland – Namensnennung – Version 2.0
  (dl-de/by-2-0), as stated in the archive's
  `quellenvermerk_datenlizenz_deutschland.pdf`.
- Required attribution (BKG *Quellenvermerk*; link it to
  <https://www.bkg.bund.de> on web pages; this project modifies the data):

```text
© GeoBasis-DE / BKG 2022 (Daten verändert)
```

**Why 31.12.2022.** Zensus 2022 Gemeinde results use the territorial status
(*Gebietsstand*) of 15.05.2022. BKG publishes VG250 only for 01.01. and 31.12.
Comparing keys on 2026-11-09:

| VG250 vintage | Gemeinden (GF = 4) | Zensus keys missing in VG250 | VG250 keys missing in Zensus |
| --- | ---: | ---: | ---: |
| 01.01.2022 | 10,993 | 2 (Pinnow, Schwedt/Oder) | 209 |
| 31.12.2022 | 10,990 | 0 | 204, all *Gemeindefreies Gebiet* |

With 31.12.2022 every Zensus Gemeinde (12-digit ARS) has exactly one geometry.
The 204 unincorporated areas keep their geometry; their population is NULL,
never 0. Residual risk: boundary changes between 15.05. and 31.12.2022 that
kept all keys would not be detected by a key comparison.

**Geofactor.** The VG250 documentation (`dokumentation/vg250.pdf`, attribute
GF) defines 1 = water without structure, 2 = water with structure, 3 = land
without structure, 4 = land with structure, and states that each
administrative unit has exactly one GF = 4 record; filtering to GF = 4
removes the North Sea, Baltic Sea and Lake Constance parts. Raw keeps all
records; normalization filters to GF = 4.

| Level | Delivered features | GF = 4 |
| --- | ---: | ---: |
| Staat (`sta`) | 11 | 1 |
| Länder (`lan`) | 35 | 16 |
| Kreise (`krs`) | 430 | 400 |
| Gemeinden (`gem`) | 11,119 | 10,990 |

## Zensus 2022 population

- Publisher: Statistische Ämter des Bundes und der Länder.
- Database: Zensusdatenbank, <https://ergebnisse.zensus2022.de/>.
- Table: **1000A-1003** "Personen: Alter (5 Altersklassen)", statistic 1000A
  "Bevölkerung kompakt (Gebietsstand 15.05.2022)".
- Reference date (*Stichtag*): 2022-05-15. Gebietsstand: 15.05.2022.
- Measure used by the Germany layer: **total population** per region, the
  row without an age class. The five age classes (`ALTKL1`: under 18,
  18–29, 30–49, 50–64, 65 and older) are loaded into raw as delivered but are
  not served.
- Retrieval: Zensus REST API (`/api/rest/2020/data/tablefile`, format
  `ffcsv`), one request per regional variable. Each file also contains the
  Germany (`GEODL1`) rows.

| Regional variable | Level | Regions | Flat CSV SHA-256 |
| --- | --- | ---: | --- |
| `GEOBL1` | Länder | 16 | `83b6ea9532e74e4c27327e9d6544e4abd48923dc1ae11563225d6acd312674f3` |
| `GEOLK4` | Kreise (Stand 15.05.22) | 400 | `71946b5fcc69a3e29d5732e33231badd7a19a7922e7d9bc39efb82d2e868f35f` |
| `GEOGM4` | Gemeinden (Gebietsstand 15.05.2022) | 10,786 | `e3489be7b6c1d432f155788f9c64ea84e3f94e535891fa2582bbd81c5c681d4a` |

The zip wrapper returned by the API differs on every request (its file name
carries a timestamp); the contained CSV was byte-identical across repeated
downloads, so the checksum applies to the extracted CSV.

**Access.** The API needs a free personal token (register at the Zensus
database, then copy it from the dialog "Webservice-Schnittstelle (API)").
Set it as `ZENSUS2022_TOKEN` in `.env`:

```bash
uv run --env-file .env python -m src.ingestion.static_sources --only zensus
```

The token is sent only as an HTTP header. **The API echoes the token in plain
text in the `Username` field of its JSON responses**, so the acquisition code
redacts JSON bodies before they appear in errors, and never stores them. The
delivered table files contain no credentials. Never commit raw API responses.

- Loaded into: `raw.zensus2022_population`, all values kept as delivered text.
- License and attribution, as returned by the API's `Copyright` field and the
  table footer:

```text
© Statistische Ämter des Bundes und der Länder, Deutschland, 2026.
Lizenziert unter der Datenlizenz Deutschland - Namensnennung - Version 2.0
```

**Confidentiality method.** Zensus 2022 results are protected with the
**Cell Key Method**, a data-perturbing method ("stochastische Überlagerung").
Destatis states that, as a consequence, the values of a table row or column
do not necessarily add up to the published total, and that official
population counts of administrative units are published unchanged
([Destatis: Geheimhaltung mit der Cell-Key-Methode](https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus2022/Datenbank/geheimhaltung-cell-key-methode.html);
[Destatis: Zensus 2022 Geheimhaltung](https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Bevoelkerung/Zensus2022/Methoden/geheimhaltung.html)).
This is why the layer uses total population: the age breakdown is perturbed
(e.g. Gemeinde values for 65+ sum to 18,389,751 against a published Germany
value of 18,390,209), while total population is not. Observed on the loaded
files for total population:

| Comparison | Result |
| --- | --- |
| Σ Gemeinden per Kreis vs. published Kreis total | exact for all 400 Kreise |
| Σ Gemeinden, Σ Kreise, Σ Länder | 82,711,282 each |
| Published Germany (`GEODL1`) total | 82,719,540 (+8,258 vs. Σ Länder) |

The 8,258-person gap between the Germany total and the sum of the Länder is
in the source itself. Destatis' *Qualitätsbericht Zensus 2022* (20/11/2024,
<https://www.destatis.de/DE/Methoden/Qualitaet/Qualitaetsberichte/Bevoelkerung/zensus-2022.pdf>)
defines the population to include "die im Ausland tätigen Angehörigen der
Bundeswehr, der Polizeibehörden und des Auswärtigen Dienstes sowie deren dort
ansässige Familien" (section 1.1) and says register-based results contain them
"auf Bundesebene" (section 7.2). The report does not state their number; the
gap is consistent with this definition but not confirmed numerically. Check 3
(`source_totals`) expects exactly this difference for the pinned extracts.

**Sign "-".** 42 Gemeinde age-class counts (34 Gemeinden) are delivered as
`-`; no total-population count is. The sign legend in Destatis' Zensus 2022
`Regionaltabelle_Bevoelkerung.xlsx` defines "– = Genau Null oder auf Null
geändert" (exactly zero, or changed to zero). No legend was found for the
database table itself; the project applies this definition and keeps the
original sign in raw.

## BA Gemeindedaten (employment)

- Publisher: Statistik der Bundesagentur für Arbeit (BA), Nürnberg.
- Product 229: *Gemeindedaten der sozialversicherungspflichtig Beschäftigten
  nach Wohn- und Arbeitsort*; Deutschland, Länder, Regierungsbezirke, Kreise
  und Gemeinden. Yearly, reference date 30 June; the 2025 file was created on
  15 Jan 2026, the next is announced for 15 Jan 2027.
- Download, no login:
  `https://statistik.arbeitsagentur.de/Statistikdaten/Detail/<YYYYMM>/iiia6/beschaeftigung-sozbe-gemband/gemband-dlk-0-<YYYYMM>-xlsx.xlsx?__blob=publicationFile&v=1`
  (`<YYYYMM>` = year and month of the reference date, e.g. `202506`). A HEAD
  request answers 200 with an xlsx content type for a published vintage and
  404 otherwise.
- Pinned vintage 2025-06-30: 1,608,751 bytes, SHA-256
  `a89513bdd5bfa967f9b81b86910e2e5d04376f82ef56b4e86f2212922a5953ff`; sheet
  `Gemeindedaten` with 10,752 Gemeinde, 294 Kreis, 20 Regierungsbezirk and 16
  Land rows; sheet `Länder` with 16 Länder, the row "keine Angabe/keine
  Zuordnung möglich" and the Germany row.
- Columns (BA numbering): 1 employees by place of residence; 2–8 of which men,
  women, Germans, foreigners, under 20, 20 to under 25, 55 and older;
  9 employees at place of work; 10 place of residence equals place of work;
  11 commuters in; 12 commuters out; 13 establishments. Employees subject to
  social insurance only (no civil servants, self-employed or marginal jobs).
- Territorial status: that of the reference date. Gemeinde keys are 8-digit
  AGS; matched to `normalized.gemeinde.ags`. Against VG250 of 31 Dec 2022:
  4 BA Gemeinden without a VG250 key (07232503 Obergeckler, 14522275 Jahnatal,
  16061119 Uder, 16076094 Berga-Wünschendorf), 38 incorporated VG250 Gemeinden
  without a BA row (merged after 2022; listed in `src/ingestion/contract.py`),
  and 204 unincorporated areas without employees. Kreise: 400 of 400 match.
- Suppression (*Geheimhaltung*, BA *Erläuterungen*): values below 3 and
  values that would allow them to be recomputed are shown as `*`; for
  Gemeinden with fewer than three establishments or a dominant establishment
  all place-of-work values (columns 9–11) are deleted. Kreis and Land totals
  include the suppressed values. The 2025 file has 7,723 `*` cells, all in
  Gemeinde rows.
- Commuters: persons whose place of residence or of work is unknown are not
  counted as commuters. The BA explains that employees reported under the
  establishment number of a head office are counted at the head office's
  Gemeinde ("Klumpungen"), so place-of-work counts can be too high there and
  too low at branch locations.
- Loaded into: `raw.ba_gemeindedaten` (values as delivered text), then
  `normalized.indicator_value` (ADR 019).
- Terms of use (imprint of the file): "Daten und Tabellen dürfen uneingeschränkt
  verwendet werden. Informationen dürfen (auch auszugsweise) gespeichert und mit
  Quellenangabe weitergegeben, vervielfältigt und verbreitet werden. Die Inhalte
  dürfen nicht verändert oder verfälscht werden. Eigene Berechnungen sind
  erlaubt, jedoch als solche kenntlich zu machen. Im Fall einer Veröffentlichung
  im Internet soll dies mit einer Verlinkung auf die Homepage der Statistik der
  Bundesagentur für Arbeit erfolgen."
- Citation (*Zitierhinweis*):

```text
Statistik der Bundesagentur für Arbeit, Tabellen, Gemeindedaten der
sozialversicherungspflichtig Beschäftigten nach Wohn- und Arbeitsort,
Nürnberg, Stichtag: 30.6.2025
```

## BA sector data (Regionalreport and WZ booklets)

Two quarterly products of the Statistik der Bundesagentur für Arbeit, both
employees subject to social insurance at place of work, both without login
(ADR 020). Terms of use and suppression as for the Gemeindedaten above.

**Regionalreport über Beschäftigte (Quartalszahlen)**, product 709, one xlsx
per Kreis:
`https://statistik.arbeitsagentur.de/Statistikdaten/Detail/<YYYYMM>/iiia6/beschaeftigung-reg-bst-reg/bst-reg-<Kreis key>-0-<YYYYMM>-xlsx.xlsx?__blob=publicationFile&v=1`.
The pattern works for Landkreise, kreisfreie Städte, Berlin (11000) and
Hamburg (02000). Each file holds five quarters (the reference quarter and the
four before it). Used: table 2.3 (WZ 2008 sections plus three manufacturing
groups and the sectors A, B–F, G–U) and table 2.1 (totals of the Kreis, its
Land, West or East Germany and Germany; also a block "am Wohnort", which
confirms that the other blocks count place of work). Not loaded: the share
and change columns (derivable) and the other tables. The 31 Mar 2026 files
were created on 10 Oct 2026; the next quarter is announced for 10 Jan 2027.
The three manufacturing groups:

| Group in table 2.3 | WZ 2008 divisions |
| --- | --- |
| Herstellung von überwiegend häuslich konsumierten Gütern | 10–15, 18, 21, 31 |
| Metall- und Elektroindustrie sowie Stahlindustrie | 24–30, 32, 33 |
| Herstellung von Vorleistungsgütern, insbesondere von chemischen Erzeugnissen und Kunststoffwaren | 16, 17, 19, 20, 22, 23 |

**Beschäftigte nach Wirtschaftszweigen (WZ 2008) (Quartalszahlen)**, one xlsx
per Land (`01`–`16`) and for Germany (`d`):
`https://statistik.arbeitsagentur.de/Statistikdaten/Detail/<YYYYMM>/iiia6/beschaeftigung-sozbe-wz-heft/wz-heft-<LL>-0-<YYYYMM>-xlsx.xlsx?__blob=publicationFile&v=1`.
Used: sheet "SVB - Tabelle I", column 1 (Insgesamt) of the total, the 88
divisions, group 241 (Erzeugung von Roheisen, Stahl und Ferrolegierungen) and
"XX Keine Angabe"; the other columns (sex, nationality, age, apprentices)
and the 3-digit groups stay in raw. One quarter per file; the booklets of the
same quarter a year earlier are loaded for the year-on-year change.

- Loaded into: `raw.ba_regionalreport` and `raw.ba_wz_heft` (values as
  delivered text, `*` kept), then `normalized.indicator_value`.
- Citations (*Zitierhinweis*, per file): "Statistik der Bundesagentur für
  Arbeit, Tabellen, Regionalreport über Beschäftigte (Quartalszahlen),
  <service centre>, <month>" and "Statistik der Bundesagentur für Arbeit,
  Tabellen, Beschäftigte nach Wirtschaftszweigen (WZ 2008)
  (Quartalszahlen)".

## Combined attribution

When presenting the data or the map, a concise attribution can read:

```text
Forecast: Deutscher Wetterdienst (DWD), ICON-D2-RUC, CC BY 4.0.

Administrative boundaries: © GeoBasis-DE / BKG 2022 (Daten verändert),
dl-de/by-2-0.

Population: Zensus 2022, © Statistische Ämter des Bundes und der Länder,
Deutschland, 2026, dl-de/by-2-0.

Employment and sectors: Statistik der Bundesagentur für Arbeit
(https://statistik.arbeitsagentur.de/); ratios, shares and Land sums of
groups are own calculations.

Spatial aggregation and roll-ups were produced by this project and are not
original source publications.
```
