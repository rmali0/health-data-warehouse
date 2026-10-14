"""Reshape the long CDC table into a location-period panel with one column per indicator."""

from __future__ import annotations

import re

import pandas as pd

OVERALL = "OVERALL"
WIDE_KEY = ("location_abbr", "location_desc", "year_start", "year_end")

# Each indicator is published in several value types (crude and age-adjusted
# prevalence, counts, rates). A panel cell must hold one of them, so for each
# indicator the first available type in this list is used. Age-adjusted
# measures come first because the panel is mainly for comparing states with
# different age structures.
VALUE_TYPE_PREFERENCE = (
    "AGEADJPREV",
    "AGEADJRATE",
    "AGESEXRACEADJRATE",
    "AGEADJMEAN",
    "CRDPREV",
    "CRDRATE",
    "CRDMEAN",
    "CRDMEDN",
    "PROP",
    "PERCAPALC",
    "CRD75TH",
    "NMBR",
)

_SQL_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def wide_column_name(question_id: str) -> str:
    name = str(question_id).strip().lower()
    if not _SQL_IDENTIFIER.match(name):
        raise ValueError(f"question_id {question_id!r} does not make a safe SQL column name")
    return name


def _rank(type_id: str) -> tuple[int, str]:
    if type_id in VALUE_TYPE_PREFERENCE:
        return (VALUE_TYPE_PREFERENCE.index(type_id), type_id)
    return (len(VALUE_TYPE_PREFERENCE), type_id)


def overall_with_values(df: pd.DataFrame) -> pd.DataFrame:
    mask = (df["stratification_category_id1"] == OVERALL) & df["data_value"].notna()
    return df.loc[mask]


def choose_value_types(df: pd.DataFrame) -> pd.Series:
    """Map each question_id to the value type the panel will use."""
    available = overall_with_values(df).groupby("question_id")["data_value_type_id"].unique()
    return available.map(lambda types: min(types, key=_rank)).rename("data_value_type_id")


def build_indicator_catalog(df: pd.DataFrame) -> pd.DataFrame:
    """One row per indicator: its text, chosen value type, unit and coverage."""
    chosen = choose_value_types(df).reset_index()
    rows = overall_with_values(df).merge(chosen, on=["question_id", "data_value_type_id"])
    catalog = rows.groupby("question_id", sort=True).agg(
        topic_id=("topic_id", "first"),
        topic=("topic", "first"),
        question=("question", "first"),
        data_source=("data_source", lambda s: "; ".join(sorted(s.dropna().unique()))),
        data_value_type_id=("data_value_type_id", "first"),
        data_value_type=("data_value_type", "first"),
        data_value_unit=("data_value_unit", "first"),
        n_locations=("location_abbr", "nunique"),
        first_year=("year_start", "min"),
        last_year=("year_end", "max"),
    )
    catalog = catalog.reset_index()
    catalog.insert(1, "wide_column", catalog["question_id"].map(wide_column_name))
    return catalog.sort_values(["topic", "question_id"]).reset_index(drop=True)


def build_wide_panel(df: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Pivot overall estimates to one row per location and period.

    Columns are named by question_id (lower case) rather than by truncated
    question text. Truncating to 50 characters, as the course version did,
    can give two indicators the same name and pivot_table would then average
    them into one column without warning.
    """
    sel = overall_with_values(df).merge(
        catalog[["question_id", "data_value_type_id", "wide_column"]],
        on=["question_id", "data_value_type_id"],
    )
    cell_key = [*WIDE_KEY, "wide_column"]
    clashes = int(sel.duplicated(subset=cell_key).sum())
    if clashes:
        raise ValueError(f"{clashes} panel cells have more than one value; check the natural key")

    wide = sel.pivot(index=list(WIDE_KEY), columns="wide_column", values="data_value")
    wide = wide.reindex(columns=list(catalog["wide_column"])).reset_index()
    wide.columns.name = None
    for col in ("year_start", "year_end"):
        wide[col] = wide[col].astype("Int64")
    return wide.sort_values(["location_abbr", "year_start", "year_end"]).reset_index(drop=True)


def indicator_columns(wide: pd.DataFrame) -> list[str]:
    return [c for c in wide.columns if c not in WIDE_KEY]
