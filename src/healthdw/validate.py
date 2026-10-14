"""Data quality checks: duplicates, range rules and outlier flags.

Every check returns a Check record so the quality report can list what was
tested, how many rows failed and what the pipeline did about it. Nothing here
fails silently: values are either corrected with a logged count or flagged.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date

import pandas as pd

# One CDC estimate is identified by period, place, source, indicator, value
# type and stratum. The course version used only (year, state, topic,
# question), which treats every sex, age and race/ethnicity row as a
# duplicate of the first one it sees.
CDC_NATURAL_KEY = (
    "year_start",
    "year_end",
    "location_abbr",
    "data_source",
    "question_id",
    "data_value_type_id",
    "stratification_category_id1",
    "stratification_id1",
)
LEGACY_COURSE_KEY = ("year_start", "location_abbr", "topic", "question")

# Outliers are judged against other locations reporting the same measure for
# the same period and stratum. Pooling all indicators (percentages, rates per
# 100,000 and raw counts) into one IQR, as the course version did, mostly
# flags whichever indicators have the largest units.
OUTLIER_GROUP = (
    "question_id",
    "data_value_type_id",
    "year_start",
    "year_end",
    "stratification_category_id1",
    "stratification_id1",
)
NATIONAL_LOCATION = "US"

# ICD-10-CM: letter, digit, alphanumeric, then an optional dot and 1 to 4 characters.
ICD10_PATTERN = re.compile(r"^[A-TV-Z][0-9][0-9A-Z](\.[0-9A-Z]{1,4})?$")


@dataclass(frozen=True)
class Check:
    table: str
    check: str
    checked: int
    failed: int
    action: str
    info: bool = False  # describes the data rather than testing a rule

    @property
    def passed(self) -> bool:
        return self.info or self.failed == 0

    @property
    def status(self) -> str:
        if self.info:
            return "info"
        return "pass" if self.failed == 0 else "flag"


def checks_to_frame(checks: list[Check]) -> pd.DataFrame:
    frame = pd.DataFrame([asdict(c) for c in checks]).drop(columns="info")
    frame["status"] = [c.status for c in checks]
    return frame


def count_duplicates(df: pd.DataFrame, key: tuple[str, ...] | None = None) -> int:
    return int(df.duplicated(subset=list(key) if key else None).sum())


def deduplicate(df: pd.DataFrame, key: tuple[str, ...]) -> tuple[pd.DataFrame, int]:
    before = len(df)
    out = df.drop_duplicates(subset=list(key), keep="first").reset_index(drop=True)
    return out, before - len(out)


def iqr_outliers(values: pd.Series, multiplier: float = 1.5) -> pd.Series:
    """True where a value lies outside the Tukey fences; missing values are False."""
    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    spread = q3 - q1
    return ((values < q1 - multiplier * spread) | (values > q3 + multiplier * spread)).fillna(False)


def add_outlier_flags(
    df: pd.DataFrame,
    value_col: str = "data_value",
    group_cols: tuple[str, ...] = OUTLIER_GROUP,
    min_group_size: int = 10,
    iqr_multiplier: float = 1.5,
    z_threshold: float = 3.0,
) -> pd.DataFrame:
    """Add is_outlier_iqr, z_score and is_outlier_z, computed within comparable groups.

    The national (US) row is excluded because it is an aggregate of the states
    it would be compared with. Groups with fewer than min_group_size values
    are left unflagged, since quartiles of a handful of numbers mean little.
    """
    out = df.copy()
    out["is_outlier_iqr"] = False
    out["z_score"] = float("nan")
    out["is_outlier_z"] = False

    eligible = out[value_col].notna() & (out["location_abbr"] != NATIONAL_LOCATION)
    sub = out.loc[eligible, [*group_cols, value_col]]
    grouped = sub.groupby(list(group_cols), dropna=False)[value_col]
    size = grouped.transform("size")
    q1 = grouped.transform("quantile", 0.25)
    q3 = grouped.transform("quantile", 0.75)
    mean = grouped.transform("mean")
    std = grouped.transform("std")

    big_enough = size >= min_group_size
    values = sub[value_col]
    spread = q3 - q1
    iqr_flag = (values < q1 - iqr_multiplier * spread) | (values > q3 + iqr_multiplier * spread)
    z = (values - mean) / std.where(std > 0)

    out.loc[sub.index, "is_outlier_iqr"] = (iqr_flag & big_enough).to_numpy()
    out.loc[sub.index, "z_score"] = z.where(big_enough).to_numpy()
    out.loc[sub.index, "is_outlier_z"] = ((z.abs() > z_threshold) & big_enough).to_numpy()
    out["is_outlier_iqr"] = out["is_outlier_iqr"].astype(bool)
    out["is_outlier_z"] = out["is_outlier_z"].astype(bool)
    return out


def validate_cdc(df: pd.DataFrame, current_year: int | None = None) -> tuple[pd.DataFrame, list[Check], int]:
    """Run the CDC checks. Returns the validated frame, the checks and rows removed."""
    current_year = current_year or date.today().year
    n = len(df)
    checks = [
        Check(
            "cdc_raw_clean",
            "exact duplicate rows",
            n,
            count_duplicates(df),
            "removed by the natural-key step",
        ),
        Check(
            "cdc_raw_clean",
            "rows sharing the course key (year_start, location, topic, question)",
            n,
            count_duplicates(df, LEGACY_COURSE_KEY),
            "none: these are distinct strata and value types, not duplicates",
            info=True,
        ),
    ]
    out, removed = deduplicate(df, CDC_NATURAL_KEY)
    checks.append(Check("cdc_raw_clean", "duplicate natural key", n, removed, "dropped (kept first)"))
    n = len(out)

    bad_year = (out["year_start"] < 1900) | (out["year_end"] > current_year)
    checks.append(
        Check("cdc_raw_clean", f"year outside 1900-{current_year}", n, int(bad_year.sum()), "reported")
    )
    reversed_period = out["year_start"] > out["year_end"]
    checks.append(
        Check("cdc_raw_clean", "year_start after year_end", n, int(reversed_period.sum()), "reported")
    )

    value = out["data_value"]
    has_value = int(value.notna().sum())
    negative = value < 0
    out.loc[negative, "data_value"] = float("nan")
    checks.append(
        Check("cdc_raw_clean", "negative data_value", has_value, int(negative.sum()), "set to missing")
    )

    is_pct = out["data_value_unit"] == "%"
    bad_pct = is_pct & ((out["data_value"] < 0) | (out["data_value"] > 100))
    out.loc[bad_pct, "data_value"] = float("nan")
    checks.append(
        Check(
            "cdc_raw_clean",
            "percentage outside 0-100",
            int((is_pct & value.notna()).sum()),
            int(bad_pct.sum()),
            "set to missing",
        )
    )

    low, high, v = out["low_confidence_limit"], out["high_confidence_limit"], out["data_value"]
    with_ci = low.notna() & high.notna() & v.notna()
    ci_bad = with_ci & ((low > v) | (v > high))
    checks.append(
        Check(
            "cdc_raw_clean", "estimate outside its 95% CI", int(with_ci.sum()), int(ci_bad.sum()), "reported"
        )
    )

    out = add_outlier_flags(out)
    flagged = out["is_outlier_iqr"]
    checks.append(
        Check(
            "cdc_raw_clean",
            "IQR outlier within indicator, period and stratum",
            has_value,
            int(flagged.sum()),
            "flagged in is_outlier_iqr (kept)",
        )
    )
    checks.append(
        Check(
            "cdc_raw_clean",
            "|z| > 3 within indicator, period and stratum",
            has_value,
            int(out["is_outlier_z"].sum()),
            "flagged in is_outlier_z (kept)",
        )
    )
    return out, checks, removed


def validate_encounters(df: pd.DataFrame, today: date | None = None) -> list[Check]:
    today = today or date.today()
    n = len(df)
    dates = df["encounter_date"]
    codes = df["diagnosis_code"].fillna("").astype(str)
    return [
        Check(
            "clinical_encounters",
            "duplicate encounter_id",
            n,
            count_duplicates(df, ("encounter_id",)),
            "reported",
        ),
        Check("clinical_encounters", "missing patient_id", n, int(df["patient_id"].isna().sum()), "reported"),
        Check(
            "clinical_encounters",
            "missing or unparseable encounter_date",
            n,
            int(dates.isna().sum()),
            "reported",
        ),
        Check(
            "clinical_encounters",
            "encounter_date in the future",
            n,
            int((dates > pd.Timestamp(today)).sum()),
            "reported",
        ),
        Check(
            "clinical_encounters",
            "diagnosis_code not ICD-10-CM format",
            n,
            int((~codes.str.match(ICD10_PATTERN)).sum()),
            "reported",
        ),
    ]


def validate_fda(df: pd.DataFrame) -> list[Check]:
    n = len(df)
    return [
        Check("fda_drug_labels", "missing label id", n, int(df["id"].isna().sum()), "reported"),
        Check("fda_drug_labels", "duplicate label id", n, count_duplicates(df, ("id",)), "reported"),
        Check(
            "fda_drug_labels",
            "missing or unparseable effective_time",
            n,
            int(df["effective_time"].isna().sum()),
            "reported",
        ),
    ]
