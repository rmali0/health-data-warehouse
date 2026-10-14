"""End-to-end run: ingest, clean, validate, reshape, load, report, export."""

from __future__ import annotations

import json
import logging
import platform
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from . import __version__
from .clean import clean_cdc, clean_encounters, clean_fda
from .config import Paths
from .figures import (
    plot_panel_coverage,
    plot_state_spread,
    plot_state_trends,
    plot_value_availability,
)
from .ingest import describe_source, read_cdc, read_encounters_html, read_fda_labels
from .load import WarehouseTables, build_warehouse, run_queries
from .report import (
    data_dictionary,
    describe_indicator_columns,
    outliers_by_topic,
    panel_coverage,
    rows_by_stratification,
    value_availability_by_topic,
    write_data_dictionary_md,
    write_quality_report,
    write_query_results_md,
)
from .transform import OVERALL, build_indicator_catalog, build_wide_panel, indicator_columns
from .validate import checks_to_frame, validate_cdc, validate_encounters, validate_fda

log = logging.getLogger("healthdw")


@dataclass
class RunResult:
    mode: str
    db_path: Path
    table_counts: dict[str, int]
    metadata: dict
    outputs: list[Path] = field(default_factory=list)


@contextmanager
def _stage(name: str, timings: dict[str, float]):
    log.info("%s ...", name)
    start = time.perf_counter()
    yield
    timings[name] = round(time.perf_counter() - start, 2)
    log.info("%s done in %.1fs", name, timings[name])


def _relative(path: Path, root: Path) -> str:
    try:
        return path.absolute().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _fda_notes(fda: pd.DataFrame) -> list[str]:
    notes = [f"{len(fda)} label record(s) loaded; {int(fda['n_sections'].sum())} label sections in total."]
    for r in fda.itertuples(index=False):
        notes.append(
            f"`{r.id}`: {r.brand_name or 'no brand name'} ({r.product_type or 'unknown type'}), "
            f"effective {r.effective_time:%Y-%m-%d}, {r.n_sections} sections."
        )
    if len(fda) < 30:
        notes.append(
            "The committed JSON is a small API sample, so this table demonstrates JSON ingestion "
            "rather than supporting any analysis. `scripts/fetch_openfda_labels.py` fetches more."
        )
    return notes


def _encounter_notes(enc: pd.DataFrame, checks) -> list[str]:
    failed = [c.check for c in checks if not c.passed]
    return [
        f"{len(enc)} simulated encounters from {enc['encounter_date'].min():%Y-%m-%d} "
        f"to {enc['encounter_date'].max():%Y-%m-%d} across {enc['department'].nunique()} departments.",
        "All checks passed." if not failed else "Checks flagged: " + "; ".join(failed) + ".",
        "These records are made up and contain no patient information.",
    ]


def run_pipeline(paths: Paths, cdc_path: Path, mode: str, today: date | None = None) -> RunResult:
    today = today or date.today()
    run_at = datetime.now(UTC).isoformat(timespec="seconds")
    timings: dict[str, float] = {}
    paths.make_output_dirs()

    with _stage("ingest", timings):
        cdc_raw = read_cdc(cdc_path)
        fda_flat, fda_records = read_fda_labels(paths.fda_json)
        enc_raw = read_encounters_html(paths.encounters_html)
        source_info = [
            describe_source("CDC Chronic Disease Indicators (CSV)", cdc_path, cdc_raw),
            describe_source("openFDA drug labels (JSON)", paths.fda_json, fda_flat),
            describe_source("Simulated clinical encounters (HTML)", paths.encounters_html, enc_raw),
        ]

    with _stage("clean", timings):
        long, clean_log = clean_cdc(cdc_raw)
        fda = clean_fda(fda_records)
        enc = clean_encounters(enc_raw)

    with _stage("validate", timings):
        long, cdc_checks, _ = validate_cdc(long, current_year=today.year)
        checks = cdc_checks + validate_fda(fda) + validate_encounters(enc, today)

    with _stage("transform", timings):
        catalog = build_indicator_catalog(long)
        wide = build_wide_panel(long, catalog)

    overall = long[(long["stratification_category_id1"] == OVERALL) & long["data_value"].notna()]
    stage_counts = pd.DataFrame(
        [
            ("ingest", "CDC rows read", len(cdc_raw)),
            ("validate", "CDC rows after natural-key dedup", len(long)),
            ("validate", "CDC rows with a numeric value", int(long["data_value"].notna().sum())),
            ("transform", "Overall-population rows with a value", len(overall)),
            ("transform", "Indicators in the panel", len(catalog)),
            ("transform", "Wide panel rows (location x period)", len(wide)),
            ("ingest", "openFDA label records", len(fda)),
            ("ingest", "Simulated encounter rows", len(enc)),
        ],
        columns=["stage", "measure", "count"],
    )

    run_row = {
        "run_at": run_at,
        "mode": mode,
        "package_version": __version__,
        "cdc_source": _relative(cdc_path, paths.root),
        "cdc_sha256": source_info[0].sha256,
        "cdc_rows_raw": len(cdc_raw),
        "cdc_rows_clean": len(long),
        "wide_rows": len(wide),
        "wide_indicators": len(catalog),
        "fda_rows": len(fda),
        "encounter_rows": len(enc),
    }
    long_db = long.copy()
    long_db.insert(0, "row_id", range(1, len(long_db) + 1))

    with _stage("load", timings):
        counts = build_warehouse(
            paths.db, paths.schema_sql, WarehouseTables(long_db, wide, catalog, fda, enc, run_row)
        )
        expected = {
            "cdc_raw_clean": len(long),
            "cdc_indicators": len(wide),
            "indicator_catalog": len(catalog),
        }
        for table, n in expected.items():
            if counts[table] != n:
                raise RuntimeError(f"{table}: loaded {counts[table]} rows, expected {n}")

    outputs: list[Path] = []
    with _stage("report", timings):
        availability = value_availability_by_topic(long)
        coverage = panel_coverage(wide, catalog)
        outliers = outliers_by_topic(long)
        strata = rows_by_stratification(long)
        dictionary = describe_indicator_columns(
            data_dictionary(
                {
                    "cdc_raw_clean": long_db,
                    "cdc_indicators": wide,
                    "indicator_catalog": catalog,
                    "fda_drug_labels": fda,
                    "clinical_encounters": enc,
                }
            ),
            catalog,
        )
        table_frames = {
            "stage_counts": stage_counts,
            "validation_checks": checks_to_frame(checks),
            "value_availability_by_topic": availability,
            "panel_coverage": coverage,
            "outliers_by_topic": outliers,
            "rows_by_stratification": strata,
            "indicator_catalog": catalog,
            "data_dictionary": dictionary,
            "cdc_indicators_wide": wide,
        }
        for name, frame in table_frames.items():
            target = paths.tables / f"{name}.csv"
            frame.to_csv(target, index=False)
            outputs.append(target)

        fig_paths = [
            plot_value_availability(availability, paths.figures / "value_availability_by_topic.png"),
            plot_panel_coverage(coverage, paths.figures / "panel_coverage_heatmap.png"),
            plot_state_trends(long, catalog, paths.figures / "trend_mo_il_us.png"),
            plot_state_spread(long, catalog, paths.figures / "state_spread_outliers.png"),
        ]
        outputs += [p for p in fig_paths if p is not None]

        sources = pd.DataFrame(
            [
                {
                    "source": s.name,
                    "file": _relative(s.path, paths.root),
                    "rows": s.rows,
                    "columns": s.columns,
                    "sha256 (first 16)": s.sha256[:16],
                }
                for s in source_info
            ]
        )
        outputs.append(write_data_dictionary_md(dictionary, paths.docs / "data_dictionary.md"))
        ctx = {
            "mode": mode,
            "run_at": run_at,
            "version": __version__,
            "sources": sources,
            "stage_counts": stage_counts,
            "clean_log": clean_log,
            "checks": checks,
            "availability": availability,
            "strata": strata,
            "wide": wide,
            "catalog": catalog,
            "outliers": outliers,
            "fda_notes": _fda_notes(fda),
            "encounter_notes": _encounter_notes(enc, [c for c in checks if c.table == "clinical_encounters"]),
        }
        outputs.append(write_quality_report(paths.docs / "data_quality_report.md", ctx))
        results = run_queries(paths.db, paths.example_queries_sql)
        outputs.append(write_query_results_md(results, paths.docs / "example_query_results.md"))

    with _stage("export", timings):
        stamp = today.strftime("%Y%m%d")
        exports = {
            f"cdc_cdi_clean_{stamp}.csv.gz": long,
            f"cdc_cdi_wide_{stamp}.csv": wide,
            f"openfda_drug_labels_clean_{stamp}.csv": fda.drop(columns=["raw_json"]),
            f"clinical_encounters_{stamp}.csv": enc,
        }
        for name, frame in exports.items():
            frame.to_csv(paths.processed / name, index=False)

    metadata = {
        "run_at": run_at,
        "mode": mode,
        "package_version": __version__,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "sources": [
            {"name": s.name, "file": _relative(s.path, paths.root), "sha256": s.sha256, "rows": s.rows}
            for s in source_info
        ],
        "table_counts": counts,
        "wide_indicator_columns": len(indicator_columns(wide)),
        "checks_flagged": [f"{c.table}: {c.check} ({c.failed})" for c in checks if not c.passed],
        "exports": sorted(exports),
        "stage_seconds": timings,
    }
    (paths.processed / f"export_metadata_{stamp}.json").write_text(json.dumps(metadata, indent=2))
    meta_path = paths.out / "outputs" / "run_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2) + "\n")
    outputs.append(meta_path)
    return RunResult(mode=mode, db_path=paths.db, table_counts=counts, metadata=metadata, outputs=outputs)
