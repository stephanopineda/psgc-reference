"""Command-line interface for the PSGC ETL."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from psgc_etl.compare import (
    compare_hierarchy_edges,
    compare_normalized_releases,
)
from psgc_etl.extract import (
    compare_workbook_schemas,
    profile_workbook,
)
from psgc_etl.extract.psgc_extractor import extract_psgc_records
from psgc_etl.hierarchy import build_hierarchy, validate_hierarchy
from psgc_etl.load.d1_loader import (
    DEFAULT_SOURCE_DIR,
    RELEASES,
    discover_release_workbooks,
    load_hierarchies,
    load_releases,
)
from psgc_etl.transform.normalizer import normalize_psgc_records

DEFAULT_HIERARCHY_OUTPUT_DIR = Path("data/processed/hierarchy")


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
    release_selection = load_parser.add_mutually_exclusive_group(required=True)
    release_selection.add_argument(
        "--all",
        action="store_true",
        help="Load all supported PSA workbooks from the source directory.",
    )
    release_selection.add_argument(
        "--release",
        choices=sorted(metadata["release_id"] for metadata in RELEASES.values()),
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

    hierarchy_load_parser = subparsers.add_parser(
        "load-hierarchy-d1",
        help="Build, validate, and persist release-specific hierarchy into local D1.",
    )
    hierarchy_load_selection = hierarchy_load_parser.add_mutually_exclusive_group(
        required=True
    )
    hierarchy_load_selection.add_argument(
        "--all",
        action="store_true",
        help="Load hierarchy for all supported imported releases.",
    )
    hierarchy_load_selection.add_argument(
        "--release",
        choices=sorted(metadata["release_id"] for metadata in RELEASES.values()),
        help="Load hierarchy for one specific release ID.",
    )
    hierarchy_load_parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"PSA source directory (default: {DEFAULT_SOURCE_DIR}).",
    )
    hierarchy_load_parser.add_argument(
        "--database-path",
        type=Path,
        help="Explicit local Wrangler D1 SQLite file path.",
    )

    hierarchy_parser = subparsers.add_parser(
        "build-hierarchy",
        help="Build and validate proposed release-specific hierarchy review reports.",
    )
    hierarchy_selection = hierarchy_parser.add_mutually_exclusive_group(required=True)
    hierarchy_selection.add_argument(
        "--all",
        action="store_true",
        help="Build reports for all supported PSA releases.",
    )
    hierarchy_selection.add_argument(
        "--release",
        choices=sorted(metadata["release_id"] for metadata in RELEASES.values()),
        help="Build a report for one specific release.",
    )
    hierarchy_parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"PSA source directory (default: {DEFAULT_SOURCE_DIR}).",
    )
    hierarchy_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_HIERARCHY_OUTPUT_DIR,
        help=(f"Directory for JSON review reports (default: {DEFAULT_HIERARCHY_OUTPUT_DIR})."),
    )

    comparison_parser = subparsers.add_parser(
        "compare-releases",
        help="Compare consecutive PSA releases by code and hierarchy.",
    )
    comparison_parser.add_argument(
        "--all",
        action="store_true",
        required=True,
        help="Compare every consecutive pair of supported releases.",
    )
    comparison_parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"PSA source directory (default: {DEFAULT_SOURCE_DIR}).",
    )
    comparison_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/comparisons"),
        help="Directory for JSON comparison reports.",
    )

    return parser


def _build_hierarchy_report(
    workbook: Path,
    release_id: str,
    publication_date: str,
) -> dict:
    """Extract, normalize, build, and independently validate one release."""
    extraction = extract_psgc_records(workbook)
    normalized = normalize_psgc_records(extraction)

    hierarchy = build_hierarchy(normalized, release_id)
    validation = validate_hierarchy(normalized, hierarchy)

    return {
        "report_type": "psgc_hierarchy_review",
        "report_version": "1.0",
        "release": {
            "release_id": release_id,
            "publication_date": publication_date,
            "source_workbook": workbook.name,
        },
        "summary": {
            "record_count": hierarchy["record_count"],
            "proposed_edge_count": hierarchy["edge_count"],
            "builder_finding_count": hierarchy["finding_count"],
            "validated_path_count": validation["validated_path_count"],
            "maximum_depth": validation["maximum_depth"],
            "validator_error_count": validation["error_count"],
            "is_valid": (hierarchy["finding_count"] == 0 and validation["is_valid"]),
            "level_counts": hierarchy["level_counts"],
            "rule_counts": hierarchy["rule_counts"],
        },
        "edges": hierarchy["edges"],
        "builder_findings": hierarchy["findings"],
        "validation": validation,
    }


def _build_comparison_release_data(
    workbook: Path,
    release_id: str,
) -> dict:
    """Extract, normalize, build, and validate one release for comparison."""
    extraction = extract_psgc_records(workbook)
    normalized = normalize_psgc_records(extraction)
    hierarchy = build_hierarchy(normalized, release_id)
    validation = validate_hierarchy(normalized, hierarchy)

    return {
        "normalized": normalized,
        "hierarchy": hierarchy,
        "validation": validation,
        "source_workbook": workbook.name,
    }


def _build_release_comparison_report(
    previous_release_id: str,
    current_release_id: str,
    previous_data: dict,
    current_data: dict,
) -> dict:
    """Combine exact-code record and proposed-hierarchy comparisons."""
    record_comparison = compare_normalized_releases(
        previous_data["normalized"],
        current_data["normalized"],
        previous_release_id=previous_release_id,
        current_release_id=current_release_id,
    )

    hierarchy_comparison = compare_hierarchy_edges(
        previous_data["hierarchy"]["edges"],
        current_data["hierarchy"]["edges"],
        previous_release_id=previous_release_id,
        current_release_id=current_release_id,
    )

    previous_validation = previous_data["validation"]
    current_validation = current_data["validation"]

    return {
        "report_type": "psgc_release_comparison",
        "report_version": "1.0",
        "comparison": {
            "previous_release_id": previous_release_id,
            "current_release_id": current_release_id,
            "policy": {
                "record_identity_key": "EXACT_10_DIGIT_PSGC_CODE",
                "continuity_evidence": "CORRESPONDENCE_CODE_REVIEW_REQUIRED",
                "removal_classification": "REMOVED_FROM_RELEASE",
                "abolition_inference": False,
                "hierarchy_comparison_key": "CHILD_PSGC_CODE",
            },
        },
        "record_comparison": record_comparison,
        "hierarchy_comparison": hierarchy_comparison,
        "hierarchy_validation": {
            "previous_release": {
                "is_valid": previous_validation["is_valid"],
                "error_count": previous_validation["error_count"],
                "validated_path_count": previous_validation["validated_path_count"],
                "maximum_depth": previous_validation["maximum_depth"],
                "builder_finding_count": previous_data["hierarchy"]["finding_count"],
            },
            "current_release": {
                "is_valid": current_validation["is_valid"],
                "error_count": current_validation["error_count"],
                "validated_path_count": current_validation["validated_path_count"],
                "maximum_depth": current_validation["maximum_depth"],
                "builder_finding_count": current_data["hierarchy"]["finding_count"],
            },
        },
        "sources": {
            "previous_workbook": previous_data["source_workbook"],
            "current_workbook": current_data["source_workbook"],
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        try:
            profiles = [profile_workbook(path) for path in args.workbooks]

            report = {
                "report_type": "psgc_workbook_profile",
                "report_version": "1.0",
                "workbooks": profiles,
                "schema_comparisons": compare_workbook_schemas(profiles),
            }

            rendered = (
                json.dumps(
                    report,
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n"
            )

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

    if args.command == "compare-releases":
        try:
            selected_releases = list(RELEASES.items())

            if len(selected_releases) < 2:
                raise ValueError("At least two supported releases are required.")

            args.output_dir.mkdir(parents=True, exist_ok=True)

            # Build each release only once, even though adjacent comparisons
            # reuse the same release as the previous/current input.
            release_data = {}
            for filename, metadata in selected_releases:
                release_id = metadata["release_id"]
                workbook = args.source_dir / filename

                print(f"Preparing {release_id}: {workbook}")
                release_data[release_id] = _build_comparison_release_data(
                    workbook,
                    release_id,
                )

            results = []
            all_hierarchies_valid = True

            for index in range(len(selected_releases) - 1):
                _, previous_metadata = selected_releases[index]
                _, current_metadata = selected_releases[index + 1]

                previous_id = previous_metadata["release_id"]
                current_id = current_metadata["release_id"]

                report = _build_release_comparison_report(
                    previous_id,
                    current_id,
                    release_data[previous_id],
                    release_data[current_id],
                )

                output_name = f"{previous_id}-to-{current_id}.json"
                output_path = args.output_dir / output_name
                output_path.write_text(
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\\n",
                    encoding="utf-8",
                )

                record_summary = report["record_comparison"]["summary"]
                hierarchy_summary = report["hierarchy_comparison"]["summary"]
                validation = report["hierarchy_validation"]

                pair_valid = (
                    validation["previous_release"]["is_valid"]
                    and validation["current_release"]["is_valid"]
                )
                all_hierarchies_valid = all_hierarchies_valid and pair_valid

                results.append(
                    {
                        "previous_release_id": previous_id,
                        "current_release_id": current_id,
                        "output": str(output_path),
                        "record_summary": record_summary,
                        "hierarchy_summary": hierarchy_summary,
                        "hierarchies_valid": pair_valid,
                    }
                )

                print(
                    f"{previous_id} -> {current_id}: "
                    f"{record_summary['added_count']} added records, "
                    f"{record_summary['removed_count']} removed records, "
                    f"{record_summary['changed_count']} changed records"
                )
                print(
                    f"  Hierarchy: "
                    f"{hierarchy_summary['changed_parent_count']} changed parents, "
                    f"{hierarchy_summary['added_edge_count']} added edges, "
                    f"{hierarchy_summary['removed_edge_count']} removed edges"
                )
                print(f"  Report: {output_path}")

            print()
            print(
                json.dumps(
                    {
                        "operation": "compare-releases",
                        "output_dir": str(args.output_dir),
                        "all_hierarchies_valid": all_hierarchies_valid,
                        "results": results,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )

            return 0 if all_hierarchies_valid else 1

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            RuntimeError,
        ) as error:
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
                        "database": str(args.database_path or "Wrangler local D1"),
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

    if args.command == "load-hierarchy-d1":
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

            results = load_hierarchies(
                workbooks,
                database_path=args.database_path,
            )

            print(
                json.dumps(
                    {
                        "operation": "load-hierarchy-d1",
                        "database": str(args.database_path or "Wrangler local D1"),
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

    if args.command == "build-hierarchy":
        try:
            if args.all:
                selected_releases = list(RELEASES.items())
            else:
                selected_releases = [
                    (filename, metadata)
                    for filename, metadata in RELEASES.items()
                    if metadata["release_id"] == args.release
                ]

            args.output_dir.mkdir(parents=True, exist_ok=True)

            results = []
            all_valid = True

            for filename, metadata in selected_releases:
                workbook = args.source_dir / filename
                release_id = metadata["release_id"]

                report = _build_hierarchy_report(
                    workbook,
                    release_id,
                    metadata["publication_date"],
                )

                output_path = args.output_dir / f"hierarchy-{release_id}.json"
                rendered = (
                    json.dumps(
                        report,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                output_path.write_text(rendered, encoding="utf-8")

                summary = report["summary"]
                all_valid = all_valid and summary["is_valid"]

                results.append(
                    {
                        "release_id": release_id,
                        "output": str(output_path),
                        **summary,
                    }
                )

                print(
                    f"{release_id}: "
                    f"{summary['record_count']:,} records, "
                    f"{summary['proposed_edge_count']:,} proposed edges, "
                    f"{summary['builder_finding_count']} builder findings, "
                    f"{summary['validator_error_count']} validator errors, "
                    f"{'PASS' if summary['is_valid'] else 'FAIL'}"
                )
                print(f"  Report: {output_path}")

            print()
            print(
                json.dumps(
                    {
                        "operation": "build-hierarchy",
                        "output_dir": str(args.output_dir),
                        "all_valid": all_valid,
                        "results": results,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )

            return 0 if all_valid else 1

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
