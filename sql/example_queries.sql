-- Example analytic queries against data/processed/health_dw.db.
-- Run them all with: python -m healthdw query sql/example_queries.sql
-- Each "-- name:" line titles the statement that follows it.

-- name: Diabetes among adults (age-adjusted %), Missouri, Illinois and U.S., from the wide panel
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

-- name: Ten highest adult obesity prevalences in the latest year (age-adjusted, with 95% CI)
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

-- name: Largest male minus female gaps in adult cigarette smoking, latest year (age-adjusted, percentage points)
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

-- name: Missing and suppressed estimates by topic (long table, all strata)
SELECT topic,
       COUNT(*)                                                  AS estimates,
       ROUND(100.0 * SUM(data_value IS NULL) / COUNT(*), 1)      AS pct_missing,
       ROUND(100.0 * SUM(data_value IS NULL
                         AND (data_value_footnote LIKE '%suppress%'
                              OR data_value_footnote LIKE '%too few%')) / COUNT(*), 1) AS pct_suppressed
FROM cdc_raw_clean
GROUP BY topic
ORDER BY pct_missing DESC;

-- name: Locations most often flagged as IQR outliers (overall population, all indicators and years)
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

-- name: Panel indicators with the fewest reporting locations
SELECT question_id, topic, question, data_value_type, n_locations, first_year, last_year
FROM indicator_catalog
ORDER BY n_locations, question_id
LIMIT 10;
