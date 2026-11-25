"""The database container keeps its names and port apart from other
PostGIS installations on the same machine."""

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.contract
def test_compose_files_use_their_own_project_name_and_port() -> None:
    postgres = (PROJECT_ROOT / "docker" / "postgres.yml").read_text()
    dagster = (PROJECT_ROOT / "docker" / "dagster.yml").read_text()

    # Without a project name, Compose names the project after the folder
    # of the first file ("docker"), which other projects share.
    for compose_file in (postgres, dagster):
        assert compose_file.startswith("name: ${COMPOSE_PROJECT_NAME:-datlas}\n")
    assert "container_name: ${POSTGRES_CONTAINER_NAME:-datlas_postgres}" in postgres
    assert '"${POSTGRES_PORT:-5433}:5432"' in postgres
