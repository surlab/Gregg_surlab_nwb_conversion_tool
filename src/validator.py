"""Validation helpers for table-driven SurLab dataset checks."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


STATUS_FOUND = "found"
STATUS_MISSING_REQUIRED = "missing (Required)"
STATUS_NOT_FOUND_RECOMMENDED = "not found (recommended)"


@dataclass
class ValidationConfig:
    """Settings for discovery validation."""

    dataset_dir: Path
    session_dir: Path
    conversion_table_path: Path
    current_stage: int = 1
    output_matrix_csv: Path = Path("demo_results/session_validation_matrix.csv")


LEGACY_TO_CANONICAL_FIELD_MAP = {
    "animalID": "animal_ID",
    "sessID": "session_ID",
    "sess_date": "session_date",
    "age": "age__days",
    "infoTrials": "trialInfo",
}


def _normalize_session_record_keys(raw_record: Dict[str, str]) -> Dict[str, str]:
    normalized = dict(raw_record)
    for legacy_name, canonical_name in LEGACY_TO_CANONICAL_FIELD_MAP.items():
        if canonical_name not in normalized and legacy_name in normalized:
            normalized[canonical_name] = normalized[legacy_name]
    return normalized


def _read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _parse_stage(row: Dict[str, str]) -> int:
    try:
        return int(str(row.get("stage", "1")).strip())
    except ValueError:
        return 1


def _rows_for_stage(rows: List[Dict[str, str]], current_stage: int) -> List[Dict[str, str]]:
    return [row for row in rows if _parse_stage(row) <= current_stage]


def _get_requirement_level(row: Dict[str, str]) -> str:
    if "requirement_level" in row and row["requirement_level"]:
        return row["requirement_level"].strip().lower()
    if "required" in row:
        return "required" if str(row["required"]).strip().lower() == "true" else "optional"
    return "optional"


def _is_required(row: Dict[str, str]) -> bool:
    return _get_requirement_level(row) == "required"


def _dataset_id(dataset_dir: Path) -> str:
    return dataset_dir.name


def _find_session_info_csv(base_dir: Path, expected_name: str) -> Path:
    expected_path = base_dir / expected_name
    if expected_path.exists():
        return expected_path
    for pattern in ("sessionInfo*.csv", "sessionsInfo*.csv", "*session*Info*.csv"):
        matches = sorted(base_dir.glob(pattern))
        if matches:
            return matches[0]
    raise FileNotFoundError(f"Could not find sessionInfo CSV in {base_dir}.")


def _resolve_filename_pattern(pattern: str, dataset_id: str, session_info_row: Dict[str, str]) -> str:
    resolved = pattern.replace("<datasetID>", dataset_id)
    for token_key in ("animal_ID", "session_ID"):
        resolved = resolved.replace(f"<{token_key}>", session_info_row.get(token_key, ""))
    return resolved


def _field_non_empty(value: object) -> bool:
    if value is None:
        return False
    as_text = str(value).strip()
    return as_text != ""


def _select_session_record(dataset_dir: Path, session_dir: Path, dataset_id: str) -> Dict[str, str]:
    session_local_info = _find_session_info_csv(session_dir, "sessionInfo_single_session.csv")
    if session_local_info.exists():
        local_rows = _read_csv_rows(session_local_info)
        if len(local_rows) == 1:
            return _normalize_session_record_keys(local_rows[0])
    dataset_info = _find_session_info_csv(dataset_dir, f"sessionInfo_{dataset_id}.csv")
    dataset_rows = _read_csv_rows(dataset_info)
    if len(dataset_rows) == 1:
        return _normalize_session_record_keys(dataset_rows[0])
    raise ValueError("Validation currently supports one-session selection for stage-1 runs.")


def _load_file_rows(file_path: Path) -> List[Dict[str, str]]:
    if not file_path.exists():
        return []
    return _read_csv_rows(file_path)


def _check_row(
    row: Dict[str, str],
    dataset_dir: Path,
    session_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
) -> str:
    location = str(row.get("surlab_file_location", "")).strip()
    file_pattern = str(row.get("surlab_filename", "")).strip()
    source_dir = dataset_dir if location == "dataset_dir" else session_dir
    resolved_name = _resolve_filename_pattern(file_pattern, dataset_id, session_record)
    file_path = source_dir / resolved_name
    if not file_path.exists() and "sessionInfo" in resolved_name:
        try:
            file_path = _find_session_info_csv(source_dir, resolved_name)
        except FileNotFoundError:
            pass

    if not file_path.exists():
        return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED

    field_name = str(row.get("fieldname_surlab", "")).strip()
    if field_name in {"", "NA", "N/A", "(derived_file_identifier)", "(all columns above)"}:
        return STATUS_FOUND

    if field_name == "dataset_specific":
        file_rows = _load_file_rows(file_path)
        if not file_rows:
            return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED
        known_fields = {
            "institution",
            "lab",
            "experimenter",
            "animal_ID",
            "session_ID",
            "session_date",
            "species",
            "sex",
            "age__days",
            "strain",
            "zero_time",
            "area",
            "condition",
            "related_publication",
            "traces",
            "lfp",
            "spikeTimes",
            "spikeWaves",
            "behEvents",
            "behTSeries",
        }
        extras_exist = any(
            key not in known_fields and _field_non_empty(value)
            for key, value in file_rows[0].items()
        )
        if extras_exist:
            return STATUS_FOUND
        return STATUS_NOT_FOUND_RECOMMENDED

    file_rows = _load_file_rows(file_path)
    if not file_rows:
        return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED
    value = file_rows[0].get(field_name)
    if _field_non_empty(value):
        return STATUS_FOUND
    return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED


def _check_name_for_row(row: Dict[str, str]) -> str:
    level = _get_requirement_level(row)
    stage = str(row.get("stage", "")).strip() or "?"
    file_name = str(row.get("surlab_filename", "")).strip()
    field_name = str(row.get("fieldname_surlab", "")).strip() or "FILE_ONLY"
    return f"stage{stage}|{level}|{file_name}|{field_name}"


def build_session_validation_matrix(config: ValidationConfig) -> List[Dict[str, str]]:
    all_rows = _read_csv_rows(config.conversion_table_path)
    stage_rows = _rows_for_stage(all_rows, config.current_stage)
    dataset_id = _dataset_id(config.dataset_dir)
    session_record = _select_session_record(config.dataset_dir, config.session_dir, dataset_id)
    session_key = f"{session_record.get('animal_ID', 'unknown')}__{session_record.get('session_ID', 'unknown')}"

    matrix_rows: List[Dict[str, str]] = []
    for row in stage_rows:
        matrix_rows.append(
            {
                "check": _check_name_for_row(row),
                session_key: _check_row(row, config.dataset_dir, config.session_dir, dataset_id, session_record),
            }
        )
    return matrix_rows


def write_validation_matrix_csv(matrix_rows: List[Dict[str, str]], output_csv: Path) -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    headers = ["check"]
    for row in matrix_rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)

    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in matrix_rows:
            writer.writerow(row)
    return output_csv

