"""Summary tables, the data dictionary and the generated data quality report."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from .figures import period_label
from .transform import WIDE_KEY, indicator_columns
from .validate import checks_to_frame

SUPPRESSION_PATTERN = r"suppress|too few"

COLUMN_DESCRIPTIONS = {
    "row_id": "Surrogate key assigned at load time.",
    "year_start": "First year of the reporting period.",
    "year_end": "Last year of the reporting period (equal to year_start for single-year estimates).",
    "location_abbr": "Two-letter state, territory or US code.",
    "location_desc": "Location name.",
    "location_id": "CDC numeric location identifier.",
    "data_source": "Survey or surveillance system behind the estimate (BRFSS, NVSS, YRBSS, ...).",
    "topic_id": "CDC topic code.",
    "topic": "Chronic disease topic.",
    "question_id": "CDC indicator code, e.g. DIA01.",
    "question": "Indicator definition.",
    "data_value_type_id": "Code for the kind of estimate (CRDPREV, AGEADJPREV, CRDRATE, NMBR, ...).",
    "data_value_type": "Kind of estimate, e.g. crude or age-adjusted prevalence.",
    "data_value_unit": "Unit of data_value (%, per 100,000, Number, ...).",
    "data_value": "Estimate, parsed from DataValueAlt with thousands separators removed. Missing when suppressed or not collected.",
    "low_confidence_limit": "Lower 95% confidence limit.",
    "high_confidence_limit": "Upper 95% confidence limit.",
    "data_value_footnote_symbol": "CDC footnote symbol.",
    "data_value_footnote": "CDC footnote text, including the reason a value is missing.",
    "stratification_category_id1": "Stratification dimension code (OVERALL, SEX, AGE, RACE, GRADE).",
    "stratification_category1": "Stratification dimension.",
    "stratification_id1": "Stratum code within the dimension.",
    "stratification1": "Stratum, e.g. Female or Hispanic.",
    "geolocation": "Location centroid as WKT POINT text.",
    "is_outlier_iqr": "1 if the value is outside the 1.5 x IQR fences of other locations with the same indicator, value type, period and stratum (groups of 10 or more; US row excluded).",
    "z_score": "Standardized value within the same comparison group as is_outlier_iqr.",
    "is_outlier_z": "1 if |z_score| > 3.",
    "wide_column": "Column name of this indicator in cdc_indicators.",
    "n_locations": "Locations with an overall value of the chosen type.",
    "first_year": "Earliest year_start with a value.",
    "last_year": "Latest year_end with a value.",
    "id": "openFDA label document id.",
    "set_id": "Structured Product Labeling set id (stable across label versions).",
    "effective_time": "Label effective date.",
    "version": "Label version number.",
    "brand_name": "openfda.brand_name, joined with '; '.",
    "generic_name": "openfda.generic_name, joined with '; '.",
    "manufacturer_name": "openfda.manufacturer_name, joined with '; '.",
    "product_type": "openfda.product_type (e.g. HUMAN OTC DRUG).",
    "route": "openfda.route, joined with '; '.",
    "purpose": "Purpose section text.",
    "indications_and_usage": "Indications and usage section text.",
    "warnings": "Warnings section text.",
    "dosage_and_administration": "Dosage and administration section text.",
    "active_ingredient": "Active ingredient section text.",
    "inactive_ingredient": "Inactive ingredient section text.",
    "n_sections": "Number of label sections present in the record.",
    "raw_json": "Full openFDA record as JSON.",
    "encounter_id": "Encounter identifier (simulated).",
    "patient_id": "Patient identifier (simulated).",
    "encounter_date": "Encounter date.",
    "department": "Hospital department.",
    "diagnosis_code": "ICD-10-CM diagnosis code.",
    "provider": "Attending provider (placeholder name).",
}

TABLE_DESCRIPTIONS = {
    "cdc_raw_clean": "Long CDC table: every estimate for every stratum and value type.",
    "cdc_indicators": "Wide panel: one row per location and reporting period, one column per indicator (overall population).",
    "indicator_catalog": "One row per indicator, with the value type used in the wide panel.",
    "fda_drug_labels": "Curated openFDA drug label fields plus the raw record.",
    "clinical_encounters": "Simulated encounter records parsed from HTML.",
}


def markdown_table(df: pd.DataFrame, float_digits: int = 1) -> str:
    """Render a small frame as a GitHub markdown table (no tabulate dependency).

    Integers get thousands separators except in year columns.
    """

    def fmt(v: object, column: str) -> str:
        if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, float):
            return f"{v:,.{float_digits}f}"
        if isinstance(v, int) and not isinstance(v, bool):
            return str(v) if "year" in column else f"{v:,}"
        return str(v).replace("|", "\\|").replace("\n", " ")

    columns = [str(c) for c in df.columns]
    header = "| " + " | ".join(columns) + " |"
    rule = "|" + "|".join("---" for _ in columns) + "|"
    body = [
        "| " + " | ".join(fmt(v, c) for v, c in zip(row, columns, strict=True)) + " |"
        for row in df.astype(object).itertuples(index=False)
    ]
    return "\n".join([header, rule, *body])


def value_availability_by_topic(long: pd.DataFrame) -> pd.DataFrame:
    has_value = long["data_value"].notna()
    suppressed = ~has_value & long["data_value_footnote"].astype("string").str.contains(
        SUPPRESSION_PATTERN, case=False, regex=True
    ).fillna(False)
    frame = pd.DataFrame({"topic": long["topic"], "has_value": has_value, "suppressed": suppressed})
    out = frame.groupby("topic").agg(
        rows=("has_value", "size"), value_reported=("has_value", "sum"), suppressed=("suppressed", "sum")
    )
    out["not_available"] = out["rows"] - out["value_reported"] - out["suppressed"]
    for col in ("value_reported", "suppressed", "not_available"):
        out[f"pct_{col}"] = (100 * out[col] / out["rows"]).round(1)
    return out.reset_index().sort_values("pct_value_reported").reset_index(drop=True)


def panel_coverage(wide: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Share of filled location x indicator cells, by topic and reporting period."""
    rows = []
    periods = wide[["year_start", "year_end"]].drop_duplicates().sort_values(["year_start", "year_end"])
    for topic, cols in catalog.groupby("topic")["wide_column"]:
        for start, end in periods.itertuples(index=False):
            block = wide.loc[(wide["year_start"] == start) & (wide["year_end"] == end), list(cols)]
            cells = block.size
            rows.append(
                {
                    "topic": topic,
                    "period": period_label(int(start), int(end)),
                    "cells": cells,
                    "filled": int(block.notna().sum().sum()),
                    "pct_filled": round(100 * block.notna().sum().sum() / cells, 1) if cells else 0.0,
                }
            )
    return pd.DataFrame(rows)


def outliers_by_topic(long: pd.DataFrame) -> pd.DataFrame:
    with_value = long[long["data_value"].notna()]
    out = with_value.groupby("topic").agg(
        values=("data_value", "size"),
        iqr_flags=("is_outlier_iqr", "sum"),
        z_flags=("is_outlier_z", "sum"),
    )
    out["pct_iqr"] = (100 * out["iqr_flags"] / out["values"]).round(2)
    return out.reset_index().sort_values("pct_iqr", ascending=False).reset_index(drop=True)


def rows_by_stratification(long: pd.DataFrame) -> pd.DataFrame:
    out = long.groupby("stratification_category1").agg(
        rows=("data_value", "size"), with_value=("data_value", "count")
    )
    out["pct_of_rows"] = (100 * out["rows"] / len(long)).round(1)
    return out.reset_index().sort_values("rows", ascending=False).reset_index(drop=True)


def sql_type(series: pd.Series) -> str:
    """SQLite storage type the loader uses for a column."""
    if pd.api.types.is_bool_dtype(series) or pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    return "TEXT"  # strings, and dates stored as ISO text


def data_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Column metadata computed on the full tables (not on a head() sample)."""
    rows = []
    for table, df in tables.items():
        n = len(df)
        for col in df.columns:
            s = df[col]
            example = s.dropna()
            example = "" if example.empty else str(example.iloc[0])
            rows.append(
                {
                    "table": table,
                    "column": col,
                    "sql_type": sql_type(s),
                    "description": COLUMN_DESCRIPTIONS.get(col, ""),
                    "non_null": int(s.notna().sum()),
                    "pct_missing": round(100 * s.isna().sum() / n, 1) if n else 0.0,
                    "n_unique": int(s.nunique(dropna=True)),
                    "example": example[:60].replace("\n", " "),
                }
            )
    return pd.DataFrame(rows)


def describe_indicator_columns(dictionary: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    """Fill in descriptions for the wide-panel indicator columns from the catalog."""
    text = {
        r.wide_column: f"{r.question} ({r.data_value_type}, {r.data_value_unit})"
        for r in catalog.itertuples(index=False)
    }
    out = dictionary.copy()
    mask = (out["table"] == "cdc_indicators") & out["column"].isin(text)
    out.loc[mask, "description"] = out.loc[mask, "column"].map(text)
    return out


def write_data_dictionary_md(dictionary: pd.DataFrame, path: Path) -> Path:
    cols = ["column", "sql_type", "pct_missing", "n_unique", "description"]
    parts = [
        "# Data dictionary",
        "",
        "Generated by `python -m healthdw run`. Statistics are computed on the full tables. "
        "The CSV copy in `outputs/tables/data_dictionary.csv` also lists every indicator column "
        "of `cdc_indicators` and an example value for each column.",
    ]
    for table, block in dictionary.groupby("table", sort=False):
        parts += ["", f"## {table}", "", TABLE_DESCRIPTIONS.get(table, ""), ""]
        if table == "cdc_indicators":
            keys = block[block["column"].isin(WIDE_KEY)]
            n_ind = len(block) - len(keys)
            parts.append(markdown_table(keys[cols]))
            parts += [
                "",
                f"Plus {n_ind} indicator columns (REAL), one per row of `indicator_catalog`, "
                "named by lower-case question_id (for example `dia01` is diabetes among adults).",
            ]
        else:
            parts.append(markdown_table(block[cols]))
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return path


def _bullet(lines: Iterable[str]) -> list[str]:
    return [f"- {line}" for line in lines]


def write_quality_report(path: Path, ctx: dict) -> Path:
    """Write docs/data_quality_report.md from the run context assembled in pipeline.py."""
    checks = checks_to_frame(ctx["checks"])
    wide = ctx["wide"]
    ind_cols = indicator_columns(wide)
    cells = wide[ind_cols].size
    filled = int(wide[ind_cols].notna().sum().sum())
    clean_log = ctx["clean_log"]

    lines = [
        "# Data quality report",
        "",
        f"Generated by `python -m healthdw run{' --sample' if ctx['mode'] == 'sample' else ''}` "
        f"on {ctx['run_at'][:10]} (package version {ctx['version']}).",
        "",
        "## Sources",
        "",
        markdown_table(ctx["sources"]),
        "",
        "## Row counts by stage",
        "",
        markdown_table(ctx["stage_counts"]),
        "",
        "## Cleaning",
        "",
        *_bullet(
            [
                f'Values with a thousands separator (for example "9,537") parsed as numbers: '
                f"{clean_log.values_with_thousands_separator:,}. The course version coerced these to missing.",
                f"Non-empty values that still failed to parse: {clean_log.unparseable_values:,}.",
                f"Text cells with mis-encoded dashes repaired: {clean_log.mojibake_cells_repaired:,}.",
                "Raw columns dropped (non-null count in brackets): "
                + ", ".join(f"`{c}` ({n:,})" for c, n in clean_log.dropped_columns.items())
                + ".",
            ]
        ),
        "",
        "## Validation checks",
        "",
        "`flag` means at least one row failed and `info` describes the data rather than testing a rule; the action column says what the pipeline did.",
        "",
        markdown_table(checks[["table", "check", "checked", "failed", "status", "action"]]),
        "",
        "## Missing values by topic (long table, all strata)",
        "",
        "Most missing values are suppressed by CDC because the subgroup is too small for a reliable "
        "estimate, which is why stratified rows (race/ethnicity especially) are much less complete "
        "than overall rows.",
        "",
        markdown_table(
            ctx["availability"][
                ["topic", "rows", "pct_value_reported", "pct_suppressed", "pct_not_available"]
            ]
        ),
        "",
        "## Rows by stratification",
        "",
        markdown_table(ctx["strata"]),
        "",
        "## Wide panel",
        "",
        *_bullet(
            [
                f"{len(wide):,} location-period rows, {len(ind_cols)} indicator columns.",
                f"{filled:,} of {cells:,} cells filled ({100 * filled / cells:.1f}%). Most empty cells are "
                "structural: each indicator is published only for the periods its survey covers.",
                "Value type per indicator: "
                + ", ".join(
                    f"{t} ({n})" for t, n in ctx["catalog"]["data_value_type_id"].value_counts().items()
                )
                + ".",
            ]
        ),
        "",
        "## Outlier flags by topic",
        "",
        "Flags are kept for review, not removed. A flagged state is unusual relative to other "
        "locations for the same measure, which often reflects a real difference between states "
        "rather than an error.",
        "",
        markdown_table(ctx["outliers"].head(10)),
        "",
        "## openFDA labels",
        "",
        *_bullet(ctx["fda_notes"]),
        "",
        "## Simulated encounters",
        "",
        *_bullet(ctx["encounter_notes"]),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_query_results_md(
    results: list[tuple[str, str, pd.DataFrame]], path: Path, max_rows: int = 15
) -> Path:
    parts = [
        "# Example query results",
        "",
        "Output of `sql/example_queries.sql` against the warehouse built by this run.",
        "",
    ]
    for title, sql, df in results:
        parts += [f"## {title}", "", "```sql", sql, "```", ""]
        parts.append(markdown_table(df.head(max_rows)))
        if len(df) > max_rows:
            parts.append(f"\n({len(df) - max_rows} more rows not shown.)")
        parts.append("")
    path.write_text("\n".join(parts), encoding="utf-8")
    return path
