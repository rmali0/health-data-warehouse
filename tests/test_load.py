import sqlite3

import pytest

from healthdw.load import split_sql_file, table_counts


def test_round_trip_counts(sample_run):
    paths, result = sample_run
    with sqlite3.connect(paths.db) as conn:
        counts = table_counts(conn)
    assert counts == result.table_counts
    assert counts["cdc_raw_clean"] == 4256
    assert counts["fda_drug_labels"] == 1
    assert counts["clinical_encounters"] == 5
    assert counts["etl_runs"] == 1


def test_values_survive_load(sample_run):
    paths, _ = sample_run
    with sqlite3.connect(paths.db) as conn:
        dia = conn.execute(
            "SELECT dia01 FROM cdc_indicators WHERE location_abbr='MO' AND year_start=2021 AND year_end=2021"
        ).fetchone()[0]
        long = conn.execute(
            "SELECT data_value FROM cdc_raw_clean WHERE location_abbr='MO' AND question_id='DIA01' "
            "AND year_start=2021 AND data_value_type_id='AGEADJPREV' AND stratification_id1='OVR'"
        ).fetchone()[0]
        big = conn.execute(
            "SELECT MAX(data_value) FROM cdc_raw_clean WHERE data_value_type_id='NMBR'"
        ).fetchone()[0]
        date = conn.execute(
            "SELECT encounter_date FROM clinical_encounters WHERE encounter_id='ENC001'"
        ).fetchone()[0]
    assert dia == long == 10.0
    assert big > 1000  # thousands-separated counts were parsed, not dropped
    assert date == "2024-01-15"


def test_natural_key_is_enforced(sample_run):
    paths, _ = sample_run
    with sqlite3.connect(paths.db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(cdc_raw_clean)")][1:]
        row = conn.execute(f"SELECT {', '.join(cols)} FROM cdc_raw_clean LIMIT 1").fetchone()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO cdc_raw_clean ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", row
            )


def test_split_sql_file_titles():
    text = "-- name: First\nSELECT 1;\n\n-- a comment\n-- name: Second\nSELECT\n  2;\nSELECT 3;"
    parsed = split_sql_file(text)
    assert [t for t, _ in parsed] == ["First", "Second", ""]
    assert parsed[1][1] == "SELECT\n  2;"
