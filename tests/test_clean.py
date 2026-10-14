import json
import math

import pandas as pd
import pytest

from healthdw.clean import (
    CDC_LONG_COLUMNS,
    clean_cdc,
    clean_encounters,
    clean_fda,
    parse_number,
    repair_mojibake,
    snake_columns,
    to_snake_case,
)

from conftest import REPO, cdc_row, raw_cdc


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("LocationAbbr", "location_abbr"),
        ("TopicID", "topic_id"),
        ("StratificationCategoryID1", "stratification_category_id1"),
        ("DataValueAlt", "data_value_alt"),
        ("EncounterID", "encounter_id"),
        ("openfda.brand_name", "openfda_brand_name"),
        ("  Year Start ", "year_start"),
        ("Location-Abbr", "location_abbr"),
    ],
)
def test_to_snake_case(raw, expected):
    assert to_snake_case(raw) == expected


def test_snake_columns_rejects_collisions():
    with pytest.raises(ValueError, match="duplicate"):
        snake_columns(pd.DataFrame(columns=["Year Start", "year_start"]))


def test_parse_number_handles_thousands_separators():
    out = parse_number(pd.Series(["9,537", "12.5", " 314,982 ", "", None, "abc"]))
    assert out.iloc[0] == 9537.0
    assert out.iloc[1] == 12.5
    assert out.iloc[2] == 314982.0
    assert out.iloc[3:].isna().all()


def test_repair_mojibake_restores_dash():
    broken = "aged 18â€“64 years"
    assert repair_mojibake(broken) == "aged 18-64 years"
    assert repair_mojibake("aged 18-64 years") == "aged 18-64 years"


def test_clean_cdc_types_and_columns():
    raw = raw_cdc(
        cdc_row(DataValueAlt="9,537", DataValue="9,537", DataValueUnit="Number", DataValueTypeID="NMBR"),
        cdc_row(DataValueAlt=None, DataValue=None, DataValueFootnote="Data suppressed; too few"),
        cdc_row(Question="Influenza vaccination among adults 18â€“64"),
    )
    df, log = clean_cdc(raw)
    assert tuple(df.columns) == CDC_LONG_COLUMNS
    assert df.loc[0, "data_value"] == 9537.0
    assert math.isnan(df.loc[1, "data_value"])
    assert df.loc[2, "question"] == "Influenza vaccination among adults 18-64"
    assert df["year_start"].dtype == "Int64"
    assert log.values_with_thousands_separator == 1
    assert log.unparseable_values == 0
    assert log.mojibake_cells_repaired == 1
    assert "response" in log.dropped_columns and log.dropped_columns["response"] == 0


def test_clean_encounters_parses_dates_and_codes():
    raw = pd.DataFrame(
        {
            "EncounterID": ["E1"],
            "PatientID": ["P1"],
            "EncounterDate": ["2024-01-15"],
            "Department": [" Cardiology "],
            "DiagnosisCode": ["i10"],
            "Provider": ["Dr. A"],
        }
    )
    df = clean_encounters(raw)
    assert list(df.columns) == [
        "encounter_id",
        "patient_id",
        "encounter_date",
        "department",
        "diagnosis_code",
        "provider",
    ]
    assert df.loc[0, "encounter_date"] == pd.Timestamp("2024-01-15")
    assert df.loc[0, "diagnosis_code"] == "I10"
    assert df.loc[0, "department"] == "Cardiology"


def test_clean_fda_keeps_raw_json():
    payload = json.loads((REPO / "data" / "raw" / "openfda_drug_labels.json").read_text())
    df = clean_fda(payload["results"])
    assert len(df) == 1
    row = df.iloc[0]
    assert row["brand_name"] == "SILICEA"
    assert row["effective_time"] == pd.Timestamp("2021-09-02")
    assert json.loads(row["raw_json"])["id"] == row["id"]
    assert row["n_sections"] == 14
