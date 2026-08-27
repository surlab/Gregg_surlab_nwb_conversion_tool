"""Unit tests for Task 3 NWB validation helpers."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

from src.nwb_validation import (
    NWBValidationResult,
    validate_nwb_file,
    validate_nwb_files_in_dataset,
    write_dataset_validation_summary,
)
from src.session_record import nwb_output_basename


def test_nwb_output_basename_uses_single_underscore():
    record = {"animal_ID": "MouseA", "session_ID": "S01"}
    assert nwb_output_basename(record) == "MouseA_S01"


def test_nwb_output_basename_requires_ids():
    with pytest.raises(ValueError):
        nwb_output_basename({"animal_ID": "MouseA"})


def test_write_dataset_validation_summary_columns(tmp_path: Path):
    session_dir = tmp_path / "MouseA_S01"
    session_dir.mkdir()
    nwb_file = session_dir / "MouseA_S01.nwb"
    nwb_file.write_text("placeholder", encoding="utf-8")
    report_file = session_dir / "MouseA_S01_pynwb_validation_report.txt"
    report_file.write_text("report", encoding="utf-8")

    results = [
        NWBValidationResult(
            dataset_dir=tmp_path,
            session_dir=session_dir,
            nwb_file=nwb_file,
            report_file=report_file,
            passed=True,
            failed_issue_count=0,
            note="pass",
        )
    ]
    summary_path = write_dataset_validation_summary(dataset_dir=tmp_path, results=results)
    rows = list(csv.DictReader(summary_path.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["session"] == "MouseA_S01"
    assert rows[0]["nwb_file"] == "MouseA_S01.nwb"
    assert rows[0]["report_file"] == "MouseA_S01_pynwb_validation_report.txt"
    assert rows[0]["passed"] == "true"
    assert rows[0]["failed"] == "false"
    assert rows[0]["number_failed"] == "0"
    assert rows[0]["note"] == "pass"


@patch("pynwb.validate")
def test_validate_nwb_file_passes_when_no_issues(mock_validate, tmp_path: Path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    nwb_file = session_dir / "MouseA_S01.nwb"
    nwb_file.write_text("placeholder", encoding="utf-8")
    mock_validate.return_value = []

    result = validate_nwb_file(nwb_file)

    assert result.passed is True
    assert result.failed_issue_count == 0
    assert result.report_file.name == "MouseA_S01_pynwb_validation_report.txt"
    report_text = result.report_file.read_text(encoding="utf-8")
    assert "passed: True" in report_text
    assert "- none" in report_text


@patch("pynwb.validate")
def test_validate_nwb_file_records_issues(mock_validate, tmp_path: Path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    nwb_file = session_dir / "MouseA_S01.nwb"
    nwb_file.write_text("placeholder", encoding="utf-8")
    mock_validate.return_value = ["missing required field"]

    result = validate_nwb_file(nwb_file)

    assert result.passed is False
    assert result.failed_issue_count == 1
    assert "missing required field" in result.report_file.read_text(encoding="utf-8")


@patch("pynwb.validate", side_effect=RuntimeError("validator unavailable"))
def test_validate_nwb_file_handles_runtime_error(mock_validate, tmp_path: Path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    nwb_file = session_dir / "MouseA_S01.nwb"
    nwb_file.write_text("placeholder", encoding="utf-8")

    result = validate_nwb_file(nwb_file)

    assert result.passed is False
    assert result.note == "validator runtime error"
    assert "Validator runtime error" in result.report_file.read_text(encoding="utf-8")


def test_validate_nwb_files_in_dataset_finds_nested_files(tmp_path: Path):
    session_a = tmp_path / "session_a"
    session_b = tmp_path / "nested" / "session_b"
    session_a.mkdir(parents=True)
    session_b.mkdir(parents=True)
    (session_a / "A_1.nwb").write_text("a", encoding="utf-8")
    (session_b / "B_2.nwb").write_text("b", encoding="utf-8")

    with patch("pynwb.validate", return_value=[]):
        results = validate_nwb_files_in_dataset(tmp_path)

    assert len(results) == 2
    assert {result.nwb_file.name for result in results} == {"A_1.nwb", "B_2.nwb"}
