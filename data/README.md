# Data

| File | Source | In git? |
|---|---|---|
| `raw/cdc_cdi.csv` | CDC U.S. Chronic Disease Indicators, dataset `g4ie-h725` on data.cdc.gov | No (about 100 MB). Run `python scripts/download_cdc_cdi.py`. |
| `sample/cdc_cdi_sample.csv.gz` | 4,256-row subset of the file above, built by `scripts/make_sample.py` | Yes (72 KB) |
| `raw/openfda_drug_labels.json` | openFDA drug label API, one record (`limit=1`), retrieved November 2025 | Yes |
| `raw/simulated_clinical_encounters.html` | Five made-up encounter records | Yes |
| `processed/` | Date-stamped exports and `health_dw.db`, written by the pipeline | No |

## CDC U.S. Chronic Disease Indicators

- Publisher: Centers for Disease Control and Prevention (CDC).
- Page: https://data.cdc.gov/Chronic-Disease-Indicators/U-S-Chronic-Disease-Indicators/g4ie-h725
- Download used by the script: https://data.cdc.gov/api/views/g4ie-h725/rows.csv?accessType=DOWNLOAD
- Terms: U.S. federal government data, generally in the public domain. Check the dataset page for current terms and cite CDC as the source.
- The committed outputs were built from a copy downloaded in November 2025: 309,215 rows, 34 columns,
  SHA-256 `a988e65ea75604ff003d70dc7a1c482b240c54417d8cf0949416f4bd213639e6`. CDC revises this dataset,
  so a fresh download may give different counts. The download script prints the SHA-256 of what it saved.
- Each row is one estimate: an indicator (`QuestionID`), a location, a reporting period
  (`YearStart` to `YearEnd`), a value type (crude or age-adjusted prevalence, rate, count, ...) and a
  stratum (overall, sex, age group, race/ethnicity or school grade).

The sample fixture keeps 16 locations (US, MO, IL and 13 other states), 9 indicators, the overall and
sex strata, and race/ethnicity rows for diabetes (to keep suppressed subgroup estimates). It is
regenerated with `python scripts/make_sample.py` after downloading the full file.

## openFDA drug labels

- Source: https://open.fda.gov/apis/drug/label/ (terms: https://open.fda.gov/terms/, license:
  https://open.fda.gov/license/). openFDA notes its data should not be used to make decisions about
  medical care.
- The committed file is the raw API response for a single label, which is enough to show JSON
  ingestion but not to analyse labels. `python scripts/fetch_openfda_labels.py --limit 100` replaces it
  with a larger pull.

## Simulated encounters

`simulated_clinical_encounters.html` is a five-row table I wrote to practise parsing HTML reports. The
patients, dates, codes and provider names are invented. It contains no patient information.
