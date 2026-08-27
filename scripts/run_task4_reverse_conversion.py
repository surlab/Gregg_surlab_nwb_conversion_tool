"""Run Task 4 reverse conversion (NWB -> SurLab)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.NWB_to_sur import ReverseConversionConfig, convert_dataset_nwb_to_surlab


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reverse-convert NWB files in a dataset to SurLab format under roundtrip_surformat/."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    parser.add_argument(
        "--session-dir",
        default=None,
        type=Path,
        help="Optional single session directory (limits reverse conversion to that session).",
    )
    parser.add_argument(
        "--conversion-table",
        default=Path("sur_nwb_conversion_table.csv"),
        type=Path,
        help="Path to conversion table CSV.",
    )
    parser.add_argument(
        "--dev-max-stage",
        default=None,
        type=int,
        help="Optional dev filter: only table rows with stage <= this value. Omit to run all implemented steps.",
    )
    parser.add_argument(
        "--output-subdir",
        default="roundtrip_surformat",
        type=str,
        help="Subdirectory under each session folder for reverse-exported SurLab files.",
    )
    parser.add_argument(
        "--log-path",
        default=None,
        type=Path,
        help="Log file path (default: <dataset-dir>/runlog.txt).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ReverseConversionConfig(
        dataset_dir=args.dataset_dir,
        conversion_table_path=args.conversion_table,
        session_dir=args.session_dir,
        dev_max_stage=args.dev_max_stage,
        output_subdir=args.output_subdir,
        log_path=args.log_path,
    )
    result = convert_dataset_nwb_to_surlab(config)
    print(f"Dataset sessionInfo CSV written: {result.dataset_sessioninfo_csv}")
    print(f"Session CSV files written: {len(result.session_csv_files)}")
    print(f"Total files written: {len(result.files_written)}")
    print(f"NWB files processed: {len(result.nwb_files_processed)}")
    if result.report_csv is not None:
        print(f"Report: {result.report_csv}")
    if result.warnings:
        print(f"Warnings: {len(result.warnings)}")


if __name__ == "__main__":
    main()
