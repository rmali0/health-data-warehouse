"""Column normalization and explicit typing for each source."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Columns of the long CDC table, in warehouse order. Anything else in the raw
# file is dropped and reported (in the current release those columns are
# entirely empty: Response, the second and third stratification levels, and
# their IDs).
CDC_LONG_COLUMNS = (
    "year_start",
    "year_end",
    "location_abbr",
    "location_desc",
    "location_id",
    "data_source",
    "topic_id",
    "topic",
    "question_id",
    "question",
    "data_value_type_id",
    "data_value_type",
    "data_value_unit",
    "data_value",
    "low_confidence_limit",
    "high_confidence_limit",
    "data_value_footnote_symbol",
    "data_value_footnote",
    "stratification_category_id1",
    "stratification_category1",
    "stratification_id1",
    "stratification1",
    "geolocation",
)

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM = re.compile(r"[^0-9a-zA-Z]+")


def to_snake_case(name: str) -> str:
    """Convert a column name to snake_case.

    Handles CamelCase as well as spaces and punctuation, so "LocationAbbr"
    becomes "location_abbr", "TopicID" becomes "topic_id" and
    "openfda.brand_name" becomes "openfda_brand_name".
    """
    name = str(name).strip()
    name = _ACRONYM_BOUNDARY.sub("_", name)
    name = _CAMEL_BOUNDARY.sub("_", name)
    name = _NON_ALNUM.sub("_", name)
    return name.strip("_").lower()


def snake_columns(df: pd.DataFrame) -> pd.DataFrame:
    renamed = [to_snake_case(c) for c in df.columns]
    if len(set(renamed)) != len(renamed):
        dupes = sorted({c for c in renamed if renamed.count(c) > 1})
        raise ValueError(f"snake_case renaming produced duplicate columns: {dupes}")
    return df.set_axis(renamed, axis=1)


def parse_number(values: pd.Series) -> pd.Series:
    """Parse numeric text, accepting thousands separators ("9,537" -> 9537.0)."""
    text = values.astype("string").str.strip().str.replace(",", "", regex=False)
    return pd.to_numeric(text, errors="coerce").astype("float64")


def repair_mojibake(text: str) -> str:
    """Undo UTF-8 text that was decoded as Windows-1252 somewhere upstream.

    The CDC release has question text such as "aged 18\u00e2\u20ac\u201c64": an en dash
    whose UTF-8 bytes were read as cp1252. Re-encoding recovers the dash, which is
    then written as a plain hyphen to match the rest of the question text.
    """
    if "\u00e2\u20ac" not in text:
        return text
    try:
        text = text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return text.replace("\u2013", "-").replace("\u2014", "-")


def _strip_text(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object or pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].astype("string").str.strip().replace("", pd.NA).astype(object)
    return out


@dataclass
class CleanLog:
    """Facts about what cleaning did, for the quality report."""

    dropped_columns: dict[str, int] = field(default_factory=dict)
    values_with_thousands_separator: int = 0
    mojibake_cells_repaired: int = 0
    unparseable_values: int = 0


def clean_cdc(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleanLog]:
    log = CleanLog()
    df = _strip_text(snake_columns(raw))

    for col in ("topic", "question", "data_value_footnote"):
        bad = df[col].astype("string").str.contains("\u00e2\u20ac", regex=False).fillna(False)
        log.mojibake_cells_repaired += int(bad.sum())
        df.loc[bad, col] = df.loc[bad, col].map(repair_mojibake)

    text_value = df["data_value_alt"]
    log.values_with_thousands_separator = int(
        text_value.astype("string").str.contains(",", regex=False).fillna(False).sum()
    )
    df["data_value"] = parse_number(text_value)
    log.unparseable_values = int((text_value.notna() & df["data_value"].isna()).sum())

    for col in ("low_confidence_limit", "high_confidence_limit"):
        df[col] = parse_number(df[col])
    for col in ("year_start", "year_end", "location_id"):
        df[col] = parse_number(df[col]).astype("Int64")

    keep = list(CDC_LONG_COLUMNS)
    # DataValue (display text) and DataValueAlt (numeric text) are replaced by
    # the single parsed data_value column.
    dropped = [c for c in df.columns if c not in keep and c not in ("data_value_alt",)]
    log.dropped_columns = {c: int(df[c].notna().sum()) for c in dropped}
    return df[keep].reset_index(drop=True), log


FDA_TEXT_SECTIONS = (
    "purpose",
    "indications_and_usage",
    "warnings",
    "dosage_and_administration",
    "active_ingredient",
    "inactive_ingredient",
)
FDA_OPENFDA_FIELDS = ("brand_name", "generic_name", "manufacturer_name", "product_type", "route")


def _join_list(value: object, sep: str) -> object:
    if isinstance(value, (list, tuple, np.ndarray)):
        return sep.join(str(v) for v in value)
    return value


def clean_fda(records: list[dict]) -> pd.DataFrame:
    """Build the curated label table: identifiers, key sections and the raw JSON.

    openFDA returns most fields as lists of strings; label sections are joined
    with blank lines and openfda metadata lists with "; ". The full record is
    kept as JSON so nothing is lost when a label has extra sections.
    """
    rows = []
    for rec in records:
        meta = rec.get("openfda", {}) or {}
        row = {
            "id": rec.get("id"),
            "set_id": rec.get("set_id"),
            "effective_time": rec.get("effective_time"),
            "version": rec.get("version"),
        }
        for f in FDA_OPENFDA_FIELDS:
            row[f] = _join_list(meta.get(f), "; ")
        for s in FDA_TEXT_SECTIONS:
            row[s] = _join_list(rec.get(s), "\n\n")
        row["n_sections"] = sum(1 for k, v in rec.items() if k != "openfda" and isinstance(v, list))
        row["raw_json"] = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        rows.append(row)
    df = pd.DataFrame(rows)
    df["effective_time"] = pd.to_datetime(df["effective_time"], format="%Y%m%d", errors="coerce")
    return df


def clean_encounters(raw: pd.DataFrame) -> pd.DataFrame:
    df = _strip_text(snake_columns(raw))
    df["encounter_date"] = pd.to_datetime(df["encounter_date"], format="%Y-%m-%d", errors="coerce")
    df["diagnosis_code"] = df["diagnosis_code"].astype("string").str.upper().astype(object)
    return df
