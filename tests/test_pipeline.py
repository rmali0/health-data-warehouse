import json

from healthdw.cli import main

from conftest import REPO


def test_sample_run_writes_outputs(sample_run):
    paths, result = sample_run
    for name in (
        "value_availability_by_topic",
        "panel_coverage_heatmap",
        "trend_mo_il_us",
        "state_spread_outliers",
    ):
        assert (paths.figures / f"{name}.png").stat().st_size > 10_000
    for name in ("data_quality_report", "data_dictionary", "example_query_results"):
        assert (paths.docs / f"{name}.md").exists()
    meta = json.loads((paths.out / "outputs" / "run_metadata.json").read_text())
    assert meta["mode"] == "sample"
    assert meta["sources"][0]["rows"] == 4256
    assert any(p.name.startswith("cdc_cdi_clean_2026") for p in paths.processed.iterdir())


def test_example_queries_return_rows(sample_run):
    paths, _ = sample_run
    text = (paths.docs / "example_query_results.md").read_text()
    assert text.count("## ") == 6
    assert "| year | missouri | illinois | us |" in text


def test_cli_reports_missing_cdc_file(tmp_path, caplog):
    code = main(["run", "--root", str(REPO), "--cdc", str(tmp_path / "missing.csv"), "--out", str(tmp_path)])
    assert code == 2
    assert "download_cdc_cdi.py" in caplog.text


def test_markdown_table_formatting():
    import pandas as pd

    from healthdw.report import markdown_table

    text = markdown_table(pd.DataFrame({"year": [2019], "rows": [12345], "pct": [1.25], "note": ["a|b"]}))
    assert text.splitlines()[2] == "| 2019 | 12,345 | 1.2 | a\\|b |"
