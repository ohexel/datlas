# Runbook

Install, operate, inspect and reset datlas. What the pipeline does, its checks
and the map are described in [pipeline.md](pipeline.md); measured numbers are
in [facts.md](facts.md).

## Requirements

- Docker Engine and the Docker Compose plugin.
- `uv` and Python 3.11, for the command-line runners and the tests.
- Network access to Python packages, the PostGIS image, the DWD Open Data
  server, BKG, the Zensus database and the BA statistics portal.
- A free Zensus 2022 API token (`ZENSUS2022_TOKEN`), only while the Zensus
  files are not yet under `data/raw/germany/`.
- `tippecanoe`, once per geography version, to build the map's boundary tiles
  (the Dagster image has it).
- Disk: about 1.1 GB for the database with one forecast run (two runs add
  about 230 MB), 200 MB for the ICON grid file, about 80 MB of GRIB files per
  retained run, and about 250 MB of BA files per quarter.

## Install

```bash
git clone https://github.com/ohexel/datlas.git
cd datlas
cp .env.example .env              # set POSTGRES_PASSWORD, DAGSTER_UID/GID; ZENSUS2022_TOKEN if needed
uv sync --frozen
docker compose --env-file .env -f docker/postgres.yml up -d
```

The database runs in the container `datlas_postgres`, published on
`127.0.0.1:5433`, in the Compose project `datlas`. These names keep datlas
apart from other PostGIS installations on the same machine (see
[A second installation](#a-second-installation)).

There is no separate schema step: every job applies the idempotent files in
`sql/` first, starting with `sql/base_schema.sql`.

## Start Dagster

In a container (recommended), with the interface, the daemon that runs the
sensors, and the run limits of `docker/dagster.yaml`:

```bash
docker compose --env-file .env -f docker/postgres.yml -f docker/dagster.yml up -d --build
```

The container runs as `DAGSTER_UID`:`DAGSTER_GID` from `.env`, which must be
your user and group (`id -u`, `id -g`): it writes its run storage to
`.dagster_home/` and the map files to `web/` in the checkout.

The interface is at <http://127.0.0.1:3001> (`DAGSTER_PORT`). The container
mounts the checkout at `/app`, so it shares the code, `data/`, `web/` and
`.dagster_home/` with commands run on the host; it reaches the database as
`postgres:5432`. The first start builds an image with the locked dependencies
from `uv.lock` and `tippecanoe`. CPU and memory are limited to 3 cores and
10 GiB (`DAGSTER_CPUS`, `DAGSTER_MEMORY_LIMIT`).

Or on the host:

```bash
export DAGSTER_HOME="$PWD/.dagster_home"
mkdir -p "$DAGSTER_HOME" && cp docker/dagster.yaml "$DAGSTER_HOME/"
uv run --env-file .env dagster dev -m src.dagster_pipeline.definitions
```

Run only one of the two: two Dagster daemons on the same `.dagster_home`
would process every sensor twice.

`docker/dagster.yaml` allows two runs at a time and stops a run after 300 s;
the jobs `static`, `employment` and `sectors` carry their own limit of 30
minutes (tag `dagster/max_runtime`).

## First build

On an empty database, in this order (by hand on the host, or as the jobs of
the same names in the Dagster interface):

```bash
# ICON grid (downloaded once, 201 MB) and its cells, VG250, Zensus,
# hierarchy, population, bridge; about 4 minutes
uv run --env-file .env python -m src.run_static

# employment: one BA Gemeindedaten vintage (newest known: 2025-06-30)
uv run --env-file .env python -m src.run_employment

# sectors: one quarter of the two BA products (newest known: 2026-03-31);
# 434 files one at a time, about 22 minutes when nothing is on disk yet
uv run --env-file .env python -m src.run_sectors
```

Each command prints its checks; all must pass. `run_static` is safe to repeat:
a geography version that already exists from the same VG250 file is left
unchanged, a different file is refused; population and the bridge are
rebuilt. `run_employment` and `run_sectors` replace the raw rows and values of
their reference date.

Then switch on the forecast in the Dagster interface (Automation): first
`forecast_publish_sensor`, then `dwd_forecast_availability_sensor`. The first
complete run is published about 15 to 30 minutes after DWD has published all
its lead times.

## Sensors

All four sensors start stopped. Switched on, they stay on across restarts
(Dagster keeps their state in `.dagster_home`).

| Sensor | Starts | Behaviour |
| --- | --- | --- |
| `dwd_forecast_availability_sensor` | `forecast` | every five minutes from :30 to :59 of each hour: HEAD requests to DWD for the newest runs; starts at most ten partitions per check whose four fields are published, newest runs and lead times first; at most five attempts per partition |
| `forecast_publish_sensor` | `forecast_publish` | every minute: the newest run with all 25 lead times for every Gemeinde is published once (retention, checks 5–6, map export); up to five attempts |
| `ba_gemeindedaten_release_sensor` | `employment` | one HEAD request a day for the vintage after the newest one loaded |
| `ba_sectors_release_sensor` | `sectors` | two HEAD requests a day for the next quarter; respects the BA cool-down file |

## Forecast by hand

```bash
uv run --env-file .env python -m src.run_forecast \
  --run-time "$(date -u -d '3 hours ago' +%Y%m%dT%H00)"
```

Run labels are **UTC**; DWD keeps runs for about 24 hours, and the Dagster
partitions cover the same window. The runner processes the 25 lead times
(skipping those already complete), then publishes and exports the map. It
does not need the sensors; with the sensors on, a run the runner completes is
published again by the publish sensor, which is harmless.

## New BA data

```bash
uv run --env-file .env python -m src.run_employment --reference-date 2026-06-30
uv run --env-file .env python -m src.run_sectors --file-date 2026-06-30
```

The release sensors start the same jobs when the BA publishes. A vintage not
yet in the contract loads if its structure matches; its key-coverage check
(10) then fails until its territorial changes are reviewed and added to
`src/ingestion/contract.py`.

**When the BA throttles.** HTTP 429 is answered with waits of 1, 5 and 15
minutes (or the server's `Retry-After`); if it persists, a cool-down of at
least an hour is written to `data/raw/germany/ba_rate_limit.json`, which every
download and the sensor respect. `run_sectors` then stops with exit status 2
and says when to run it again; the next run continues with the missing files.
Avoid back-to-back full downloads from the same network. Files copied from
another checkout into `data/raw/germany/ba_regionalreport/` and
`data/raw/germany/ba_wz_heft/` under the same names are checked like downloads
and not requested again.

## Map

The publish job writes `web/germany-dashboard/data/` after every publish. By
hand, and with a local preview:

```bash
uv run --env-file .env python -m src.export_germany_dashboard --serve
# -> http://127.0.0.1:8766/
```

Options: `--rebuild-tiles` (build the boundary tiles again), `--output-dir`,
`--host`, `--port`. A theme whose data is not loaded is left out.

**Publishing** is outside the pipeline: copy `web/germany-dashboard/`,
including `data/`, to the web host, for example with a cron job on the host
that runs `rsync` after the publish job has written new files. The host must
answer HTTP Range requests for the `.pmtiles` file and serve the page from the
same origin as the tiles. After a new forecast run only `data/values.json`
changes. Browsers fetch the JSON files with `cache: "no-cache"`, so they get a
new file on the next page load.

## Inspect

Load the project environment into the current shell to use its variables:

```bash
set -a; source .env; set +a
psql() { docker compose --env-file .env -f docker/postgres.yml \
  exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"; }
```

The served forecast run:

```bash
psql -c "SELECT run_time_utc, gemeinde_count, lead_time_count, population_total
         FROM analytical.current_bund_summary;"
```

Expected: one row, 10,990 Gemeinden, 25 lead times and a population of
82,711,282 (the sum of the Länder; the published Germany total is 8,258
higher, see check 3 in [pipeline.md](pipeline.md#checks-and-thresholds)).

The 24-hour series of one Land, area- and population-weighted:

```bash
psql -c "SELECT lead_hour, valid_time_berlin,
                ROUND(apparent_temperature_shade_area_weighted_c::numeric, 1) AS area_c,
                ROUND(apparent_temperature_shade_population_weighted_c::numeric, 1) AS population_c
         FROM analytical.current_land_forecast_25h
         WHERE land_name = 'Bayern' ORDER BY lead_hour;"
```

Coverage of the employment and sector views:

```bash
psql -c "SELECT 'employment' AS theme, reference_date, level, COUNT(*) AS regions
         FROM analytical.current_employment GROUP BY reference_date, level
         UNION ALL
         SELECT 'sectors', reference_date, level, COUNT(*)
         FROM analytical.current_sectors GROUP BY reference_date, level
         ORDER BY 1, 3;"
```

Expected: employment `gem` 10,990, `krs` 400, `lan` 16, `sta` 1; sectors
`krs` 400, `lan` 16, `sta` 1. Values the BA suppresses or does not report are
rows with a `*_status` other than `value`, never missing rows.

All checks and the serving contracts on the installed data, read-only (about
45 s):

```bash
uv run --env-file .env python -m pytest -m acceptance
```

## Retention

- Database: the newest complete forecast run, the complete run before it, and
  a newer run while it is loading (`normalized.prune_forecast`).
- GRIB files under `data/raw/icon_d2_ruc/`: kept while their run is in the
  database or younger than `FORECAST_RETENTION_HOURS` (1–24, default 24).
- Both are applied by every publish. To see what would be deleted, or to
  delete it outside a publish:

  ```bash
  uv run --env-file .env python -m src.retention.grib_files           # report only
  uv run --env-file .env python -m src.retention.grib_files --apply
  ```

- BA, Zensus and VG250 files under `data/raw/germany/` and the grid file are
  kept. Notes about GRIB files that failed to decode are kept under
  `data/raw/quarantine/icon_d2_ruc/`.

## Failure handling

| Symptom | Meaning | Action |
| --- | --- | --- |
| `run_static` reports `ZENSUS2022_TOKEN is not set` | The Zensus files are not on disk yet and no token is configured. | Set `ZENSUS2022_TOKEN` in `.env` (the Dagster container reads it from there too) and retry. |
| `run_static` refuses the VG250 file | A different file than the one the geography version was built from. | Keep the original file, or load the new one under a new `geography_version`. |
| ICON grid download fails | DWD unreachable; the reason is in `data/raw/icon_d2_grid/metadata.json`. | Retry later, or download it with `uv run python -m src.download_icon_d2_grid`. |
| Requested forecast run unavailable | Run is unpublished, incomplete, older than about 24 hours, or entered in local time. | Choose another UTC run. |
| A forecast partition fails to decode | A GRIB file is broken; a note is under `data/raw/quarantine/icon_d2_ruc/`. | The sensor retries up to five attempts; the views keep serving the previous complete run. |
| Check 5 (`forecast_completeness`) warns | A newer run was loaded but never completed, e.g. a failed download or a model field with missing values. | Nothing; the next complete run replaces it. |
| The Dagster container restarts in a loop | It runs as a user that cannot write `.dagster_home/` (wrong `DAGSTER_UID`/`DAGSTER_GID`, or the folder was created by Docker as root). | Set both in `.env` to `id -u` and `id -g`; if `.dagster_home` belongs to root, `sudo chown -R "$(id -u):$(id -g)" .dagster_home`; then `up -d` again. |
| Runs stay queued | Two runs at a time (`docker/dagster.yaml`); the sensor queues up to ten partitions per check. | Wait; each partition takes a few seconds. |
| `run_sectors` exits with status 2 | The BA throttled the downloads; a cool-down is in force. | Run the same command again after the time it prints. |
| Check 10 (`ba_key_coverage`) fails on a new vintage | The BA's territorial status changed. | Review the changes and add them to `src/ingestion/contract.py`. |
| A BA file is refused by its contract | The BA changed the file's layout. | Do not bypass the contract; adapt the parser and contract deliberately. |
| Tile build fails | `tippecanoe` is not installed (on the host). | Install it, or let the Dagster container export; later exports reuse the tiles. |

## Database lifecycle

Stop and start the database without losing data:

```bash
docker compose --env-file .env -f docker/postgres.yml stop
docker compose --env-file .env -f docker/postgres.yml up -d
```

Stop or start only Dagster:

```bash
docker compose --env-file .env -f docker/postgres.yml -f docker/dagster.yml stop dagster
docker compose --env-file .env -f docker/postgres.yml -f docker/dagster.yml up -d dagster
docker compose --env-file .env -f docker/postgres.yml -f docker/dagster.yml logs -f dagster
```

### Reset

`scripts/reset_database.sh` **deletes the Compose project's PostgreSQL volume
and all database state**, then starts an empty database. It asks for the
confirmation text `RESET`. Check first that `.env` selects the intended
Compose project. Afterwards run the [first build](#first-build) again; files
under `data/` are kept, so nothing is downloaded twice.

### A second installation

To run a second, isolated installation beside the first, give the second
checkout's `.env` its own names:

```dotenv
POSTGRES_PORT=55433
POSTGRES_CONTAINER_NAME=datlas_cleanroom_postgres
COMPOSE_PROJECT_NAME=datlas_cleanroom
DAGSTER_PORT=3002
```

Docker volumes, containers, ports and Dagster run history stay separate. Copy
the files under `data/raw/` rather than downloading them a second time from
the same network.

Tests: [testing.md](testing.md).
