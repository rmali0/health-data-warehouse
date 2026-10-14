from datetime import date

import numpy as np
import pandas as pd

from healthdw.clean import clean_cdc
from healthdw.validate import (
    add_outlier_flags,
    count_duplicates,
    iqr_outliers,
    validate_cdc,
    validate_encounters,
)

from conftest import cdc_row, raw_cdc

STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID"]


def _by_check(checks):
    return {c.check: c for c in checks}


def test_strata_are_not_duplicates():
    # Same year, state, topic and question: the course key saw these as duplicates.
    raw = raw_cdc(
        cdc_row(),
        cdc_row(
            StratificationCategoryID1="SEX",
            StratificationCategory1="Sex",
            StratificationID1="SEXF",
            Stratification1="Female",
        ),
        cdc_row(DataValueTypeID="CRDPREV", DataValueType="Crude Prevalence"),
    )
    df, _ = clean_cdc(raw)
    out, checks, removed = validate_cdc(df, current_year=2026)
    assert removed == 0 and len(out) == 3
    legacy = _by_check(checks)["rows sharing the course key (year_start, location, topic, question)"]
    assert legacy.failed == 2 and legacy.status == "info"


def test_exact_duplicates_removed():
    df, _ = clean_cdc(raw_cdc(cdc_row(), cdc_row()))
    out, checks, removed = validate_cdc(df, current_year=2026)
    assert removed == 1 and len(out) == 1
    assert _by_check(checks)["exact duplicate rows"].failed == 1


def test_range_rules_set_values_missing():
    df, _ = clean_cdc(
        raw_cdc(
            cdc_row(DataValueAlt="-3", LocationAbbr="IL", LocationDesc="Illinois"),
            cdc_row(DataValueAlt="140", LocationAbbr="KS", LocationDesc="Kansas"),
            cdc_row(DataValueAlt="12", LowConfidenceLimit="13", LocationAbbr="IA", LocationDesc="Iowa"),
        )
    )
    out, checks, _ = validate_cdc(df, current_year=2026)
    by = _by_check(checks)
    assert by["negative data_value"].failed == 1
    assert by["percentage outside 0-100"].failed == 1
    assert by["estimate outside its 95% CI"].failed == 1
    assert out["data_value"].isna().sum() == 2


def test_future_years_reported():
    df, _ = clean_cdc(raw_cdc(cdc_row(YearStart="2030", YearEnd="2030")))
    _, checks, _ = validate_cdc(df, current_year=2026)
    assert _by_check(checks)["year outside 1900-2026"].failed == 1


def test_iqr_outliers_simple():
    s = pd.Series([10, 11, 12, 11, 10, 12, 11, 50, np.nan])
    flags = iqr_outliers(s)
    assert flags.tolist() == [False] * 7 + [True, False]


def _group_frame(values, question="DIA01", locations=None):
    locations = locations or STATES[: len(values)]
    return pd.DataFrame(
        {
            "question_id": question,
            "data_value_type_id": "AGEADJPREV",
            "year_start": 2021,
            "year_end": 2021,
            "stratification_category_id1": "OVERALL",
            "stratification_id1": "OVR",
            "location_abbr": locations,
            "data_value": values,
        }
    )


def test_outlier_flags_within_group_only():
    typical = [10.0, 10.5, 11.0, 9.5, 10.2, 10.8, 9.8, 10.1, 10.4, 9.9, 10.3]
    high = _group_frame(typical + [30.0])
    # A different indicator on a much larger scale must not drive the first group's flags.
    other = _group_frame([float(v) for v in range(1000, 1012)], question="CAN07")
    out = add_outlier_flags(pd.concat([high, other], ignore_index=True))
    assert out.loc[out["question_id"] == "DIA01", "is_outlier_iqr"].tolist() == [False] * 11 + [True]
    assert not out.loc[out["question_id"] == "CAN07", "is_outlier_iqr"].any()
    assert out.loc[11, "is_outlier_z"]


def test_outlier_flags_skip_small_groups_and_us():
    small = _group_frame([10.0, 10.0, 10.0, 50.0])
    assert not add_outlier_flags(small)["is_outlier_iqr"].any()

    values = [10.0, 10.5, 11.0, 9.5, 10.2, 10.8, 9.8, 10.1, 10.4, 9.9, 10.3, 30.0]
    with_us = _group_frame(values, locations=STATES[:11] + ["US"])
    out = add_outlier_flags(with_us)
    assert not out["is_outlier_iqr"].any()
    assert np.isnan(out.loc[11, "z_score"])


def test_count_duplicates_on_key():
    df = pd.DataFrame({"a": [1, 1, 2], "b": [1, 2, 3]})
    assert count_duplicates(df) == 0
    assert count_duplicates(df, ("a",)) == 1


def test_validate_encounters_flags_problems():
    df = pd.DataFrame(
        {
            "encounter_id": ["E1", "E1", "E3"],
            "patient_id": ["P1", None, "P3"],
            "encounter_date": pd.to_datetime(["2024-01-01", "2027-01-01", None]),
            "diagnosis_code": ["I10", "E11.9", "BAD"],
        }
    )
    by = _by_check(validate_encounters(df, today=date(2026, 1, 1)))
    assert by["duplicate encounter_id"].failed == 1
    assert by["missing patient_id"].failed == 1
    assert by["missing or unparseable encounter_date"].failed == 1
    assert by["encounter_date in the future"].failed == 1
    assert by["diagnosis_code not ICD-10-CM format"].failed == 1
