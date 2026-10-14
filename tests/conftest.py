from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from healthdw.config import Paths
from healthdw.pipeline import run_pipeline

REPO = Path(__file__).resolve().parents[1]
RAW_CDC_COLUMNS = [
    "YearStart",
    "YearEnd",
    "LocationAbbr",
    "LocationDesc",
    "DataSource",
    "Topic",
    "Question",
    "Response",
    "DataValueUnit",
    "DataValueType",
    "DataValue",
    "DataValueAlt",
    "DataValueFootnoteSymbol",
    "DataValueFootnote",
    "LowConfidenceLimit",
    "HighConfidenceLimit",
    "StratificationCategory1",
    "Stratification1",
    "StratificationCategory2",
    "Stratification2",
    "StratificationCategory3",
    "Stratification3",
    "Geolocation",
    "LocationID",
    "TopicID",
    "QuestionID",
    "ResponseID",
    "DataValueTypeID",
    "StratificationCategoryID1",
    "StratificationID1",
    "StratificationCategoryID2",
    "StratificationID2",
    "StratificationCategoryID3",
    "StratificationID3",
]


def cdc_row(**overrides: str) -> dict[str, object]:
    """One raw CDC row (all text, as read_cdc returns it) with sensible defaults."""
    row: dict[str, object] = {c: None for c in RAW_CDC_COLUMNS}
    row.update(
        YearStart="2021",
        YearEnd="2021",
        LocationAbbr="MO",
        LocationDesc="Missouri",
        LocationID="29",
        DataSource="BRFSS",
        Topic="Diabetes",
        TopicID="DIA",
        Question="Diabetes among adults",
        QuestionID="DIA01",
        DataValueUnit="%",
        DataValueType="Age-adjusted Prevalence",
        DataValueTypeID="AGEADJPREV",
        DataValue="10.0",
        DataValueAlt="10.0",
        LowConfidenceLimit="9.0",
        HighConfidenceLimit="11.0",
        StratificationCategory1="Overall",
        StratificationCategoryID1="OVERALL",
        Stratification1="Overall",
        StratificationID1="OVR",
    )
    row.update(overrides)
    return row


def raw_cdc(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=RAW_CDC_COLUMNS)


@pytest.fixture(scope="session")
def sample_run(tmp_path_factory):
    """Run the whole pipeline once on the bundled sample, writing to a temp dir."""
    out = tmp_path_factory.mktemp("sample_run")
    paths = Paths.for_run(REPO, out)
    result = run_pipeline(paths, paths.cdc_sample, mode="sample", today=date(2026, 1, 15))
    return paths, result
