"""Command line interface: `healthdw run` and `healthdw query`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .config import Paths
from .ingest import SchemaError, SourceMissingError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="healthdw", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the full pipeline and rebuild the warehouse")
    run.add_argument(
        "--sample",
        action="store_true",
        help="use the bundled CDC sample (data/sample) and write to build/sample",
    )
    run.add_argument("--cdc", type=Path, help="path to a CDC CDI CSV (default: data/raw/cdc_cdi.csv)")
    run.add_argument("--root", type=Path, default=Path("."), help="repository root (default: .)")
    run.add_argument(
        "--out", type=Path, help="output root (default: repo root, or build/sample with --sample)"
    )

    query = sub.add_parser("query", help="run the statements in a SQL file against the warehouse")
    query.add_argument("sql_file", type=Path, nargs="?", default=Path("sql/example_queries.sql"))
    query.add_argument("--db", type=Path, default=Path("data/processed/health_dw.db"))
    query.add_argument("--max-rows", type=int, default=20)
    return parser


def _run(args: argparse.Namespace) -> int:
    from .pipeline import run_pipeline

    root = args.root.resolve()
    out = args.out or (root / "build" / "sample" if args.sample else root)
    paths = Paths.for_run(root, out)
    if args.cdc:
        cdc_path = args.cdc
    elif args.sample:
        cdc_path = paths.cdc_sample
    else:
        cdc_path = paths.find_cdc_raw() or paths.raw / "cdc_cdi.csv"

    try:
        result = run_pipeline(paths, cdc_path, mode="sample" if args.sample else "full")
    except (SourceMissingError, SchemaError) as exc:
        logging.getLogger("healthdw").error("%s", exc)
        return 2

    print(f"Warehouse: {result.db_path}")
    for table, n in result.table_counts.items():
        print(f"  {table:<20} {n:>9,} rows")
    print(f"Wrote {len(result.outputs)} report files under {paths.out}")
    return 0


def _query(args: argparse.Namespace) -> int:
    from .load import run_queries
    from .report import markdown_table

    if not args.db.exists():
        print(f"{args.db} not found. Build it first with `python -m healthdw run`.", file=sys.stderr)
        return 2
    for title, _sql, df in run_queries(args.db, args.sql_file):
        print(f"\n## {title or 'query'}\n")
        print(markdown_table(df.head(args.max_rows)))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    args = _build_parser().parse_args(argv)
    return _run(args) if args.command == "run" else _query(args)
