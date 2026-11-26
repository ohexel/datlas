"""The schema chain builds the whole database from nothing, twice.

A throwaway database (from template0, so without PostGIS) receives every
schema file in the order the code applies them, then all of them again.
It must then hold exactly the tables, views, functions and indexes the
files create: nothing missing, nothing left over from elsewhere.
"""

import re
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from src.database.connection import DatabaseSettings, database_connection
from src.database.forecast import apply_forecast_schema
from src.ingestion.ba_sectors import apply_sector_schema


pytestmark = pytest.mark.integration

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SCHEMAS = ("raw", "normalized", "analytical")
CREATED = re.compile(
    r"^\s*CREATE (?:OR REPLACE )?(TABLE IF NOT EXISTS|VIEW|FUNCTION|INDEX IF NOT EXISTS)"
    r" (?:(\w+)\.)?(\w+)",
    re.MULTILINE,
)


def _declared() -> dict[str, set[str]]:
    declared: dict[str, set[str]] = {"relation": set(), "function": set(), "index": set()}
    for path in SQL_DIR.glob("*.sql"):
        for kind, schema, name in CREATED.findall(path.read_text(encoding="utf-8")):
            if kind.startswith("INDEX"):
                declared["index"].add(name)
            elif kind == "FUNCTION":
                declared["function"].add(f"{schema}.{name}")
            else:
                declared["relation"].add(f"{schema}.{name}")
    return declared


def _installed(connection: psycopg.Connection) -> dict[str, set[str]]:
    def names(sql: str) -> set[str]:
        return {row[0] for row in connection.execute(sql, (list(SCHEMAS),))}

    return {
        "relation": names(
            """
            SELECT n.nspname || '.' || c.relname
            FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(%s) AND c.relkind IN ('r', 'v', 'm', 'p')
            """
        ),
        "function": names(
            """
            SELECT n.nspname || '.' || p.proname
            FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = ANY(%s)
            """
        ),
        # Indexes created by name, not those behind primary keys or unique constraints.
        "index": names(
            """
            SELECT c.relname
            FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(%s) AND c.relkind = 'i'
              AND c.oid NOT IN (SELECT conindid FROM pg_constraint)
            """
        ),
    }


def test_schema_files_build_the_database_from_empty_twice() -> None:
    settings = DatabaseSettings.from_env()
    scratch = f"datlas_schema_test_{uuid4().hex[:8]}"
    admin = dict(
        host=settings.host, port=settings.port, dbname=settings.database,
        user=settings.user, password=settings.password, autocommit=True,
    )
    declared = _declared()
    assert len(declared["relation"]) == 39 and len(declared["function"]) == 24

    with psycopg.connect(**admin) as connection:
        connection.execute(f'CREATE DATABASE "{scratch}" TEMPLATE template0')
    try:
        target = replace(settings, database=scratch)
        for _ in range(2):
            with database_connection(target, application_name="datlas_schema_test") as connection:
                apply_sector_schema(connection)   # base, raw, normalized, indicator, sector
                apply_forecast_schema(connection)
        with database_connection(target, application_name="datlas_schema_test") as connection:
            installed = _installed(connection)
            postgis = connection.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'postgis'"
            ).fetchone()
    finally:
        with psycopg.connect(**admin) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)')

    assert postgis is not None
    assert installed == declared
