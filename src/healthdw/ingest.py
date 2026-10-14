"""Read the three source formats (CSV, JSON, HTML) into DataFrames.

Each reader checks that the columns the rest of the pipeline depends on are
present, so a changed upstream file fails here with a clear message instead of
surfacing later as a KeyError in the middle of a transform.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

CDC_REQUIRED_COLUMNS = (
    "YearStart",
    "YearEnd",
    "LocationAbbr",
    "LocationDesc",
    "DataSource",
    "Topic",
    "TopicID",
    "Question",
    "QuestionID",
    "DataValueUnit",
    "DataValueType",
    "DataValueTypeID",
    "DataValueAlt",
    "StratificationCategory1",
    "StratificationCategoryID1",
    "Stratification1",
    "StratificationID1",
)

ENCOUNTER_REQUIRED_COLUMNS = ("EncounterID", "PatientID", "EncounterDate")


class SchemaError(ValueError):
    """A source file is missing columns the pipeline needs."""


class SourceMissingError(FileNotFoundError):
    """A source file is not where the pipeline expects it."""


@dataclass(frozen=True)
class SourceInfo:
    name: str
    path: Path
    sha256: str
    rows: int
    columns: int


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def require_columns(df: pd.DataFrame, required: tuple[str, ...], source: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SchemaError(f"{source} is missing expected columns: {', '.join(missing)}")


def _require_file(path: Path, hint: str) -> None:
    if not path.exists():
        raise SourceMissingError(f"{path} not found. {hint}")


def read_cdc(path: Path) -> pd.DataFrame:
    """Read the CDC Chronic Disease Indicators export as text.

    Everything is read as a string and typed explicitly in clean.py. Letting
    pandas infer types is what hid the original bug: values such as "9,537"
    made the whole column text, and a later to_numeric(errors="coerce")
    silently turned them into missing values.
    """
    _require_file(
        path,
        "Run `python scripts/download_cdc_cdi.py`, or use `--sample` for the bundled fixture.",
    )
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    if df.empty:
        raise SchemaError(f"{path.name} has no rows")
    require_columns(df, CDC_REQUIRED_COLUMNS, path.name)
    return df


def read_fda_labels(path: Path) -> tuple[pd.DataFrame, list[dict]]:
    """Read an openFDA drug label API response.

    Returns the flattened table and the raw records, which are kept so the
    warehouse can store each label's full JSON alongside the curated columns.
    """
    _require_file(path, "Run `python scripts/fetch_openfda_labels.py` to fetch labels.")
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    records = payload.get("results")
    if not records:
        raise SchemaError(f"{path.name} has no 'results' records")
    return pd.json_normalize(records), records


def read_encounters_html(path: Path) -> pd.DataFrame:
    """Parse the first HTML table in the (simulated) encounter report."""
    _require_file(path, "The simulated encounter file ships with the repository.")
    tables = pd.read_html(path, flavor="lxml")
    if not tables:
        raise SchemaError(f"{path.name} contains no HTML table")
    # "string" keeps empty cells as missing; astype(str) would turn them into "nan".
    df = tables[0].astype("string")
    if df.empty:
        raise SchemaError(f"{path.name} table has no rows")
    require_columns(df, ENCOUNTER_REQUIRED_COLUMNS, path.name)
    return df


def describe_source(name: str, path: Path, df: pd.DataFrame) -> SourceInfo:
    return SourceInfo(name=name, path=path, sha256=sha256_of(path), rows=len(df), columns=df.shape[1])
