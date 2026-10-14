-- Mini health data warehouse: SQLite schema.
--
-- The pipeline rebuilds the database from scratch on every run, so each
-- table is dropped and recreated here. The wide panel table cdc_indicators is
-- not declared in this file because its columns depend on which indicators
-- are present in the CDC release; load.py generates its DDL from
-- indicator_catalog (key columns below, then one REAL column per indicator,
-- named by lower-case question_id):
--
--   CREATE TABLE cdc_indicators (
--       location_abbr TEXT    NOT NULL,
--       location_desc TEXT    NOT NULL,
--       year_start    INTEGER NOT NULL,
--       year_end      INTEGER NOT NULL,
--       alc01         REAL,  ...  -- one column per indicator_catalog.wide_column
--       PRIMARY KEY (location_abbr, year_start, year_end)
--   );

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS cdc_indicators;
DROP TABLE IF EXISTS cdc_raw_clean;
DROP TABLE IF EXISTS indicator_catalog;
DROP TABLE IF EXISTS fda_drug_labels;
DROP TABLE IF EXISTS clinical_encounters;
DROP TABLE IF EXISTS etl_runs;

-- One row per CDC indicator, with the value type used in the wide panel.
CREATE TABLE indicator_catalog (
    question_id        TEXT    PRIMARY KEY,
    wide_column        TEXT    NOT NULL UNIQUE,
    topic_id           TEXT    NOT NULL,
    topic              TEXT    NOT NULL,
    question           TEXT    NOT NULL,
    data_source        TEXT,
    data_value_type_id TEXT    NOT NULL,
    data_value_type    TEXT    NOT NULL,
    data_value_unit    TEXT,
    n_locations        INTEGER NOT NULL,
    first_year         INTEGER NOT NULL,
    last_year          INTEGER NOT NULL
);

-- Long table: every CDC estimate for every stratum and value type.
CREATE TABLE cdc_raw_clean (
    row_id                      INTEGER PRIMARY KEY,
    year_start                  INTEGER NOT NULL,
    year_end                    INTEGER NOT NULL,
    location_abbr               TEXT    NOT NULL,
    location_desc               TEXT    NOT NULL,
    location_id                 INTEGER,
    data_source                 TEXT    NOT NULL,
    topic_id                    TEXT    NOT NULL,
    topic                       TEXT    NOT NULL,
    question_id                 TEXT    NOT NULL,
    question                    TEXT    NOT NULL,
    data_value_type_id          TEXT    NOT NULL,
    data_value_type             TEXT    NOT NULL,
    data_value_unit             TEXT,
    data_value                  REAL,
    low_confidence_limit        REAL,
    high_confidence_limit       REAL,
    data_value_footnote_symbol  TEXT,
    data_value_footnote         TEXT,
    stratification_category_id1 TEXT    NOT NULL,
    stratification_category1    TEXT    NOT NULL,
    stratification_id1          TEXT    NOT NULL,
    stratification1             TEXT    NOT NULL,
    geolocation                 TEXT,
    is_outlier_iqr              INTEGER NOT NULL CHECK (is_outlier_iqr IN (0, 1)),
    z_score                     REAL,
    is_outlier_z                INTEGER NOT NULL CHECK (is_outlier_z IN (0, 1)),
    CHECK (year_start <= year_end),
    UNIQUE (year_start, year_end, location_abbr, data_source, question_id,
            data_value_type_id, stratification_category_id1, stratification_id1)
);

CREATE INDEX idx_cdc_raw_question ON cdc_raw_clean (question_id, location_abbr, year_start);
CREATE INDEX idx_cdc_raw_topic ON cdc_raw_clean (topic);
CREATE INDEX idx_cdc_raw_strat ON cdc_raw_clean (stratification_category_id1, stratification_id1);

-- Curated openFDA label fields plus the full record as JSON.
CREATE TABLE fda_drug_labels (
    id                        TEXT PRIMARY KEY,
    set_id                    TEXT,
    effective_time            TEXT,   -- ISO date (YYYY-MM-DD)
    version                   TEXT,
    brand_name                TEXT,
    generic_name              TEXT,
    manufacturer_name         TEXT,
    product_type              TEXT,
    route                     TEXT,
    purpose                   TEXT,
    indications_and_usage     TEXT,
    warnings                  TEXT,
    dosage_and_administration TEXT,
    active_ingredient         TEXT,
    inactive_ingredient       TEXT,
    n_sections                INTEGER NOT NULL,
    raw_json                  TEXT    NOT NULL
);

-- Simulated encounter records parsed from an HTML report.
CREATE TABLE clinical_encounters (
    encounter_id   TEXT PRIMARY KEY,
    patient_id     TEXT NOT NULL,
    encounter_date TEXT,              -- ISO date (YYYY-MM-DD)
    department     TEXT,
    diagnosis_code TEXT,              -- ICD-10-CM
    provider       TEXT
);

-- Lineage: one row per pipeline run that built this database.
CREATE TABLE etl_runs (
    run_id            INTEGER PRIMARY KEY,
    run_at            TEXT    NOT NULL,
    mode              TEXT    NOT NULL,
    package_version   TEXT    NOT NULL,
    cdc_source        TEXT    NOT NULL,
    cdc_sha256        TEXT    NOT NULL,
    cdc_rows_raw      INTEGER NOT NULL,
    cdc_rows_clean    INTEGER NOT NULL,
    wide_rows         INTEGER NOT NULL,
    wide_indicators   INTEGER NOT NULL,
    fda_rows          INTEGER NOT NULL,
    encounter_rows    INTEGER NOT NULL
);
