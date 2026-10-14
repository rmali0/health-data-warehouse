# Example query results

Output of `sql/example_queries.sql` against the warehouse built by this run.

## Diabetes among adults (age-adjusted %), Missouri, Illinois and U.S., from the wide panel

```sql
SELECT year_start                                              AS year,
       ROUND(MAX(CASE WHEN location_abbr = 'MO' THEN dia01 END), 1) AS missouri,
       ROUND(MAX(CASE WHEN location_abbr = 'IL' THEN dia01 END), 1) AS illinois,
       ROUND(MAX(CASE WHEN location_abbr = 'US' THEN dia01 END), 1) AS us
FROM cdc_indicators
WHERE year_start = year_end
  AND location_abbr IN ('MO', 'IL', 'US')
  AND dia01 IS NOT NULL
GROUP BY year_start
ORDER BY year_start;
```

| year | missouri | illinois | us |
|---|---|---|---|
| 2019 | 9.1 | 10.1 | 10.0 |
| 2020 | 9.5 | 9.4 | 10.0 |
| 2021 | 10.0 | 9.7 | 10.3 |
| 2022 | 10.2 | 10.8 | 10.8 |

## Ten highest adult obesity prevalences in the latest year (age-adjusted, with 95% CI)

```sql
WITH obesity AS (
    SELECT location_desc, year_start, data_value, low_confidence_limit, high_confidence_limit
    FROM cdc_raw_clean
    WHERE question_id = 'NPW14'
      AND data_value_type_id = 'AGEADJPREV'
      AND stratification_category_id1 = 'OVERALL'
      AND location_abbr <> 'US'
      AND year_start = year_end
      AND data_value IS NOT NULL
)
SELECT location_desc        AS location,
       year_start           AS year,
       data_value           AS obesity_pct,
       low_confidence_limit AS ci_low,
       high_confidence_limit AS ci_high
FROM obesity
WHERE year_start = (SELECT MAX(year_start) FROM obesity)
ORDER BY data_value DESC
LIMIT 10;
```

| location | year | obesity_pct | ci_low | ci_high |
|---|---|---|---|---|
| West Virginia | 2022 | 41.5 | 39.6 | 43.5 |
| Oklahoma | 2022 | 40.6 | 38.9 | 42.3 |
| Louisiana | 2022 | 40.3 | 38.5 | 42.2 |
| Mississippi | 2022 | 40.1 | 38.1 | 42.1 |
| Tennessee | 2022 | 39.1 | 37.2 | 41.1 |
| Alabama | 2022 | 38.4 | 36.3 | 40.5 |
| Indiana | 2022 | 38.4 | 37.0 | 39.7 |
| Ohio | 2022 | 38.4 | 37.1 | 39.6 |
| Kentucky | 2022 | 38.1 | 35.9 | 40.4 |
| Wisconsin | 2022 | 38.1 | 36.7 | 39.5 |

## Largest male minus female gaps in adult cigarette smoking, latest year (age-adjusted, percentage points)

```sql
WITH smoking AS (
    SELECT location_abbr, year_start, stratification_id1, data_value
    FROM cdc_raw_clean
    WHERE question_id = 'TOB04'
      AND data_value_type_id = 'AGEADJPREV'
      AND stratification_category_id1 = 'SEX'
      AND year_start = year_end
      AND data_value IS NOT NULL
)
SELECT m.location_abbr                       AS location,
       m.year_start                          AS year,
       m.data_value                          AS male_pct,
       f.data_value                          AS female_pct,
       ROUND(m.data_value - f.data_value, 1) AS gap_pts
FROM smoking AS m
JOIN smoking AS f
  ON f.location_abbr = m.location_abbr
 AND f.year_start = m.year_start
 AND f.stratification_id1 = 'SEXF'
WHERE m.stratification_id1 = 'SEXM'
  AND m.year_start = (SELECT MAX(year_start) FROM smoking)
ORDER BY gap_pts DESC
LIMIT 10;
```

| location | year | male_pct | female_pct | gap_pts |
|---|---|---|---|---|
| GU | 2022 | 25.2 | 15.8 | 9.4 |
| MS | 2022 | 21.1 | 15.2 | 5.9 |
| PR | 2022 | 13.4 | 7.5 | 5.9 |
| CA | 2022 | 12.8 | 7.0 | 5.8 |
| AR | 2022 | 22.5 | 17.3 | 5.2 |
| IL | 2022 | 15.1 | 10.5 | 4.6 |
| VA | 2022 | 14.5 | 10.0 | 4.5 |
| AK | 2022 | 18.0 | 13.9 | 4.1 |
| SC | 2022 | 18.3 | 14.2 | 4.1 |
| CT | 2022 | 12.3 | 8.3 | 4.0 |

## Missing and suppressed estimates by topic (long table, all strata)

```sql
SELECT topic,
       COUNT(*)                                                  AS estimates,
       ROUND(100.0 * SUM(data_value IS NULL) / COUNT(*), 1)      AS pct_missing,
       ROUND(100.0 * SUM(data_value IS NULL
                         AND (data_value_footnote LIKE '%suppress%'
                              OR data_value_footnote LIKE '%too few%')) / COUNT(*), 1) AS pct_suppressed
FROM cdc_raw_clean
GROUP BY topic
ORDER BY pct_missing DESC;
```

| topic | estimates | pct_missing | pct_suppressed |
|---|---|---|---|
| Cognitive Health and Caregiving | 9,904 | 61.8 | 20.9 |
| Asthma | 10,511 | 50.2 | 49.0 |
| Maternal Health | 1,026 | 41.3 | 37.2 |
| Tobacco | 15,931 | 39.9 | 20.8 |
| Diabetes | 17,318 | 36.2 | 35.2 |
| Immunization | 19,140 | 36.0 | 31.7 |
| Arthritis | 18,645 | 35.9 | 30.5 |
| Social Determinants of Health | 19,026 | 35.3 | 23.0 |
| Alcohol | 25,321 | 35.2 | 30.2 |
| Chronic Obstructive Pulmonary Disease | 26,951 | 32.0 | 30.0 |
| Oral Health | 13,236 | 31.8 | 28.1 |
| Mental Health | 16,976 | 30.9 | 26.7 |
| Cancer | 22,358 | 26.2 | 24.4 |
| Health Status | 25,612 | 25.2 | 22.7 |
| Nutrition, Physical Activity, and Weight Status | 26,069 | 24.7 | 16.7 |

(4 more rows not shown.)

## Locations most often flagged as IQR outliers (overall population, all indicators and years)

```sql
SELECT r.location_desc                                   AS location,
       COUNT(r.data_value)                               AS estimates,
       SUM(r.is_outlier_iqr)                             AS iqr_flags,
       ROUND(100.0 * SUM(r.is_outlier_iqr) / COUNT(r.data_value), 1) AS pct_flagged
FROM cdc_raw_clean AS r
WHERE r.stratification_category_id1 = 'OVERALL'
  AND r.location_abbr <> 'US'
GROUP BY r.location_desc
ORDER BY iqr_flags DESC
LIMIT 10;
```

| location | estimates | iqr_flags | pct_flagged |
|---|---|---|---|
| Puerto Rico | 357 | 109 | 30.5 |
| West Virginia | 518 | 89 | 17.2 |
| Texas | 514 | 58 | 11.3 |
| Guam | 292 | 55 | 18.8 |
| California | 497 | 53 | 10.7 |
| Florida | 441 | 51 | 11.6 |
| Virgin Islands | 129 | 41 | 31.8 |
| Kentucky | 523 | 41 | 7.8 |
| New York | 524 | 38 | 7.3 |
| Mississippi | 536 | 36 | 6.7 |

## Panel indicators with the fewest reporting locations

```sql
SELECT question_id, topic, question, data_value_type, n_locations, first_year, last_year
FROM indicator_catalog
ORDER BY n_locations, question_id
LIMIT 10;
```

| question_id | topic | question | data_value_type | n_locations | first_year | last_year |
|---|---|---|---|---|---|---|
| MEN01 | Mental Health | Current poor mental health among high school students | Crude Prevalence | 36 | 2021 | 2021 |
| SDH05 | Social Determinants of Health | Unable to pay mortgage, rent, or utility bills in the past 12 months among adults | Age-adjusted Prevalence | 38 | 2022 | 2022 |
| SDH06 | Social Determinants of Health | Lack of reliable transportation in the past 12 months among adults | Age-adjusted Prevalence | 38 | 2022 | 2022 |
| SDH07 | Social Determinants of Health | Lack of social and emotional support needed among adults | Age-adjusted Prevalence | 38 | 2022 | 2022 |
| NPW03 | Nutrition, Physical Activity, and Weight Status | Consumed vegetables less than one time daily among high school students | Crude Prevalence | 39 | 2019 | 2021 |
| AST01 | Asthma | Asthma mortality among all people, underlying cause | Age-adjusted Rate | 40 | 2019 | 2021 |
| TOB01 | Tobacco | Current tobacco use of any tobacco product among high school students | Crude Prevalence | 42 | 2019 | 2021 |
| TOB03 | Tobacco | Current smokeless tobacco use among high school students | Crude Prevalence | 44 | 2019 | 2021 |
| NPW05 | Nutrition, Physical Activity, and Weight Status | Consumed regular soda at least one time daily among high school students | Crude Prevalence | 45 | 2019 | 2021 |
| DIA02 | Diabetes | Gestational diabetes among women with a recent live birth | Crude Prevalence | 46 | 2019 | 2021 |
