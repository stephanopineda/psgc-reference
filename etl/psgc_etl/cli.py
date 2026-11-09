"""Command-line interface for the PSGC ETL."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from psgc_etl.extract import (
    compare_workbook_schemas,
    profile_workbook,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="psgc-etl",
        description="Inspect and profile PSA PSGC publication workbooks.",
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

    parser.error("Unsupported command.")
    return 2
