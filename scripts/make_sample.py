"""Build the small CDC fixture in data/sample/ from the full download.

The fixture keeps every column and the original row order, restricted to a
fixed set of locations, indicators and strata, so tests and the --sample run
exercise the same code paths as the full file (thousands separators,
suppressed values, multi-year periods, several strata) in about a second.

    python scripts/make_sample.py [--src data/raw/cdc_cdi.csv]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
from pathlib import Path

LOCATIONS = {"US", "MO", "IL", "KS", "IA", "NE", "KY", "TN", "AR", "OK", "IN", "WI", "MN", "CA", "NY", "TX"}
QUESTIONS = {"DIA01", "NPW14", "TOB04", "NPW06", "MEN02", "HEA01", "ALC06", "SDH09", "CAN07"}
STRATA = {"OVERALL", "SEX"}
# Race/ethnicity rows for one indicator, to keep suppressed subgroup estimates in the fixture.
RACE_QUESTIONS = {"DIA01"}


def keep(row: dict) -> bool:
    if row["LocationAbbr"] not in LOCATIONS or row["QuestionID"] not in QUESTIONS:
        return False
    strat = row["StratificationCategoryID1"]
    return strat in STRATA or (strat == "RACE" and row["QuestionID"] in RACE_QUESTIONS)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=root / "data" / "raw" / "cdc_cdi.csv")
    parser.add_argument("--dest", type=Path, default=root / "data" / "sample" / "cdc_cdi_sample.csv.gz")
    args = parser.parse_args()

    with open(args.src, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = [r for r in reader if keep(r)]
        fields = reader.fieldnames

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the gzip bytes identical across rebuilds.
    with open(args.dest, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(buffer.getvalue().encode("utf-8"))
    print(f"Wrote {len(rows):,} rows to {args.dest} ({args.dest.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
