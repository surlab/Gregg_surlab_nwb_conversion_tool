"""Stage-oriented SurLab -> NWB conversion driven by conversion_table.csv."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class ConversionConfig:
    """User-configurable settings for a conversion run."""

    dataset_dir: Path
    session_dir: Path
    conversion_table_path: Path
    output_nwb_path: Path
    current_stage: int = 1
    timezone_name: str = "UTC"


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
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _get_requirement_level(row: Dict[str, str]) -> str:
    if "requirement_level" in row and row["requirement_level"]:
        return row["requirement_level"].strip().lower()
    if "required" in row:
        return "required" if str(row["required"]).strip().lower() == "true" else "optional"
    return "optional"


def _is_required(row: Dict[str, str]) -> bool:
    return _get_requirement_level(row) == "required"


def _parse_stage(row: Dict[str, str]) -> int:
    try:
        return int(str(row.get("stage", "1")).strip())
    except ValueError:
        return 1


def _rows_for_stage(rows: List[Dict[str, str]], current_stage: int) -> List[Dict[str, str]]:
    return [row for row in rows if _parse_stage(row) <= current_stage]


def _extract_dataset_id(dataset_dir: Path) -> str:
    return dataset_dir.name


def _build_dataset_session_info_path(dataset_dir: Path, dataset_id: str) -> Path:
    return dataset_dir / f"sessionInfo_{dataset_id}.csv"


def _find_session_info_csv(base_dir: Path, expected_name: str) -> Optional[Path]:
    expected_path = base_dir / expected_name
    if expected_path.exists():
        return expected_path
    for pattern in ("sessionInfo*.csv", "sessionsInfo*.csv", "*session*Info*.csv"):
        matches = sorted(base_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _load_session_record(dataset_dir: Path, session_dir: Path, dataset_id: str) -> Dict[str, str]:
    session_local_info = _find_session_info_csv(session_dir, "sessionInfo_single_session.csv")
    if session_local_info is not None and session_local_info.exists():
        local_rows = _read_csv_rows(session_local_info)
        if len(local_rows) == 1:
            return _normalize_session_record_keys(local_rows[0])

    expected_dataset_file = f"sessionInfo_{dataset_id}.csv"
    dataset_info_path = _find_session_info_csv(dataset_dir, expected_dataset_file)
    if dataset_info_path is None:
        raise FileNotFoundError("Could not find dataset sessionInfo CSV in dataset directory.")
    dataset_rows = _read_csv_rows(dataset_info_path)
    if len(dataset_rows) == 1:
        return _normalize_session_record_keys(dataset_rows[0])
    raise ValueError(
        "Could not select one session row. Provide a single-row sessionInfo_single_session.csv "
        "or reduce dataset-level sessionInfo rows to one for this stage-1 run."
    )


def _non_empty(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    string_value = str(value).strip()
    return string_value != ""


def _value_for_field(session_record: Dict[str, str], field_name: str) -> Optional[str]:
    if field_name in ("NA", "N/A", "", None):
        return None
    value = session_record.get(field_name)
    if value is None:
        return None
    if not _non_empty(value):
        return None
    return str(value).strip()


def _derive_identifier(session_record: Dict[str, str]) -> str:
    animal_id = session_record.get("animal_ID", "").strip()
    session_id = session_record.get("session_ID", "").strip()
    if not animal_id or not session_id:
        raise ValueError("Cannot derive NWB identifier without non-empty animal_ID and session_ID.")
    return f"{animal_id}__{session_id}"


def _parse_session_start_time(session_record: Dict[str, str]) -> datetime:
    raw_value = session_record.get("session_date", "").strip()
    if not raw_value:
        raise ValueError("session_date is required and must be non-empty.")
    parsed = None
    for date_format in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(raw_value, date_format)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError(f"session_date '{raw_value}' is not parseable.")
    return parsed.replace(tzinfo=timezone.utc)


def _normalize_age(age_days: str) -> Optional[str]:
    cleaned = age_days.strip()
    if cleaned.lower() in {"u", "unknown", "na", "n/a", "//"}:
        return None
    day_count = float(cleaned)
    if day_count < 0:
        raise ValueError("age__days cannot be negative.")
    if day_count.is_integer():
        return f"P{int(day_count)}D"
    return f"P{day_count}D"


def _collect_stage1_core_fields(session_record: Dict[str, str]) -> Tuple[Dict[str, object], Dict[str, object]]:
    nwb_fields: Dict[str, object] = {}
    subject_fields: Dict[str, object] = {}

    nwb_fields["identifier"] = _derive_identifier(session_record)
    nwb_fields["session_description"] = session_record.get("condition", "").strip() or "No session description provided."
    nwb_fields["session_start_time"] = _parse_session_start_time(session_record)

    optional_nwb_field_map = {
        "institution": "institution",
        "lab": "lab",
        "session_ID": "session_id",
        "related_publication": "related_publications",
    }
    for surlab_name, nwb_name in optional_nwb_field_map.items():
        value = session_record.get(surlab_name, "").strip()
        if value:
            nwb_fields[nwb_name] = value

    subject_map = {
        "animal_ID": "subject_id",
        "species": "species",
        "sex": "sex",
        "strain": "strain",
        "area": "description",
    }
    for surlab_name, nwb_name in subject_map.items():
        value = session_record.get(surlab_name, "").strip()
        if value:
            subject_fields[nwb_name] = value

    age_days = session_record.get("age__days", "").strip()
    if age_days:
        normalized_age = _normalize_age(age_days)
        if normalized_age is not None:
            subject_fields["age"] = normalized_age

    keywords: List[str] = []
    for modality_field, keyword in (
        ("traces", "traces"),
        ("lfp", "lfp"),
        ("spikeTimes", "spike_times"),
        ("spikeWaves", "spike_waveforms"),
        ("behEvents", "behavior_events"),
        ("behTSeries", "behavior_timeseries"),
    ):
        raw_value = str(session_record.get(modality_field, "")).strip().lower()
        if raw_value in {"1", "true", "yes"}:
            keywords.append(keyword)
    if keywords:
        nwb_fields["keywords"] = keywords

    return nwb_fields, subject_fields


def _collect_dataset_specific_fields(session_record: Dict[str, str], known_fields: List[str]) -> Dict[str, str]:
    known = set(known_fields)
    extras: Dict[str, str] = {}
    for key, value in session_record.items():
        if key in known:
            continue
        trimmed = str(value).strip()
        if trimmed:
            extras[key] = trimmed
    return extras


def _build_surlab_labmetadata(extras: Dict[str, str]):
    """Build LabMetaData object for dataset_specific values."""
    from hdmf.utils import docval, popargs
    from pynwb.file import LabMetaData

    class SurLabSessionInfoExtras(LabMetaData):
        __nwbfields__ = ("extras_json",)

        @docval(
            {"name": "name", "type": str, "doc": "Container name"},
            {"name": "extras_json", "type": str, "doc": "JSON string of extra session info columns"},
        )
        def __init__(self, **kwargs):
            extras_json = popargs("extras_json", kwargs)
            super().__init__(**kwargs)
            self.extras_json = extras_json

    return SurLabSessionInfoExtras(name="SurLabSessionInfoExtras", extras_json=json.dumps(extras, sort_keys=True))


def _create_nwbfile_from_session_record(session_record: Dict[str, str], known_fields: List[str]):
    try:
        from pynwb import NWBHDF5IO, NWBFile
        from pynwb.file import Subject
    except ImportError as exc:
        raise ImportError(
            "PyNWB is required for SurLab->NWB conversion. Install with "
            "`pip install pynwb hdmf` or recreate environment from "
            "`environment_cross_platform.yml`."
        ) from exc

    nwb_fields, subject_fields = _collect_stage1_core_fields(session_record)
    required_args = {
        "session_description": nwb_fields.pop("session_description"),
        "identifier": nwb_fields.pop("identifier"),
        "session_start_time": nwb_fields.pop("session_start_time"),
    }
    nwbfile = NWBFile(**required_args, **nwb_fields)
    if subject_fields:
        nwbfile.subject = Subject(**subject_fields)

    extras = _collect_dataset_specific_fields(session_record, known_fields=known_fields)
    if extras:
        nwbfile.add_lab_meta_data(_build_surlab_labmetadata(extras))

    return nwbfile, NWBHDF5IO


def _known_stage1_session_fields(stage_rows: List[Dict[str, str]]) -> List[str]:
    known_fields: List[str] = []
    for row in stage_rows:
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if not field_name:
            continue
        if field_name in {"dataset_specific", "(derived_file_identifier)", "(all columns above)", "NA", "N/A"}:
            continue
        known_fields.append(field_name)
    return sorted(set(known_fields))


def convert_surlab_session_to_nwb(config: ConversionConfig) -> Path:
    """
    Convert one SurLab session to NWB using stage-aware checks.

    File-level phase guard: rows/files with stage greater than current_stage are ignored.
    """
    conversion_rows = _read_csv_rows(config.conversion_table_path)
    stage_rows = _rows_for_stage(conversion_rows, config.current_stage)
    dataset_id = _extract_dataset_id(config.dataset_dir)
    session_record = _load_session_record(config.dataset_dir, config.session_dir, dataset_id)
    known_fields = _known_stage1_session_fields(stage_rows)
    nwbfile, io_class = _create_nwbfile_from_session_record(session_record, known_fields=known_fields)

    config.output_nwb_path.parent.mkdir(parents=True, exist_ok=True)
    with io_class(str(config.output_nwb_path), mode="w") as io_handle:
        io_handle.write(nwbfile)
    return config.output_nwb_path

