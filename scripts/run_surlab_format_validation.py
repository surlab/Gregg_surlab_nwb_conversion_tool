"""Validate SurLab dataset format conventions (presence, naming, types, consistency)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.session_record import discover_session_dirs
from src.validator import (
    ValidationConfig,
    collect_table_gaps,
    validate_session_format,
    write_convention_report_csv,
    write_format_summary_csv,
    write_validation_matrix_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate SurLab format conventions for one dataset (not NWB / not round-trip)."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    parser.add_argument(
        "--session-dir",
        required=False,
        type=Path,
        help="Optional single session directory. Default: all sessions under dataset-dir.",
    )
    parser.add_argument(
        "--conversion-table",
        default=Path("sur_nwb_conversion_table.csv"),
        type=Path,
        help="Conversion table CSV (ground truth for required fields and types).",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        type=Path,
        help="Defaults to <dataset-dir>/runlog_surlab_format_validation.txt",
    )
    return parser.parse_args()


def _configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w"), logging.StreamHandler()],
        force=True,
    )


def main() -> int:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    log_path = args.log_file or (dataset_dir / "runlog_surlab_format_validation.txt")
    _configure_logging(log_path)
    logger = logging.getLogger(__name__)

    logger.info("Starting SurLab format validation.")
    logger.info("Dataset directory: %s", dataset_dir)
    logger.info("Conversion table: %s", args.conversion_table)

    if args.session_dir is not None:
        session_dirs = [args.session_dir.resolve()]
    else:
        session_dirs = discover_session_dirs(dataset_dir)
        if not session_dirs:
            logger.error("No session subdirectories found in %s", dataset_dir)
            return 2

    results = []
    aggregate_matrix: List[dict] = []
    all_gaps: List[str] = []

    for session_dir in session_dirs:
        logger.info("Validating session: %s", session_dir.name)
        config = ValidationConfig(
            dataset_dir=dataset_dir,
            session_dir=session_dir,
            conversion_table_path=args.conversion_table,
        )
        result = validate_session_format(config)
        results.append(result)

        report_path = session_dir / "surlab_format_validation_report.csv"
        write_convention_report_csv(result.issues, report_path)
        write_validation_matrix_csv(result.matrix_rows, session_dir / "session_validation_report.csv")
        logger.info(
            "Session %s: fails=%d warns=%d report=%s",
            result.session_key,
            result.fail_count,
            result.warn_count,
            report_path,
        )
        for gap in collect_table_gaps(result.issues):
            if gap not in all_gaps:
                all_gaps.append(gap)

        # Merge matrix columns across sessions.
        if not aggregate_matrix:
            aggregate_matrix = [dict(row) for row in result.matrix_rows]
        else:
            by_check = {row["check"]: dict(row) for row in aggregate_matrix}
            for row in result.matrix_rows:
                check = row["check"]
                if check not in by_check:
                    by_check[check] = {"check": check}
                for key, value in row.items():
                    if key != "check":
                        by_check[check][key] = value
            aggregate_matrix = [by_check[key] for key in sorted(by_check.keys())]

    summary_path = dataset_dir / "surlab_format_validation_summary.csv"
    write_format_summary_csv(results, summary_path)
    matrix_path = dataset_dir / "session_validation_matrix.csv"
    write_validation_matrix_csv(aggregate_matrix, matrix_path)

    total_fails = sum(result.fail_count for result in results)
    total_warns = sum(result.warn_count for result in results)

    print()
    print("=== SurLab format validation complete ===")
    print(f"Dataset directory: {dataset_dir}")
    print(f"Summary: {summary_path}")
    print(f"Presence matrix: {matrix_path}")
    print(f"Log file: {log_path}")
    print(f"Total fails: {total_fails}  Total warns: {total_warns}")
    for result in results:
        print(f"  {result.session_key}: fails={result.fail_count}, warns={result.warn_count}")
    if all_gaps:
        print()
        print("Table gaps (consider Task 1 updates):")
        for gap in all_gaps:
            print(f"  - {gap}")

    logger.info("SurLab format validation completed. fails=%d warns=%d", total_fails, total_warns)
    return 1 if total_fails > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
