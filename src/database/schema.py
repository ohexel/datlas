"""Apply the base schema: schemas, PostGIS, the ICON grid and shared
functions. Every other schema file builds on it."""

from pathlib import Path

from psycopg import Connection


BASE_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "base_schema.sql"


def apply_base_schema(connection: Connection) -> None:
    connection.execute(BASE_SCHEMA_PATH.read_text(encoding="utf-8"))
