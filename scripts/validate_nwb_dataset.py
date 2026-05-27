"""Validate all NWB files under a dataset directory (Task 3)."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from src.nwb_validation import validate_nwb_files_in_dataset, write_dataset_validation_summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run PyNWB validation on every NWB file under one dataset directory."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    return parser.parse_args()


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(message: str, handle) -> None:
    line = f"[{_timestamp()}] {message}"
    print(line)
    handle.write(line + "\n")
    handle.flush()


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory does not exist: {dataset_dir}")
    if not dataset_dir.is_dir():
        raise NotADirectoryError(f"Dataset path is not a directory: {dataset_dir}")

    runlog_path = dataset_dir / "runlog.txt"
    with runlog_path.open("w", encoding="utf-8") as runlog:
        _log("Starting Task 3 NWB validation run.", runlog)
        _log(f"Dataset directory: {dataset_dir}", runlog)
        _log(f"Runlog path: {runlog_path}", runlog)

        nwb_files = sorted(dataset_dir.rglob("*.nwb"))
        _log(f"Found {len(nwb_files)} NWB file(s).", runlog)
        for nwb_file in nwb_files:
            _log(f"Validating: {nwb_file}", runlog)

        results = validate_nwb_files_in_dataset(dataset_dir=dataset_dir)
        summary_path = write_dataset_validation_summary(dataset_dir=dataset_dir, results=results)

        _log(f"Dataset validation summary written: {summary_path}", runlog)
        if not results:
            _log("No NWB files were found under the dataset directory.", runlog)
            _log("Task 3 NWB validation run completed.", runlog)
            return

        passed_count = sum(1 for result in results if result.passed)
        failed_count = len(results) - passed_count
        _log(
            f"Validated {len(results)} NWB file(s): {passed_count} passed, {failed_count} failed.",
            runlog,
        )
        _log("Per-file reports were written next to each NWB file.", runlog)
        _log("Task 3 NWB validation run completed.", runlog)


if __name__ == "__main__":
    main()
