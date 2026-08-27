"""Task 5: full round-trip validation (forward, PyNWB validate, reverse, compare)."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.roundtrip_validation import (
    ComparisonConfig,
    capture_original_snapshot,
    compare_session_roundtrip,
    discover_session_dirs,
    load_nwb_validation_status,
    write_dataset_summary,
    write_session_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run SurLab -> NWB -> SurLab round-trip validation for one dataset."
    )
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Path to one dataset directory.")
    parser.add_argument(
        "--session-dir",
        required=False,
        type=Path,
        help="Optional single session directory. If omitted, all session subfolders are processed.",
    )
    parser.add_argument(
        "--conversion-table",
        default=Path("sur_nwb_conversion_table.csv"),
        type=Path,
        help="Path to conversion table CSV.",
    )
    parser.add_argument(
        "--float-rtol",
        default=1e-9,
        type=float,
        help="Relative tolerance for numeric array comparisons.",
    )
    parser.add_argument(
        "--float-atol",
        default=1e-6,
        type=float,
        help="Absolute tolerance for numeric array comparisons.",
    )
    parser.add_argument(
        "--skip-forward",
        action="store_true",
        help="Skip forward conversion and PyNWB validation subprocesses.",
    )
    parser.add_argument(
        "--skip-reverse",
        action="store_true",
        help="Skip reverse conversion subprocess.",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        type=Path,
        help="Optional log file path. Defaults to <dataset-dir>/runlog_roundtrip_validation.txt.",
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


def _run_subprocess(command: List[str], logger: logging.Logger, step_name: str) -> bool:
    logger.info("Running %s: %s", step_name, " ".join(command))
    completed = subprocess.run(command, cwd=str(REPO_ROOT), check=False)
    if completed.returncode != 0:
        logger.error("%s failed with exit code %s", step_name, completed.returncode)
        return False
    return True


def _python_executable() -> str:
    return sys.executable


def main() -> None:
    args = parse_args()
    dataset_dir = args.dataset_dir.resolve()
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory does not exist: {dataset_dir}")

    log_path = args.log_file or (dataset_dir / "runlog_roundtrip_validation.txt")
    logger = _configure_logging(log_path)
    logger.info("Starting Task 5 round-trip validation.")
    logger.info("Dataset directory: %s", dataset_dir)
    logger.info("Conversion table: %s", args.conversion_table)

    if args.session_dir is not None:
        session_dirs = [args.session_dir.resolve()]
    else:
        session_dirs = discover_session_dirs(dataset_dir)
    if not session_dirs:
        raise ValueError(f"No session subdirectories found in dataset_dir: {dataset_dir}")

    snapshots = {}
    for session_dir in session_dirs:
        logger.info("Capturing original snapshot for session: %s", session_dir.name)
        snapshots[session_dir] = capture_original_snapshot(
            dataset_dir=dataset_dir,
            session_dir=session_dir,
            conversion_table_path=args.conversion_table,
        )

    forward_ok = True
    reverse_ok = True

    if not args.skip_forward:
        forward_ok = _run_subprocess(
            [
                _python_executable(),
                str(REPO_ROOT / "scripts" / "run_convert_and_validate.py"),
                "--dataset-dir",
                str(dataset_dir),
                "--conversion-table",
                str(args.conversion_table),
            ],
            logger=logger,
            step_name="forward conversion and PyNWB validation",
        )
    else:
        logger.info("Skipping forward conversion and PyNWB validation.")

    if not args.skip_reverse:
        reverse_ok = _run_subprocess(
            [
                _python_executable(),
                str(REPO_ROOT / "scripts" / "run_task4_reverse_conversion.py"),
                "--dataset-dir",
                str(dataset_dir),
                "--conversion-table",
                str(args.conversion_table),
            ],
            logger=logger,
            step_name="reverse conversion",
        )
    else:
        logger.info("Skipping reverse conversion.")

    if not forward_ok:
        logger.warning("Forward conversion failed; continuing with comparison using existing files.")
    if not reverse_ok:
        logger.warning("Reverse conversion failed; continuing with comparison using existing files.")

    comparison_config = ComparisonConfig(
        dataset_dir=dataset_dir,
        conversion_table_path=args.conversion_table,
        float_rtol=args.float_rtol,
        float_atol=args.float_atol,
    )

    session_results = []
    total_mismatches = 0
    for session_dir in session_dirs:
        logger.info("Comparing round-trip values for session: %s", session_dir.name)
        result = compare_session_roundtrip(
            dataset_dir=dataset_dir,
            session_dir=session_dir,
            config=comparison_config,
            snapshot=snapshots[session_dir],
        )
        passed, note = load_nwb_validation_status(dataset_dir, session_dir)
        result.nwb_validation_passed = passed
        result.nwb_validation_note = note

        report_path = write_session_report(result, session_dir / "roundtrip_validation_report.csv")
        logger.info("Session report written: %s", report_path)
        session_results.append(result)
        total_mismatches += result.mismatch_count

    summary_path = write_dataset_summary(
        dataset_dir=dataset_dir,
        results=session_results,
        output_csv=dataset_dir / "roundtrip_validation_summary.csv",
        forward_ok=forward_ok,
        reverse_ok=reverse_ok,
    )
    logger.info("Dataset summary written: %s", summary_path)

    for result in session_results:
        logger.info(
            "Session %s: %d mismatch(es), nwb_validation_passed=%s",
            result.session_dir.name,
            result.mismatch_count,
            result.nwb_validation_passed,
        )

    logger.info("Task 5 round-trip validation completed.")
    print("")
    print("=== Task 5 round-trip validation complete ===")
    print(f"Dataset directory: {dataset_dir}")
    print(f"Summary: {summary_path}")
    print(f"Log file: {log_path}")
    print(f"Total mismatches: {total_mismatches}")
    for result in session_results:
        print(
            f"  {result.session_dir.name}: mismatches={result.mismatch_count}, "
            f"nwb_validation_passed={result.nwb_validation_passed}"
        )

    if total_mismatches > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
