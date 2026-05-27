"""One-command stage-1 SurLab -> NWB conversion plus validation matrix."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.sur_to_nwb import ConversionConfig, convert_surlab_session_to_nwb
from src.validator import ValidationConfig, build_session_validation_matrix, write_validation_matrix_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run stage-1 SurLab -> NWB conversion.")
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    parser.add_argument(
        "--session-dir",
        required=False,
        type=Path,
        help="Path to one session directory. If omitted, loops over all session subfolders.",
    )
    parser.add_argument(
        "--conversion-table",
        default=Path("conversion_table.csv"),
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
    parser.add_argument("--stage", default=1, type=int, help="Current conversion stage.")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run discovery validation only; skip NWB writing.",
    )
    return parser.parse_args()


def _discover_session_dirs(dataset_dir: Path) -> List[Path]:
    return sorted([path for path in dataset_dir.iterdir() if path.is_dir()])


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
        session_dirs = _discover_session_dirs(args.dataset_dir)
        if not session_dirs:
            raise ValueError(f"No session subdirectories found in dataset_dir: {args.dataset_dir}")

    aggregate_matrix_rows: List[Dict[str, str]] = []
    for session_dir in session_dirs:
        validation_config = ValidationConfig(
            dataset_dir=args.dataset_dir,
            session_dir=session_dir,
            conversion_table_path=args.conversion_table,
            current_stage=args.stage,
            output_matrix_csv=session_dir / "session_validation_report.csv",
        )
        matrix_rows = build_session_validation_matrix(validation_config)
        # One report per session directory for quick inspection.
        session_report_path = session_dir / "session_validation_report.csv"
        write_validation_matrix_csv(matrix_rows, session_report_path)
        print(f"Session validation report written: {session_report_path}")
        aggregate_matrix_rows = _merge_matrix_rows(aggregate_matrix_rows, matrix_rows)

        if args.validate_only:
            continue

        if args.session_dir is not None and args.output_nwb is not None:
            output_nwb_path = args.output_nwb
        else:
            output_nwb_path = session_dir / f"{session_dir.name}_stage{args.stage}.nwb"

        conversion_config = ConversionConfig(
            dataset_dir=args.dataset_dir,
            session_dir=session_dir,
            conversion_table_path=args.conversion_table,
            output_nwb_path=output_nwb_path,
            current_stage=args.stage,
        )
        output_path = convert_surlab_session_to_nwb(conversion_config)
        print(f"NWB written: {output_path}")

    matrix_path = write_validation_matrix_csv(aggregate_matrix_rows, dataset_matrix_path)
    print(f"Validation matrix written: {matrix_path}")
    if args.validate_only:
        print("Validation-only mode complete.")


if __name__ == "__main__":
    main()

