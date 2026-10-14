"""Fetch drug label records from the openFDA API (https://open.fda.gov/apis/drug/label/).

    python scripts/fetch_openfda_labels.py [--limit 100] [--search 'openfda.product_type:"HUMAN PRESCRIPTION DRUG"']

Writes the raw API response to data/raw/openfda_drug_labels.json, the file
the pipeline reads. The committed copy is a one-record sample; fetching more
replaces it. Without an API key openFDA allows 1,000 requests a day, and one
request returns at most 1,000 records. Set OPENFDA_API_KEY to use a key.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://api.fda.gov/drug/label.json"


def build_url(limit: int, search: str | None, api_key: str | None) -> str:
    params = {"limit": str(limit)}
    if search:
        params["search"] = search
    if api_key:
        params["api_key"] = api_key
    return f"{BASE_URL}?{urllib.parse.urlencode(params)}"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=100, help="records to fetch (1 to 1000)")
    parser.add_argument("--search", help="openFDA search expression")
    parser.add_argument("--dest", type=Path, default=root / "data" / "raw" / "openfda_drug_labels.json")
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        raise SystemExit("--limit must be between 1 and 1000")

    url = build_url(args.limit, args.search, os.environ.get("OPENFDA_API_KEY"))
    request = urllib.request.Request(url, headers={"User-Agent": "healthdw-fetch/2.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    records = payload.get("results") or []
    if not records:
        raise SystemExit("openFDA returned no results")
    args.dest.parent.mkdir(parents=True, exist_ok=True)
    args.dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} label records to {args.dest}")


if __name__ == "__main__":
    main()
