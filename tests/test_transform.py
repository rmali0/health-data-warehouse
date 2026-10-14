import pandas as pd
import pytest

from healthdw.clean import clean_cdc
from healthdw.transform import (
    build_indicator_catalog,
    build_wide_panel,
    choose_value_types,
    wide_column_name,
)
from healthdw.validate import validate_cdc

from conftest import cdc_row, raw_cdc


def _long(*rows):
    df, _ = clean_cdc(raw_cdc(*rows))
    out, _, _ = validate_cdc(df, current_year=2026)
    return out


def test_choose_value_types_prefers_age_adjusted():
    long = _long(
        cdc_row(DataValueTypeID="CRDPREV", DataValueType="Crude Prevalence", DataValueAlt="11"),
        cdc_row(DataValueTypeID="AGEADJPREV", DataValueAlt="10"),
        cdc_row(
            QuestionID="DIA02",
            Question="Gestational diabetes",
            DataValueTypeID="CRDPREV",
            DataValueType="Crude Prevalence",
            DataValueAlt="7",
        ),
    )
    chosen = choose_value_types(long)
    assert chosen["DIA01"] == "AGEADJPREV"
    assert chosen["DIA02"] == "CRDPREV"


def test_wide_panel_uses_overall_rows_only():
    long = _long(
        cdc_row(DataValueAlt="10"),
        cdc_row(LocationAbbr="IL", LocationDesc="Illinois", DataValueAlt="9"),
        cdc_row(YearStart="2022", YearEnd="2022", DataValueAlt="11"),
        cdc_row(
            StratificationCategoryID1="SEX",
            StratificationCategory1="Sex",
            StratificationID1="SEXF",
            Stratification1="Female",
            DataValueAlt="99",
        ),
        cdc_row(
            QuestionID="TOB04",
            Question="Current cigarette smoking among adults",
            Topic="Tobacco",
            TopicID="TOB",
            DataValueAlt="18",
        ),
    )
    catalog = build_indicator_catalog(long)
    wide = build_wide_panel(long, catalog)
    assert list(wide.columns) == [
        "location_abbr",
        "location_desc",
        "year_start",
        "year_end",
        "dia01",
        "tob04",
    ]
    assert len(wide) == 3
    mo21 = wide[(wide["location_abbr"] == "MO") & (wide["year_start"] == 2021)].iloc[0]
    assert mo21["dia01"] == 10 and mo21["tob04"] == 18
    assert 99 not in wide["dia01"].tolist()
    assert pd.isna(wide.loc[wide["location_abbr"] == "IL", "tob04"]).all()


def test_similar_question_text_gets_separate_columns():
    # The first 50 characters match, so the course version merged these into one averaged column.
    stem = "Hospitalization for chronic obstructive pulmonary disease as "
    long = _long(
        cdc_row(QuestionID="COPD03", Question=stem + "any diagnosis", DataValueAlt="20"),
        cdc_row(QuestionID="COPD04", Question=stem + "principal diagnosis", DataValueAlt="5"),
    )
    wide = build_wide_panel(long, build_indicator_catalog(long))
    assert wide.loc[0, "copd03"] == 20 and wide.loc[0, "copd04"] == 5


def test_wide_panel_refuses_ambiguous_cells():
    long = _long(cdc_row(DataValueAlt="10"), cdc_row(DataSource="NVSS", DataValueAlt="12"))
    with pytest.raises(ValueError, match="more than one value"):
        build_wide_panel(long, build_indicator_catalog(long))


def test_wide_column_name_validation():
    assert wide_column_name("COPD01") == "copd01"
    with pytest.raises(ValueError):
        wide_column_name("1; DROP TABLE x")
