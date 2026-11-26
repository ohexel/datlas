FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.33 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/datlas-venv \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/datlas-venv/bin:${PATH}"

# tippecanoe builds the map's boundary tiles once per geography version.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 tippecanoe \
    && rm -rf /var/lib/apt/lists/* \
    && tippecanoe --version

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --frozen --no-install-project --no-dev \
    && python -c 'import dagster, dagster_webserver, psycopg' \
    && python -c 'import eccodes' \
    && python -c 'import geopandas' \
    && python -c 'import netCDF4'
