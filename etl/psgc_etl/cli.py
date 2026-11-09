"""Command-line interface for the PSGC ETL."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from psgc_etl.extract import (
    compare_workbook_schemas,
    profile_workbook,
)
from psgc_etl.load.d1_loader import (
    DEFAULT_SOURCE_DIR,
    RELEASES,
    discover_release_workbooks,
    load_releases,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="psgc-etl",
        description="Inspect, validate, compare, and load PSA PSGC publications.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Profile one or more .xlsx workbooks without modifying them.",
    )
    inspect_parser.add_argument(
        "workbooks",
        nargs="+",
        type=Path,
        help="Workbook paths to inspect.",
    )
    inspect_parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path instead of stdout.",
    )

    load_parser = subparsers.add_parser(
        "load-d1",
        help="Validate and load supported PSA releases into local Wrangler D1.",
    )
    release_selection = load_parser.add_mutually_exclusive_group(
        required=True
    )
    release_selection.add_argument(
        "--all",
        action="store_true",
        help="Load all supported PSA workbooks from the source directory.",
    )
    release_selection.add_argument(
        "--release",
        choices=sorted({
            metadata["release_id"] for metadata in RELEASES.values()
        }),
        help="Load one specific supported release by release ID.",
    )
    load_parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"PSA source directory (default: {DEFAULT_SOURCE_DIR}).",
    )
    load_parser.add_argument(
        "--database-path",
        type=Path,
        help="Explicit local Wrangler D1 SQLite file path.",
    )
    load_parser.add_argument(
        "--actor",
        default="local-etl",
        help="Audit actor recorded for the import (default: local-etl).",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        try:
            profiles = [
                profile_workbook(path)
                for path in args.workbooks
            ]

            report = {
                "report_type": "psgc_workbook_profile",
                "report_version": "1.0",
                "workbooks": profiles,
                "schema_comparisons": compare_workbook_schemas(profiles),
            }

            rendered = json.dumps(
                report,
                indent=2,
                ensure_ascii=False,
            ) + "\n"

            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
                print(f"Profile report written to: {args.output}")
            else:
                sys.stdout.write(rendered)

            return 0

        except (OSError, ValueError, KeyError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2

    if args.command == "load-d1":
        try:
            if args.all:
                workbooks = discover_release_workbooks(args.source_dir)
            else:
                filename = next(
                    filename
                    for filename, metadata in RELEASES.items()
                    if metadata["release_id"] == args.release
                )
                workbooks = [args.source_dir / filename]

            results = load_releases(
                workbooks,
                database_path=args.database_path,
                actor=args.actor,
            )

            print(
                json.dumps(
                    {
                        "operation": "load-d1",
                        "database": str(
                            args.database_path or "Wrangler local D1"
                        ),
                        "results": results,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        except (
            OSError,
            ValueError,
            KeyError,
            RuntimeError,
            sqlite3.Error,
        ) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2

    parser.error("Unsupported command.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
