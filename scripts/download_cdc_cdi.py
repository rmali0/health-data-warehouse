"""Download the CDC U.S. Chronic Disease Indicators export (dataset g4ie-h725).

    python scripts/download_cdc_cdi.py [--dest data/raw/cdc_cdi.csv] [--force]

The file is about 100 MB. It is written to a temporary file first and only
moved into place after the header has been checked, so an interrupted
download never leaves a truncated CSV where the pipeline would read it.
CDC revises this dataset, so a new download can differ from the copy behind
the committed outputs; the SHA-256 printed at the end can be compared with
outputs/run_metadata.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

URL = "https://data.cdc.gov/api/views/g4ie-h725/rows.csv?accessType=DOWNLOAD"
EXPECTED_COLUMNS = {
    "YearStart",
    "YearEnd",
    "LocationAbbr",
    "Topic",
    "QuestionID",
    "DataValueAlt",
    "DataValueTypeID",
    "StratificationCategoryID1",
    "StratificationID1",
}
CHUNK = 1 << 20


def download(url: str, dest: Path, timeout: float = 60.0) -> str:
    """Stream url to dest; return the SHA-256 of the bytes written."""
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "healthdw-download/2.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response, open(dest, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            size = f"{done / 1e6:,.0f} MB" + (f" of {total / 1e6:,.0f} MB" if total else "")
            print(f"\r  {size}", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    return digest.hexdigest()


def check_header(path: Path) -> None:
    with open(path, newline="", encoding="utf-8") as fh:
        header = set(next(csv.reader(fh)))
    missing = EXPECTED_COLUMNS - header
    if missing:
        raise SystemExit(f"Downloaded file is missing expected columns: {sorted(missing)}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=root / "data" / "raw" / "cdc_cdi.csv")
    parser.add_argument("--url", default=URL)
    parser.add_argument("--force", action="store_true", help="replace an existing file")
    args = parser.parse_args()

    if args.dest.exists() and not args.force:
        print(f"{args.dest} already exists; use --force to download again.")
        return
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {args.url}")
    with tempfile.NamedTemporaryFile(dir=args.dest.parent, suffix=".part", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        sha = download(args.url, tmp_path)
        check_header(tmp_path)
        shutil.move(tmp_path, args.dest)
    finally:
        tmp_path.unlink(missing_ok=True)
    print(f"Saved {args.dest} ({args.dest.stat().st_size / 1e6:,.1f} MB), sha256 {sha}")


if __name__ == "__main__":
    main()
