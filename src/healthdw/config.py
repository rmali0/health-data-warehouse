"""Paths and constants shared by the pipeline.

All paths are derived from two directories: the repository root (where the raw
inputs and SQL files live) and an output root (where figures, tables, docs, the
processed exports and the SQLite file are written). A full run writes into the
repository itself; a sample run writes into build/sample so it never overwrites
the committed results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CDC_FILENAME = "cdc_cdi.csv"
CDC_SAMPLE_FILENAME = "cdc_cdi_sample.csv.gz"
FDA_FILENAME = "openfda_drug_labels.json"
ENCOUNTERS_FILENAME = "simulated_clinical_encounters.html"
DB_FILENAME = "health_dw.db"

# The CDC download page for U.S. Chronic Disease Indicators (dataset g4ie-h725).
CDC_DATASET_URL = "https://data.cdc.gov/api/views/g4ie-h725/rows.csv?accessType=DOWNLOAD"


@dataclass(frozen=True)
class Paths:
    root: Path
    out: Path

    @classmethod
    def for_run(cls, root: Path | str = ".", out: Path | str | None = None) -> Paths:
        root = Path(root).resolve()
        return cls(root=root, out=Path(out).resolve() if out else root)

    # Inputs, always read from the repository.
    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def sample(self) -> Path:
        return self.root / "data" / "sample"

    @property
    def sql(self) -> Path:
        return self.root / "sql"

    @property
    def schema_sql(self) -> Path:
        return self.sql / "schema.sql"

    @property
    def example_queries_sql(self) -> Path:
        return self.sql / "example_queries.sql"

    @property
    def fda_json(self) -> Path:
        return self.raw / FDA_FILENAME

    @property
    def encounters_html(self) -> Path:
        return self.raw / ENCOUNTERS_FILENAME

    @property
    def cdc_sample(self) -> Path:
        return self.sample / CDC_SAMPLE_FILENAME

    # Outputs, written under the output root.
    @property
    def processed(self) -> Path:
        return self.out / "data" / "processed"

    @property
    def db(self) -> Path:
        return self.processed / DB_FILENAME

    @property
    def figures(self) -> Path:
        return self.out / "outputs" / "figures"

    @property
    def tables(self) -> Path:
        return self.out / "outputs" / "tables"

    @property
    def docs(self) -> Path:
        return self.out / "docs"

    def make_output_dirs(self) -> None:
        for p in (self.processed, self.figures, self.tables, self.docs):
            p.mkdir(parents=True, exist_ok=True)

    def find_cdc_raw(self) -> Path | None:
        """Return the full CDC file if it has been downloaded (plain or gzipped)."""
        for name in (CDC_FILENAME, CDC_FILENAME + ".gz"):
            candidate = self.raw / name
            if candidate.exists():
                return candidate
        return None
