"""The Docker set-up keeps datlas apart from other installations on the same
machine and keeps the source data out of the image build."""

from pathlib import Path

import pytest


DOCKER = Path(__file__).resolve().parents[1] / "docker"


@pytest.mark.contract
def test_docker_setup_has_its_own_names_and_a_small_build_context() -> None:
    postgres = (DOCKER / "postgres.yml").read_text()
    dagster = (DOCKER / "dagster.yml").read_text()

    # Without a project name, Compose names the project after the folder of
    # the first file ("docker"), so `down` in one checkout would stop the
    # containers of another project that has a docker/ folder too.
    for compose_file in (postgres, dagster):
        assert compose_file.startswith("name: ${COMPOSE_PROJECT_NAME:-datlas}\n")
    assert "container_name: ${POSTGRES_CONTAINER_NAME:-datlas_postgres}" in postgres
    assert '"${POSTGRES_PORT:-5433}:5432"' in postgres
    # Dagster reaches the database of the same Compose project.
    assert "POSTGRES_HOST: postgres" in dagster
    assert "condition: service_healthy" in dagster

    # The build context holds only the lock files, never data/ (gigabytes).
    patterns = {
        line.strip()
        for line in (DOCKER / "dagster.dockerfile.dockerignore").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "**" in patterns
    assert not any(pattern.startswith("!data") for pattern in patterns)
