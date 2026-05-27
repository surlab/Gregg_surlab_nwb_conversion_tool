"""Task 3 NWB validation utilities using the official PyNWB validator."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


@dataclass
class NWBValidationResult:
    """Validation status for one NWB file."""

    dataset_dir: Path
    session_dir: Path
    nwb_file: Path
    report_file: Path
    passed: bool
    failed_issue_count: int
    note: str


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issues_to_text_lines(issues: List[object]) -> List[str]:
    if not issues:
        return []
    return [str(issue) for issue in issues]


def validate_nwb_file(nwb_file: Path) -> NWBValidationResult:
    """Run official PyNWB validation for one NWB file and save a report next to it."""
    from pynwb import validate

    session_dir = nwb_file.parent
    report_file = session_dir / f"{nwb_file.stem}_pynwb_validation_report.txt"
    issue_lines: List[str] = []
    passed = False
    note = ""

    try:
        validation_output = validate(path=str(nwb_file))
        issue_lines = _issues_to_text_lines(list(validation_output))
        passed = len(issue_lines) == 0
        note = "pass" if passed else "validator issues found"
    except Exception as error:  # pragma: no cover - defensive fallback for runtime environment issues.
        issue_lines = [f"Validator runtime error: {error}"]
        passed = False
        note = "validator runtime error"

    report_lines = [
        "PyNWB validation report",
        f"generated_utc: {_now_iso_utc()}",
        f"nwb_file: {nwb_file}",
        f"passed: {passed}",
        f"failed_issue_count: {len(issue_lines)}",
        "",
        "issues:",
    ]
    if issue_lines:
        report_lines.extend(f"- {line}" for line in issue_lines)
    else:
        report_lines.append("- none")

    report_file.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return NWBValidationResult(
        dataset_dir=Path(),
        session_dir=session_dir,
        nwb_file=nwb_file,
        report_file=report_file,
        passed=passed,
        failed_issue_count=len(issue_lines),
        note=note,
    )


def validate_nwb_files_in_dataset(dataset_dir: Path) -> List[NWBValidationResult]:
    """Validate every NWB file found recursively under a dataset directory."""
    nwb_files = sorted(dataset_dir.rglob("*.nwb"))
    results: List[NWBValidationResult] = []
    for nwb_file in nwb_files:
        file_result = validate_nwb_file(nwb_file)
        results.append(
            NWBValidationResult(
                dataset_dir=dataset_dir,
                session_dir=file_result.session_dir,
                nwb_file=file_result.nwb_file,
                report_file=file_result.report_file,
                passed=file_result.passed,
                failed_issue_count=file_result.failed_issue_count,
                note=file_result.note,
            )
        )
    return results


def write_dataset_validation_summary(dataset_dir: Path, results: List[NWBValidationResult]) -> Path:
    """Write one summary CSV in dataset root with one row per validated NWB file."""
    summary_path = dataset_dir / "nwb_validation_summary.csv"
    fieldnames = [
        "session",
        "nwb_file",
        "report_file",
        "passed",
        "failed",
        "number_failed",
        "note",
    ]

    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "session": result.session_dir.name,
                    "nwb_file": result.nwb_file.name,
                    "report_file": result.report_file.name,
                    "passed": "true" if result.passed else "false",
                    "failed": "false" if result.passed else "true",
                    "number_failed": str(result.failed_issue_count),
                    "note": result.note,
                }
            )

    return summary_path
