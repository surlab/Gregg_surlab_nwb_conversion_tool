"""Table-driven NWB -> SurLab reverse conversion (Task 4)."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


@dataclass
class ReverseConversionConfig:
    """Settings for reverse conversion."""

    dataset_dir: Path
    conversion_table_path: Path
    current_stage: int = 4
    output_session_info_name: str = "sessionInfo_single_session.csv"


def _subject_value(nwbfile, attribute_name: str) -> str:
    if nwbfile.subject is None:
        return ""
    value = getattr(nwbfile.subject, attribute_name, None)
    return "" if value is None else str(value)


def _extract_extras(nwbfile) -> Dict[str, str]:
    extras: Dict[str, str] = {}
    if not hasattr(nwbfile, "lab_meta_data") or not nwbfile.lab_meta_data:
        return extras
    for metadata_obj in nwbfile.lab_meta_data.values():
        if getattr(metadata_obj, "name", "") != "SurLabSessionInfoExtras":
            continue
        extras_json = getattr(metadata_obj, "extras_json", "")
        if not extras_json:
            continue
        try:
            parsed = json.loads(extras_json)
        except json.JSONDecodeError:
            continue
        for key, value in parsed.items():
            extras[key] = str(value)
    return extras


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
    return str(row.get("requirement_level", "")).strip().lower()


def _field_non_empty(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip() != ""


def _safe_join_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if _field_non_empty(part)]
        return ",".join(parts)
    return str(value).strip()


def _age_duration_to_days(age_value: str) -> str:
    normalized = age_value.strip()
    if not (normalized.startswith("P") and normalized.endswith("D")):
        return ""
    return normalized[1:-1]


def _value_from_nwb_by_fieldname(nwbfile, fieldname_surlab: str) -> str:
    subject_map = {
        "animal_ID": lambda: _subject_value(nwbfile, "subject_id"),
        "species": lambda: _subject_value(nwbfile, "species"),
        "sex": lambda: _subject_value(nwbfile, "sex"),
        "age__days": lambda: _age_duration_to_days(_subject_value(nwbfile, "age")),
        "strain": lambda: _subject_value(nwbfile, "strain"),
        "area": lambda: _subject_value(nwbfile, "description"),
    }
    file_map = {
        "institution": lambda: _safe_join_text(getattr(nwbfile, "institution", "")),
        "lab": lambda: _safe_join_text(getattr(nwbfile, "lab", "")),
        "experimenter": lambda: _safe_join_text(getattr(nwbfile, "experimenter", "")),
        "session_ID": lambda: _safe_join_text(getattr(nwbfile, "session_id", "")),
        "session_date": lambda: nwbfile.session_start_time.strftime("%Y-%m-%d"),
        "condition": lambda: _safe_join_text(getattr(nwbfile, "session_description", "")),
        "related_publication": lambda: _safe_join_text(getattr(nwbfile, "related_publications", "")),
    }
    if fieldname_surlab in file_map:
        return file_map[fieldname_surlab]()
    if fieldname_surlab in subject_map:
        return subject_map[fieldname_surlab]()
    return ""


def _is_sessioninfo_row(row: Dict[str, str]) -> bool:
    filename = str(row.get("surlab_filename", "")).strip().lower()
    row_type = str(row.get("row_type", "")).strip().lower()
    return "sessioninfo" in filename and row_type == "metadata_field"


def _ordered_sessioninfo_columns(stage_rows: List[Dict[str, str]]) -> List[str]:
    required: List[str] = []
    optional: List[str] = []
    seen = set()
    for row in stage_rows:
        if not _is_sessioninfo_row(row):
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if field_name in {"", "NA", "N/A", "(derived_file_identifier)", "(all columns above)", "dataset_specific"}:
            continue
        if field_name in seen:
            continue
        seen.add(field_name)
        level = _get_requirement_level(row)
        if level == "required":
            required.append(field_name)
        else:
            optional.append(field_name)
    return required + optional


def _find_nwb_files(dataset_dir: Path) -> List[Path]:
    return sorted(dataset_dir.rglob("*.nwb"))


def _build_session_row_from_nwb(nwbfile, ordered_columns: Sequence[str]) -> Dict[str, str]:
    row = {column: _value_from_nwb_by_fieldname(nwbfile, column) for column in ordered_columns}
    extras = _extract_extras(nwbfile)
    row.update(extras)
    return row


def _write_single_row_csv(output_csv: Path, row: Dict[str, str], headers: Sequence[str]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers))
        writer.writeheader()
        writer.writerow({header: row.get(header, "") for header in headers})


def _all_headers(explicit_columns: Sequence[str], session_rows: Iterable[Dict[str, str]]) -> List[str]:
    headers = list(explicit_columns)
    extras: List[str] = []
    for row in session_rows:
        for key in row.keys():
            if key in headers or key in extras:
                continue
            extras.append(key)
    return headers + sorted(extras)


def _dataset_sessioninfo_name(dataset_dir: Path) -> str:
    dataset_id = dataset_dir.name
    return f"sessionInfo_{dataset_id}.csv"


def convert_dataset_nwb_to_surlab(config: ReverseConversionConfig) -> Dict[str, object]:
    """Reverse-convert all NWB files in one dataset into SurLab sessionInfo CSVs."""
    from pynwb import NWBHDF5IO

    conversion_rows = _read_csv_rows(config.conversion_table_path)
    stage_rows = _rows_for_stage(conversion_rows, config.current_stage)
    ordered_columns = _ordered_sessioninfo_columns(stage_rows)
    nwb_files = _find_nwb_files(config.dataset_dir)
    if not nwb_files:
        raise FileNotFoundError(f"No NWB files found under dataset directory: {config.dataset_dir}")

    session_outputs: List[Path] = []
    session_rows: List[Dict[str, str]] = []

    for nwb_path in nwb_files:
        with NWBHDF5IO(str(nwb_path), mode="r", load_namespaces=True) as io_handle:
            nwbfile = io_handle.read()
            row = _build_session_row_from_nwb(nwbfile, ordered_columns=ordered_columns)
        headers_for_session = _all_headers(ordered_columns, [row])
        output_csv = nwb_path.parent / config.output_session_info_name
        _write_single_row_csv(output_csv, row, headers_for_session)
        session_outputs.append(output_csv)
        session_rows.append(row)

    dataset_headers = _all_headers(ordered_columns, session_rows)
    dataset_csv = config.dataset_dir / _dataset_sessioninfo_name(config.dataset_dir)
    dataset_csv.parent.mkdir(parents=True, exist_ok=True)
    with dataset_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=dataset_headers)
        writer.writeheader()
        for row in session_rows:
            writer.writerow({header: row.get(header, "") for header in dataset_headers})

    return {
        "dataset_sessioninfo_csv": dataset_csv,
        "session_csv_files": session_outputs,
        "nwb_files_processed": nwb_files,
    }

