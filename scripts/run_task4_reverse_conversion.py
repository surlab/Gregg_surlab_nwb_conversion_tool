"""Run Task 4 reverse conversion (NWB -> SurLab sessionInfo CSVs)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.NWB_to_sur import ReverseConversionConfig, convert_dataset_nwb_to_surlab


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reverse-convert all NWB files in a dataset to SurLab sessionInfo CSV files."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    parser.add_argument(
        "--conversion-table",
        default=Path("conversion_table.csv"),
        type=Path,
        help="Path to conversion table CSV.",
    )
    parser.add_argument("--stage", default=4, type=int, help="Current conversion stage for table filtering.")
    parser.add_argument(
        "--session-info-name",
        default="sessionInfo_single_session.csv",
        type=str,
        help="Filename written in each session directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ReverseConversionConfig(
        dataset_dir=args.dataset_dir,
        conversion_table_path=args.conversion_table,
        current_stage=args.stage,
        output_session_info_name=args.session_info_name,
    )
    result = convert_dataset_nwb_to_surlab(config)
    print(f"Dataset sessionInfo CSV written: {result['dataset_sessioninfo_csv']}")
    print(f"Session CSV files written: {len(result['session_csv_files'])}")
    print(f"NWB files processed: {len(result['nwb_files_processed'])}")


if __name__ == "__main__":
    main()
