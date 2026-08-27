"""Task 3: convert all implemented SurLab data to NWB, then run PyNWB validation."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.nwb_validation import (
    NWBValidationResult,
    validate_nwb_files_in_dataset,
    write_dataset_validation_summary,
)
from src.session_record import discover_session_dirs, load_session_record, nwb_output_basename
from src.surlab_paths import dataset_id_from_dir
from src.sur_to_nwb import ConversionConfig, convert_surlab_session_to_nwb


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert SurLab sessions to NWB, then validate with official PyNWB validator."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    parser.add_argument(
        "--conversion-table",
        default=Path("sur_nwb_conversion_table.csv"),
        type=Path,
        help="Path to conversion table CSV.",
    )
    parser.add_argument(
        "--open-results",
        action="store_true",
        help="Open validation summary CSV, per-file reports, and session folders (Windows).",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        type=Path,
        help="Optional log file path. Defaults to <dataset-dir>/runlog_convert_and_validate.txt.",
    )
    return parser.parse_args()


def _configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w"), logging.StreamHandler()],
        force=True,
    )
    return logging.getLogger(__name__)


def _convert_dataset(dataset_dir: Path, conversion_table: Path, logger: logging.Logger) -> List[Path]:
    session_dirs = discover_session_dirs(dataset_dir)
    if not session_dirs:
        raise ValueError(f"No session subdirectories found in dataset_dir: {dataset_dir}")

    dataset_id = dataset_id_from_dir(dataset_dir)
    written_nwb_paths: List[Path] = []
    for session_dir in session_dirs:
        session_record = load_session_record(dataset_dir, session_dir, dataset_id)
        output_nwb_path = session_dir / f"{nwb_output_basename(session_record)}.nwb"
        logger.info("Converting session: %s -> %s", session_dir.name, output_nwb_path.name)

        conversion_config = ConversionConfig(
            dataset_dir=dataset_dir,
            session_dir=session_dir,
            conversion_table_path=conversion_table,
            output_nwb_path=output_nwb_path,
            dev_max_stage=None,
        )
        result = convert_surlab_session_to_nwb(conversion_config)
        written_nwb_paths.append(result.output_nwb_path)
        logger.info("NWB written: %s", result.output_nwb_path)
        for warning in result.warnings:
            logger.warning(warning)
        for gap in result.table_gaps:
            logger.warning("Table gap: %s", gap)
    return written_nwb_paths


def _validate_dataset(dataset_dir: Path, logger: logging.Logger) -> List[NWBValidationResult]:
    results = validate_nwb_files_in_dataset(dataset_dir=dataset_dir)
    summary_path = write_dataset_validation_summary(dataset_dir=dataset_dir, results=results)
    logger.info("Validation summary written: %s", summary_path)
    return results


def _open_path(path: Path) -> None:
    if not path.exists():
        return
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    subprocess.run(["xdg-open", str(path)], check=False)


def _open_validation_results(dataset_dir: Path, results: List[NWBValidationResult]) -> None:
    summary_path = dataset_dir / "nwb_validation_summary.csv"
    _open_path(summary_path)
    opened_session_dirs = set()
    for result in results:
        _open_path(result.report_file)
        session_dir = result.session_dir.resolve()
        if session_dir not in opened_session_dirs:
            _open_path(session_dir)
            opened_session_dirs.add(session_dir)


def _print_results_summary(results: List[NWBValidationResult], dataset_dir: Path) -> None:
    summary_path = dataset_dir / "nwb_validation_summary.csv"
    print("")
    print("=== Task 3 convert + validate complete ===")
    print(f"Dataset directory: {dataset_dir}")
    print(f"Validation summary: {summary_path}")
    if not results:
        print("No NWB files were found to validate.")
        return

    passed_count = sum(1 for result in results if result.passed)
    failed_count = len(results) - passed_count
    print(f"Validated {len(results)} NWB file(s): {passed_count} passed, {failed_count} failed.")
    print("")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.nwb_file}")
        print(f"       report: {result.report_file}")
    print("")
    print("Inspect NWBs interactively: scripts/inspect_nwb.ipynb")


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory does not exist: {dataset_dir}")
    if not dataset_dir.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_dir}")

    log_path = args.log_file or (dataset_dir / "runlog_convert_and_validate.txt")
    logger = _configure_logging(log_path)
    logger.info("Starting Task 3 convert + validate run.")
    logger.info("Dataset directory: %s", dataset_dir)
    logger.info("Conversion table: %s", args.conversion_table)
    logger.info("Log file: %s", log_path)

    _convert_dataset(dataset_dir=dataset_dir, conversion_table=args.conversion_table, logger=logger)
    results = _validate_dataset(dataset_dir=dataset_dir, logger=logger)
    _print_results_summary(results=results, dataset_dir=dataset_dir)

    if args.open_results:
        _open_validation_results(dataset_dir=dataset_dir, results=results)

    logger.info("Task 3 convert + validate run completed.")


if __name__ == "__main__":
    main()
