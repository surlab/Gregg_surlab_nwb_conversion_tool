"""One-command SurLab -> NWB conversion plus validation matrix.

Default: integrated conversion (all implemented handlers) + discovery validation.
``--stage`` is a dev-only filter on conversion_table ``stage`` column.
``--validate-only`` skips NWB write. See for_cursor/task2_implementation_decisions_and_answers.txt §E.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.session_record import discover_session_dirs, load_session_record, nwb_output_basename
from src.surlab_paths import dataset_id_from_dir
from src.sur_to_nwb import ConversionConfig, convert_surlab_session_to_nwb
from src.validator import (
    ValidationConfig,
    build_discovery_ledger,
    build_session_validation_matrix,
    write_discovery_ledger_csv,
    write_validation_matrix_csv,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert one SurLab session to NWB.")
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    parser.add_argument(
        "--session-dir",
        required=False,
        type=Path,
        help="Path to one session directory. If omitted, loops over all session subfolders.",
    )
    parser.add_argument(
        "--conversion-table",
        default=Path("sur_nwb_conversion_table.csv"),
        type=Path,
        help="Path to conversion table CSV.",
    )
    parser.add_argument(
        "--output-nwb",
        required=False,
        type=Path,
        help="Output NWB file path for single-session mode.",
    )
    parser.add_argument(
        "--output-matrix",
        default=None,
        type=Path,
        help="Optional dataset-level validation matrix path. Defaults to <dataset-dir>/session_validation_matrix.csv.",
    )
    parser.add_argument(
        "--stage",
        default=None,
        type=int,
        help="Dev-only filter: include table rows with stage <= this value.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run discovery validation only; skip NWB writing.",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        type=Path,
        help="Optional log file path. Defaults to <session-dir>/runlog.txt.",
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


def _merge_matrix_rows(aggregate_rows: List[Dict[str, str]], new_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    aggregate_by_check = {row["check"]: dict(row) for row in aggregate_rows}
    for row in new_rows:
        check_name = row["check"]
        if check_name not in aggregate_by_check:
            aggregate_by_check[check_name] = {"check": check_name}
        for key, value in row.items():
            if key != "check":
                aggregate_by_check[check_name][key] = value
    return [aggregate_by_check[key] for key in sorted(aggregate_by_check.keys())]


def main() -> None:
    args = parse_args()
    dataset_matrix_path = args.output_matrix or (args.dataset_dir / "session_validation_matrix.csv")
    if args.session_dir is not None:
        session_dirs = [args.session_dir]
    else:
        session_dirs = discover_session_dirs(args.dataset_dir)
        if not session_dirs:
            raise ValueError(f"No session subdirectories found in dataset_dir: {args.dataset_dir}")

    aggregate_matrix_rows: List[Dict[str, str]] = []
    for session_dir in session_dirs:
        log_path = args.log_file or (session_dir / "runlog.txt")
        _configure_logging(log_path)
        logger = logging.getLogger(__name__)
        logger.info("Processing session: %s", session_dir)

        validation_config = ValidationConfig(
            dataset_dir=args.dataset_dir,
            session_dir=session_dir,
            conversion_table_path=args.conversion_table,
            dev_max_stage=args.stage,
            output_matrix_csv=session_dir / "session_validation_report.csv",
            output_discovery_csv=session_dir / "conversion_table_discovered.csv",
        )
        matrix_rows = build_session_validation_matrix(validation_config)
        session_report_path = session_dir / "session_validation_report.csv"
        write_validation_matrix_csv(matrix_rows, session_report_path)
        logger.info("Session validation report written: %s", session_report_path)

        ledger_rows = build_discovery_ledger(validation_config)
        ledger_path = write_discovery_ledger_csv(
            ledger_rows,
            session_dir / "conversion_table_discovered.csv",
        )
        logger.info("Discovery ledger written: %s", ledger_path)

        aggregate_matrix_rows = _merge_matrix_rows(aggregate_matrix_rows, matrix_rows)

        if args.validate_only:
            continue

        if args.session_dir is not None and args.output_nwb is not None:
            output_nwb_path = args.output_nwb
        else:
            dataset_id = dataset_id_from_dir(args.dataset_dir)
            session_record = load_session_record(args.dataset_dir, session_dir, dataset_id)
            output_nwb_path = session_dir / f"{nwb_output_basename(session_record)}.nwb"

        conversion_config = ConversionConfig(
            dataset_dir=args.dataset_dir,
            session_dir=session_dir,
            conversion_table_path=args.conversion_table,
            output_nwb_path=output_nwb_path,
            dev_max_stage=args.stage,
        )
        result = convert_surlab_session_to_nwb(conversion_config)
        logger.info("NWB written: %s", result.output_nwb_path)
        for warning in result.warnings:
            logger.warning(warning)
        for gap in result.table_gaps:
            logger.warning("Table gap: %s", gap)

    matrix_path = write_validation_matrix_csv(aggregate_matrix_rows, dataset_matrix_path)
    print(f"Validation matrix written: {matrix_path}")
    if args.validate_only:
        print("Validation-only mode complete.")


if __name__ == "__main__":
    main()
