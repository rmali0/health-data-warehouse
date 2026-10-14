"""Build the SQLite warehouse from the validated tables."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .transform import WIDE_KEY, wide_column_name

TABLES = (
    "cdc_indicators",
    "cdc_raw_clean",
    "indicator_catalog",
    "fda_drug_labels",
    "clinical_encounters",
    "etl_runs",
)


def wide_table_ddl(catalog: pd.DataFrame) -> str:
    """CREATE TABLE statement for the panel, one REAL column per catalog indicator."""
    cols = [
        "    location_abbr TEXT NOT NULL",
        "    location_desc TEXT NOT NULL",
        "    year_start INTEGER NOT NULL",
        "    year_end INTEGER NOT NULL",
    ]
    cols += [f"    {wide_column_name(c)} REAL" for c in catalog["wide_column"]]
    cols.append("    PRIMARY KEY (location_abbr, year_start, year_end)")
    return "CREATE TABLE cdc_indicators (\n" + ",\n".join(cols) + "\n);"


def _to_sql_values(df: pd.DataFrame) -> list[tuple]:
    """Convert a frame to plain Python tuples that sqlite3 can bind."""
    out = df.copy()
    for col in out.columns:
        series = out[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            out[col] = series.dt.strftime("%Y-%m-%d")
        elif pd.api.types.is_bool_dtype(series):
            out[col] = series.astype(int)
    out = out.astype(object).where(out.notna(), None)
    return [tuple(v.item() if hasattr(v, "item") else v for v in row) for row in out.itertuples(index=False)]


def insert_frame(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    columns = ", ".join(df.columns)
    placeholders = ", ".join("?" for _ in df.columns)
    rows = _to_sql_values(df)
    conn.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", rows)
    return len(rows)


@dataclass(frozen=True)
class WarehouseTables:
    long: pd.DataFrame
    wide: pd.DataFrame
    catalog: pd.DataFrame
    fda: pd.DataFrame
    encounters: pd.DataFrame
    run: dict


def build_warehouse(db_path: Path, schema_sql: Path, tables: WarehouseTables) -> dict[str, int]:
    """Create the database from scratch and load every table in one transaction."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (db_path, db_path.with_name(db_path.name + "-journal")):
        stale.unlink(missing_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(schema_sql.read_text(encoding="utf-8"))
        conn.execute(wide_table_ddl(tables.catalog))
        wide_cols = [*WIDE_KEY, *tables.catalog["wide_column"]]
        with conn:
            insert_frame(conn, "indicator_catalog", tables.catalog)
            insert_frame(conn, "cdc_raw_clean", tables.long)
            insert_frame(conn, "cdc_indicators", tables.wide[wide_cols])
            insert_frame(conn, "fda_drug_labels", tables.fda)
            insert_frame(conn, "clinical_encounters", tables.encounters)
            insert_frame(conn, "etl_runs", pd.DataFrame([tables.run]))
        return table_counts(conn)
    finally:
        conn.close()


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


def split_sql_file(text: str) -> list[tuple[str, str]]:
    """Split a SQL file into (title, statement) pairs.

    A statement's title comes from the most recent "-- name: ..." comment.
    """
    queries, buffer, title = [], [], ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("-- name:"):
            title = stripped.split(":", 1)[1].strip()
            continue
        if not buffer and (not stripped or stripped.startswith("--")):
            continue
        buffer.append(line)
        statement = "\n".join(buffer)
        if sqlite3.complete_statement(statement):
            queries.append((title, statement.strip()))
            buffer, title = [], ""
    return queries


def run_queries(db_path: Path, sql_path: Path) -> list[tuple[str, str, pd.DataFrame]]:
    """Run every statement in a SQL file and return (title, sql, result) triples."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return [
            (title, sql, pd.read_sql_query(sql, conn))
            for title, sql in split_sql_file(sql_path.read_text(encoding="utf-8"))
        ]
    finally:
        conn.close()
