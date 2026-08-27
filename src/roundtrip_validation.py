"""Task 5: compare original SurLab data with round-trip reverse-export outputs."""

from __future__ import annotations

import csv
import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from src.conversion_table import (
    expand_rows_for_datatypes,
    is_informational_row,
    known_sessioninfo_fieldnames,
    read_conversion_table,
    row_applies_to_session,
)
from src.data_io import load_json, load_numeric_array, load_spike_times_by_unit
from src.session_record import (
    discover_session_dirs,
    find_session_info_csv,
    load_session_record,
    normalize_session_record_keys,
    read_csv_rows,
    session_key,
)
from src.nwb_triangulation import (
    attribute_roundtrip_issue,
    find_session_nwb,
    load_nwb_file,
    read_nwb_value_for_row,
    spike_times_match_in_nwb,
)
from src.surlab_paths import (
    ResolvedSurLabFile,
    dataset_id_from_dir,
    discover_datatypes_from_files,
    resolve_dataset_file,
    resolve_row_source_file,
    resolve_session_file,
)

logger = logging.getLogger(__name__)

ROUNDTRIP_SUBDIR = "roundtrip_surformat"

STATUS_MATCH = "match"
STATUS_MISMATCH = "mismatch"
STATUS_SKIPPED_ORIGINAL_MISSING = "skipped_original_missing"
STATUS_SKIPPED_ROUNDTRIP_MISSING = "skipped_roundtrip_missing"
STATUS_SKIPPED_NON_COMPARABLE = "skipped_non_comparable"

SESSIONINFO_SINGLE_NAME = "sessionInfo_single_session.csv"
SESSIONINFO_FIELDNAMES_SKIP = {
    "",
    "N/A",
    "NA",
    "dataset_specific",
    "(derived_file_identifier)",
    "(all columns above)",
}

_SCHEMA_MIRROR_RE = re.compile(
    r"Legacy optional mirror:\s*(\w+)_schema\.json key (\S+)",
    re.IGNORECASE,
)

MODALITY_BOOLEAN_FIELDS = {
    "lfp",
    "spikeTimes",
    "spikeWaves",
    "trialInfo",
    "behEvents",
}

# Modality not yet round-tripped; skip stream scalars when sessionInfo flag is off.
DEFERRED_MODALITIES = {"lfp"}

STREAM_SCALAR_PREFIXES = ("spikeTimes", "lfp", "spikeWaves")


@dataclass
class ComparisonConfig:
    """Settings for one round-trip validation run."""

    dataset_dir: Path
    conversion_table_path: Path
    float_rtol: float = 1e-9
    float_atol: float = 1e-6
    roundtrip_subdir: str = ROUNDTRIP_SUBDIR


@dataclass
class ComparisonRow:
    """One conversion-table check compared between original and round-trip."""

    check: str
    original_path: str
    roundtrip_path: str
    status: str
    detail: str = ""
    nwb_value: str = ""
    nwb_note: str = ""
    likely_owner: str = ""


@dataclass
class SessionComparisonResult:
    """Round-trip comparison results for one session."""

    session_dir: Path
    session_key: str
    rows: List[ComparisonRow] = field(default_factory=list)
    nwb_validation_passed: Optional[bool] = None
    nwb_validation_note: str = ""

    @property
    def mismatch_count(self) -> int:
        return sum(1 for row in self.rows if row.status == STATUS_MISMATCH)


@dataclass
class OriginalSnapshot:
    """Original SurLab values captured before reverse conversion runs."""

    session_record: Dict[str, str]
    dataset_sessioninfo_path: Optional[Path]
    dataset_session_row: Dict[str, str]
    session_sessioninfo_path: Optional[Path]
    session_session_row: Dict[str, str]
    discovered_datatypes: Set[str]
    resolved_files: Dict[str, Optional[ResolvedSurLabFile]]


def _check_id(row: Dict[str, str]) -> str:
    parts = [
        str(row.get("row_type", "")).strip(),
        str(row.get("surlab_file_location", "")).strip(),
        str(row.get("surlab_filename", "")).strip(),
        str(row.get("fieldname_surlab", "")).strip(),
    ]
    datatype_id = str(row.get("datatype_id", "")).strip()
    if datatype_id:
        parts.append(datatype_id)
    return "|".join(parts)


def _original_session_info_path(session_dir: Path) -> Optional[Path]:
    """Prefer legacy/per-session sessionInfo files over round-trip exports."""
    candidates = sorted(session_dir.glob("sessionsInfo*.csv"))
    if candidates:
        return candidates[0]
    candidates = sorted(session_dir.glob("sessionInfo*.csv"))
    for path in candidates:
        if path.name == SESSIONINFO_SINGLE_NAME:
            continue
        return path
    single_session = session_dir / SESSIONINFO_SINGLE_NAME
    if single_session.exists():
        return single_session
    return find_session_info_csv(session_dir, SESSIONINFO_SINGLE_NAME)


def _select_session_row(rows: List[Dict[str, str]], session_record: Dict[str, str]) -> Dict[str, str]:
    if not rows:
        return {}
    if len(rows) == 1:
        return normalize_session_record_keys(rows[0])
    target_key = session_key(session_record)
    for row in rows:
        normalized = normalize_session_record_keys(row)
        if session_key(normalized) == target_key:
            return normalized
    return normalize_session_record_keys(rows[0])


def _discover_datatypes_original(session_dir: Path, dataset_id: str, session_record: Dict[str, str]) -> Set[str]:
    datatypes = discover_datatypes_from_files(session_dir, dataset_id, session_record)
    roundtrip_dir = session_dir / ROUNDTRIP_SUBDIR
    if roundtrip_dir.is_dir():
        datatypes.update(discover_datatypes_from_files(roundtrip_dir, dataset_id, session_record))
    return datatypes


def capture_original_snapshot(
    dataset_dir: Path,
    session_dir: Path,
    conversion_table_path: Path,
) -> OriginalSnapshot:
    """Read original SurLab files before reverse conversion can overwrite them."""
    dataset_id = dataset_id_from_dir(dataset_dir)
    session_record = load_session_record(dataset_dir, session_dir, dataset_id)
    table_rows = read_conversion_table(conversion_table_path)
    discovered = _discover_datatypes_original(session_dir, dataset_id, session_record)
    expanded_rows = expand_rows_for_datatypes(table_rows, discovered)

    dataset_info_path = resolve_dataset_file(
        dataset_dir,
        f"sessionInfo_{dataset_id}.csv",
        session_record,
    )
    dataset_row: Dict[str, str] = {}
    if dataset_info_path is not None:
        dataset_row = _select_session_row(read_csv_rows(dataset_info_path.path), session_record)

    session_info_path = _original_session_info_path(session_dir)
    session_row: Dict[str, str] = {}
    if session_info_path is not None:
        session_row = _select_session_row(read_csv_rows(session_info_path), session_record)

    resolved_files: Dict[str, Optional[ResolvedSurLabFile]] = {}
    for row in expanded_rows:
        if is_informational_row(row):
            continue
        if not row_applies_to_session(row, discovered, datatype_id=row.get("datatype_id")):
            continue
        check = _check_id(row)
        resolved_files[check] = resolve_row_source_file(
            row,
            dataset_dir,
            session_dir,
            session_record,
            datatype_id=row.get("datatype_id"),
        )

    return OriginalSnapshot(
        session_record=session_record,
        dataset_sessioninfo_path=dataset_info_path.path if dataset_info_path else None,
        dataset_session_row=dataset_row,
        session_sessioninfo_path=session_info_path,
        session_session_row=session_row,
        discovered_datatypes=discovered,
        resolved_files=resolved_files,
    )


def _roundtrip_roots(session_dir: Path, dataset_dir: Path) -> Tuple[Path, Path]:
    session_root = session_dir / ROUNDTRIP_SUBDIR
    if not session_root.is_dir():
        session_root = session_dir
    dataset_root = dataset_dir / ROUNDTRIP_SUBDIR
    if not dataset_root.is_dir():
        dataset_root = dataset_dir
    return session_root, dataset_root


def _resolve_roundtrip_file(
    row: Dict[str, str],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    datatype_id: Optional[str] = None,
) -> Optional[ResolvedSurLabFile]:
    session_root, dataset_root = _roundtrip_roots(session_dir, dataset_dir)
    location = str(row.get("surlab_file_location", "")).strip()
    file_pattern = str(row.get("surlab_filename", "")).strip()

    if file_pattern == SESSIONINFO_SINGLE_NAME or "(all columns above)" in file_pattern:
        for root in (session_dir / ROUNDTRIP_SUBDIR, session_dir):
            candidate = root / SESSIONINFO_SINGLE_NAME
            if candidate.exists():
                return ResolvedSurLabFile(path=candidate, pattern=file_pattern, datatype_id=datatype_id)
        return None

    if "sessionInfo" in file_pattern and location == "dataset_dir":
        dataset_id = dataset_id_from_dir(dataset_dir)
        for root in (dataset_dir / ROUNDTRIP_SUBDIR, dataset_dir):
            candidate = root / f"sessionInfo_{dataset_id}.csv"
            if candidate.exists():
                return ResolvedSurLabFile(path=candidate, pattern=file_pattern)
            resolved = resolve_dataset_file(root, file_pattern, session_record)
            if resolved is not None:
                return resolved
        return None

    if location == "dataset_dir":
        return resolve_dataset_file(dataset_root, file_pattern, session_record)
    return resolve_session_file(
        session_root,
        dataset_dir,
        file_pattern,
        session_record,
        datatype_id=datatype_id,
    )


def _normalize_scalar(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if str(part).strip() != ""]
        return ",".join(parts)
    if isinstance(value, (float, np.floating)):
        if float(value).is_integer():
            return str(int(value))
        return str(float(value))
    text = str(value).strip()
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        return text[:-2]
    if text.lower() in {"true", "yes"}:
        return "1"
    if text.lower() in {"false", "no"}:
        return "0"
    return text


def _normalize_age_value(value: object) -> str:
    text = _normalize_scalar(value)
    if text.startswith("P") and text.endswith("D"):
        return text[1:-1]
    return text


def _normalize_date_value(value: object) -> str:
    text = _normalize_scalar(value)
    for date_format in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(text, date_format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def _parse_schema_mirror_from_notes(notes: str) -> Optional[Tuple[str, str]]:
    """Return (datatype_id, schema_json_key) from a conversion-table notes field."""
    match = _SCHEMA_MIRROR_RE.search(notes)
    if match is None:
        return None
    return match.group(1), match.group(2).rstrip(".")


def _stream_scalar_datatype_prefix(field_name: str) -> Optional[str]:
    for prefix in STREAM_SCALAR_PREFIXES:
        if field_name.startswith(prefix + "_"):
            return prefix
    return None


def _session_row(snapshot: OriginalSnapshot) -> Dict[str, str]:
    return snapshot.session_session_row or snapshot.dataset_session_row


def _modality_flag_value(snapshot: OriginalSnapshot, modality: str) -> str:
    return _normalize_scalar(_session_row(snapshot).get(modality, ""))


def _modality_flag_is_absent(value: str) -> bool:
    return _normalize_scalar(value) in ("", "0", "false", "no")


def _find_session_schema_path(session_dir: Path, datatype_id: str) -> Optional[Path]:
    for path in sorted(session_dir.glob(f"{datatype_id}_schema*.json")):
        if ROUNDTRIP_SUBDIR in path.parts:
            continue
        return path
    return None


def _schema_json_value(session_dir: Path, datatype_id: str, schema_key: str) -> str:
    schema_path = _find_session_schema_path(session_dir, datatype_id)
    if schema_path is None:
        return ""
    payload = load_json(schema_path)
    return _normalize_scalar(payload.get(schema_key, ""))


def _effective_sessioninfo_scalar(
    field_name: str,
    snapshot: OriginalSnapshot,
    session_dir: Path,
    table_row: Dict[str, str],
) -> Tuple[str, str]:
    """Resolve canonical sessionInfo scalar using sessionInfo column and schema mirror."""
    sessioninfo_val = _normalize_scalar(_session_row(snapshot).get(field_name, ""))
    mirror = _parse_schema_mirror_from_notes(str(table_row.get("notes", "")))
    schema_val = ""
    if mirror is not None:
        datatype_id, schema_key = mirror
        schema_val = _schema_json_value(session_dir, datatype_id, schema_key)

    if sessioninfo_val and schema_val and sessioninfo_val != schema_val:
        return sessioninfo_val, f"sessionInfo (schema mirror disagrees: {schema_val!r})"
    if sessioninfo_val:
        return sessioninfo_val, "sessionInfo"
    if schema_val:
        return schema_val, "schema mirror"
    return "", "none"


def _normalize_modality_flag(value: object) -> str:
    text = _normalize_scalar(value)
    if text in ("", "false", "no"):
        return "0"
    return text


def _compare_sessioninfo_field(
    field_name: str,
    snapshot: OriginalSnapshot,
    session_dir: Path,
    table_row: Dict[str, str],
    original_row: Dict[str, str],
    roundtrip_row: Dict[str, str],
    config: ComparisonConfig,
) -> Tuple[str, str]:
    """Compare one sessionInfo column honoring spec dual-read and modality flags."""
    prefix = _stream_scalar_datatype_prefix(field_name)
    if prefix in DEFERRED_MODALITIES and _modality_flag_is_absent(_modality_flag_value(snapshot, prefix)):
        return STATUS_SKIPPED_NON_COMPARABLE, f"{prefix} flag=0 (modality not converted)"

    if field_name in MODALITY_BOOLEAN_FIELDS:
        orig = _normalize_modality_flag(original_row.get(field_name, ""))
        roundtrip = _normalize_modality_flag(roundtrip_row.get(field_name, ""))
        if orig == roundtrip:
            return STATUS_MATCH, ""
        return STATUS_MISMATCH, f"orig={orig!r} roundtrip={roundtrip!r}"

    if _parse_schema_mirror_from_notes(str(table_row.get("notes", ""))) or prefix is not None:
        effective_orig, source = _effective_sessioninfo_scalar(field_name, snapshot, session_dir, table_row)
        roundtrip_val = _normalize_scalar(roundtrip_row.get(field_name, ""))
        if effective_orig == "" and roundtrip_val == "":
            return STATUS_SKIPPED_ORIGINAL_MISSING, ""
        matched, detail = _values_match(field_name, effective_orig, roundtrip_val, config)
        if matched:
            if source == "schema mirror":
                return STATUS_MATCH, f"matches {source}"
            return STATUS_MATCH, detail
        return STATUS_MISMATCH, detail

    matched, detail = _values_match(
        field_name,
        original_row.get(field_name, ""),
        roundtrip_row.get(field_name, ""),
        config,
    )
    return (STATUS_MATCH if matched else STATUS_MISMATCH), detail


def _values_match(field_name: str, original: object, roundtrip: object, config: ComparisonConfig) -> Tuple[bool, str]:
    if field_name == "age__days":
        left = _normalize_age_value(original)
        right = _normalize_age_value(roundtrip)
    elif field_name == "session_date":
        left = _normalize_date_value(original)
        right = _normalize_date_value(roundtrip)
    else:
        left = _normalize_scalar(original)
        right = _normalize_scalar(roundtrip)

    if left == right:
        return True, ""
    return False, f"orig={left!r} roundtrip={right!r}"


def _sessioninfo_row_for_location(
    snapshot: OriginalSnapshot,
    location: str,
) -> Dict[str, str]:
    if location == "dataset_dir":
        return snapshot.dataset_session_row
    return snapshot.session_session_row


def _roundtrip_sessioninfo_row(
    row: Dict[str, str],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
) -> Tuple[Dict[str, str], Optional[Path]]:
    for root in (session_dir / ROUNDTRIP_SUBDIR, session_dir, dataset_dir / ROUNDTRIP_SUBDIR, dataset_dir):
        candidate = root / SESSIONINFO_SINGLE_NAME
        if candidate.exists():
            rows = read_csv_rows(candidate)
            return _select_session_row(rows, session_record), candidate

    resolved = _resolve_roundtrip_file(row, dataset_dir, session_dir, session_record)
    if resolved is None:
        return {}, None
    rows = read_csv_rows(resolved.path)
    return _select_session_row(rows, session_record), resolved.path


METADATA_COLUMN_ALIASES = {
    "depth__um": "depth",
    "spike_sorting_ID": "spikesorting_ID",
    # trialInfo legacy demo headers (canonical SurLab names are written on reverse)
    "start_time__s": "start_time",
    "stop_time__s": "stop_time",
    "stimulus_onset__s": "stim_onset",
    "stimulus_offset__s": "stim_offset",
    "tone_frequency__Hz": "tone_freq",
    "tone_intensity__dB": "tone_intensity",
    "reaction_time__s": "reaction_time",
}


def _metadata_csv_column_values(path: Path, column_name: str) -> List[str]:
    rows = read_csv_rows(path)
    if not rows:
        return []
    headers = rows[0].keys()
    lookup_name = column_name
    if lookup_name not in headers and lookup_name in METADATA_COLUMN_ALIASES:
        lookup_name = METADATA_COLUMN_ALIASES[lookup_name]
    if lookup_name not in headers:
        return []
    return [_normalize_scalar(row.get(lookup_name, "")) for row in rows]


def _compare_metadata_csv_column(
    original_path: Path,
    roundtrip_path: Path,
    column_name: str,
) -> Tuple[bool, str]:
    original_values = _metadata_csv_column_values(original_path, column_name)
    roundtrip_values = _metadata_csv_column_values(roundtrip_path, column_name)
    if not original_values and not roundtrip_values:
        return True, ""
    if len(original_values) != len(roundtrip_values):
        return False, f"row_count {len(original_values)} vs {len(roundtrip_values)}"
    for index, (left, right) in enumerate(zip(original_values, roundtrip_values)):
        if left != right:
            return False, f"row {index}: orig={left!r} roundtrip={right!r}"
    return True, ""


def _compare_json_field(original_path: Path, roundtrip_path: Path, field_name: str) -> Tuple[bool, str]:
    original_json = load_json(original_path)
    roundtrip_json = load_json(roundtrip_path)
    left = _normalize_scalar(original_json.get(field_name, ""))
    right = _normalize_scalar(roundtrip_json.get(field_name, ""))
    if left == right:
        return True, ""
    return False, f"orig={left!r} roundtrip={right!r}"


def _is_spike_times_data_file(path: Path) -> bool:
    return path.stem.startswith("spikeTimes_data")


def _compare_arrays(original_path: Path, roundtrip_path: Path, config: ComparisonConfig) -> Tuple[bool, str]:
    if _is_spike_times_data_file(original_path) or _is_spike_times_data_file(roundtrip_path):
        original_series = load_spike_times_by_unit(original_path)
        roundtrip_series = load_spike_times_by_unit(roundtrip_path)
        if len(original_series) != len(roundtrip_series):
            return False, f"unit_count {len(original_series)} vs {len(roundtrip_series)}"
        for index, (left, right) in enumerate(zip(original_series, roundtrip_series)):
            if not np.allclose(left, right, rtol=config.float_rtol, atol=config.float_atol, equal_nan=True):
                return False, f"unit {index}: max_abs_diff={np.max(np.abs(left - right)):.6g}"
        return True, ""

    if "spike" in original_path.stem.lower() and original_path.stem.endswith("_data"):
        original_series = load_spike_times_by_unit(original_path)
        roundtrip_series = load_spike_times_by_unit(roundtrip_path)
        if len(original_series) != len(roundtrip_series):
            return False, f"unit_count {len(original_series)} vs {len(roundtrip_series)}"
        for index, (left, right) in enumerate(zip(original_series, roundtrip_series)):
            if not np.allclose(left, right, rtol=config.float_rtol, atol=config.float_atol, equal_nan=True):
                return False, f"unit {index}: max_abs_diff={np.max(np.abs(left - right)):.6g}"
        return True, ""

    original_array = load_numeric_array(original_path)
    roundtrip_array = load_numeric_array(roundtrip_path)
    if original_array.shape != roundtrip_array.shape:
        return False, f"shape {original_array.shape} vs {roundtrip_array.shape}"
    if not np.allclose(
        original_array,
        roundtrip_array,
        rtol=config.float_rtol,
        atol=config.float_atol,
        equal_nan=True,
    ):
        max_diff = float(np.max(np.abs(original_array - roundtrip_array)))
        return False, f"max_abs_diff={max_diff:.6g}"
    return True, ""


def _compare_dataset_specific_columns(
    snapshot: OriginalSnapshot,
    roundtrip_row: Dict[str, str],
    known_fields: Set[str],
    config: ComparisonConfig,
    roundtrip_path: Optional[Path],
) -> List[ComparisonRow]:
    rows: List[ComparisonRow] = []
    original_row = snapshot.session_session_row or snapshot.dataset_session_row
    extra_columns = sorted(
        column
        for column in set(original_row.keys()).union(roundtrip_row.keys())
        if column not in known_fields and column not in SESSIONINFO_FIELDNAMES_SKIP
    )
    original_source = str(snapshot.session_sessioninfo_path or snapshot.dataset_sessioninfo_path or "")
    roundtrip_source = str(roundtrip_path or "")
    for column in extra_columns:
        original_value = original_row.get(column, "")
        roundtrip_value = roundtrip_row.get(column, "")
        if original_value == "" and roundtrip_value == "":
            status = STATUS_SKIPPED_ORIGINAL_MISSING
            detail = ""
        elif original_value != "" and roundtrip_value == "":
            status = STATUS_SKIPPED_ROUNDTRIP_MISSING
            detail = ""
        else:
            matched, detail = _values_match(column, original_value, roundtrip_value, config)
            status = STATUS_MATCH if matched else STATUS_MISMATCH
        rows.append(
            ComparisonRow(
                check=f"dataset_specific|sessionInfo|{column}",
                original_path=original_source,
                roundtrip_path=roundtrip_source,
                status=status,
                detail=detail,
            )
        )
    return rows


def _compare_table_row(
    row: Dict[str, str],
    snapshot: OriginalSnapshot,
    dataset_dir: Path,
    session_dir: Path,
    config: ComparisonConfig,
) -> ComparisonRow:
    check = _check_id(row)
    row_type = str(row.get("row_type", "")).strip()
    field_name = str(row.get("fieldname_surlab", "")).strip()
    location = str(row.get("surlab_file_location", "")).strip()
    datatype_id = str(row.get("datatype_id", "")).strip() or None

    if field_name == "dataset_specific":
        known_fields = set(known_sessioninfo_fieldnames(read_conversion_table(config.conversion_table_path)))
        roundtrip_row, roundtrip_path_obj = _roundtrip_sessioninfo_row(
            row,
            dataset_dir,
            session_dir,
            snapshot.session_record,
        )
        extras = _compare_dataset_specific_columns(
            snapshot,
            roundtrip_row,
            known_fields,
            config,
            roundtrip_path_obj,
        )
        if extras:
            return extras[0]
        return ComparisonRow(
            check=check,
            original_path=str(snapshot.session_sessioninfo_path or ""),
            roundtrip_path=str(roundtrip_path_obj or ""),
            status=STATUS_SKIPPED_ORIGINAL_MISSING,
            detail="no dataset_specific columns found",
        )

    original_resolved = snapshot.resolved_files.get(check)
    roundtrip_resolved = _resolve_roundtrip_file(
        row,
        dataset_dir,
        session_dir,
        snapshot.session_record,
        datatype_id=datatype_id,
    )
    original_path = original_resolved.path if original_resolved else None
    roundtrip_path = roundtrip_resolved.path if roundtrip_resolved else None

    if row_type in {"data_array", "timestamps_array"}:
        if original_path is None:
            return ComparisonRow(check, "n/a", "n/a", STATUS_SKIPPED_ORIGINAL_MISSING, "")
        if roundtrip_path is None:
            return ComparisonRow(check, str(original_path), "n/a", STATUS_SKIPPED_ROUNDTRIP_MISSING, "")
        matched, detail = _compare_arrays(original_path, roundtrip_path, config)
        status = STATUS_MATCH if matched else STATUS_MISMATCH
        return ComparisonRow(check, str(original_path), str(roundtrip_path), status, detail)

    if row_type != "metadata_field":
        return ComparisonRow(check, "n/a", "n/a", STATUS_SKIPPED_NON_COMPARABLE, f"unsupported row_type={row_type}")

    filename = str(row.get("surlab_filename", "")).lower()
    if filename.endswith(".json"):
        if original_path is None:
            return ComparisonRow(check, "n/a", "n/a", STATUS_SKIPPED_ORIGINAL_MISSING, "")
        if roundtrip_path is None:
            return ComparisonRow(check, str(original_path), "n/a", STATUS_SKIPPED_ROUNDTRIP_MISSING, "")
        matched, detail = _compare_json_field(original_path, roundtrip_path, field_name)
        status = STATUS_MATCH if matched else STATUS_MISMATCH
        return ComparisonRow(check, str(original_path), str(roundtrip_path), status, detail)

    if filename.endswith(".csv"):
        if "sessioninfo" in filename:
            original_row = _sessioninfo_row_for_location(snapshot, location)
            roundtrip_row, resolved_roundtrip = _roundtrip_sessioninfo_row(
                row,
                dataset_dir,
                session_dir,
                snapshot.session_record,
            )
            original_source = snapshot.session_sessioninfo_path if location == "session_dir" else snapshot.dataset_sessioninfo_path
            if not original_row:
                return ComparisonRow(check, "n/a", "n/a", STATUS_SKIPPED_ORIGINAL_MISSING, "")
            if not roundtrip_row:
                return ComparisonRow(
                    check,
                    str(original_source or ""),
                    str(resolved_roundtrip or ""),
                    STATUS_SKIPPED_ROUNDTRIP_MISSING,
                    "",
                )
            status, detail = _compare_sessioninfo_field(
                field_name,
                snapshot,
                session_dir,
                row,
                original_row,
                roundtrip_row,
                config,
            )
            return ComparisonRow(
                check,
                str(original_source or ""),
                str(resolved_roundtrip or ""),
                status,
                detail,
            )

        if original_path is None:
            return ComparisonRow(check, "n/a", "n/a", STATUS_SKIPPED_ORIGINAL_MISSING, "")
        if roundtrip_path is None:
            return ComparisonRow(check, str(original_path), "n/a", STATUS_SKIPPED_ROUNDTRIP_MISSING, "")
        matched, detail = _compare_metadata_csv_column(original_path, roundtrip_path, field_name)
        status = STATUS_MATCH if matched else STATUS_MISMATCH
        return ComparisonRow(check, str(original_path), str(roundtrip_path), status, detail)

    if filename.endswith(".pdf"):
        if original_path is None:
            return ComparisonRow(check, "n/a", "n/a", STATUS_SKIPPED_ORIGINAL_MISSING, "")
        if roundtrip_path is None:
            return ComparisonRow(check, str(original_path), "n/a", STATUS_SKIPPED_ROUNDTRIP_MISSING, "")
        original_hash = hashlib.sha256(original_path.read_bytes()).hexdigest()
        roundtrip_hash = hashlib.sha256(roundtrip_path.read_bytes()).hexdigest()
        if original_hash == roundtrip_hash:
            return ComparisonRow(check, str(original_path), str(roundtrip_path), STATUS_MATCH, "")
        return ComparisonRow(check, str(original_path), str(roundtrip_path), STATUS_MISMATCH, "pdf hash mismatch")

    return ComparisonRow(check, "n/a", "n/a", STATUS_SKIPPED_NON_COMPARABLE, f"unsupported filename={filename}")


def _original_scalar_for_row(
    row: Dict[str, str],
    snapshot: OriginalSnapshot,
    dataset_dir: Path,
    session_dir: Path,
) -> str:
    row_type = str(row.get("row_type", "")).strip()
    field_name = str(row.get("fieldname_surlab", "")).strip()
    location = str(row.get("surlab_file_location", "")).strip()
    check = _check_id(row)
    filename = str(row.get("surlab_filename", "")).lower()

    if field_name == "dataset_specific":
        return ""

    if filename.endswith(".csv") and "sessioninfo" in filename:
        session_row = _sessioninfo_row_for_location(snapshot, location)
        if _stream_scalar_datatype_prefix(field_name) or _parse_schema_mirror_from_notes(
            str(row.get("notes", ""))
        ):
            effective, _ = _effective_sessioninfo_scalar(field_name, snapshot, session_dir, row)
            return effective
        if field_name in MODALITY_BOOLEAN_FIELDS:
            return _normalize_modality_flag(session_row.get(field_name, ""))
        return _normalize_scalar(session_row.get(field_name, ""))

    original_resolved = snapshot.resolved_files.get(check)
    if original_resolved is None:
        return ""

    if row_type in {"data_array", "timestamps_array"}:
        if _is_spike_times_data_file(original_resolved.path):
            series = load_spike_times_by_unit(original_resolved.path)
            return str(len(series))
        array = load_numeric_array(original_resolved.path)
        return f"shape={array.shape}"

    if filename.endswith(".json"):
        payload = load_json(original_resolved.path)
        return _normalize_scalar(payload.get(field_name, ""))

    if filename.endswith(".csv"):
        values = _metadata_csv_column_values(original_resolved.path, field_name)
        if not values:
            return ""
        if len(values) == 1:
            return values[0]
        return "|".join(values[:5]) + ("|..." if len(values) > 5 else "")

    return ""


def _roundtrip_scalar_for_row(
    row: Dict[str, str],
    snapshot: OriginalSnapshot,
    dataset_dir: Path,
    session_dir: Path,
) -> str:
    row_type = str(row.get("row_type", "")).strip()
    field_name = str(row.get("fieldname_surlab", "")).strip()
    location = str(row.get("surlab_file_location", "")).strip()
    filename = str(row.get("surlab_filename", "")).lower()
    datatype_id = str(row.get("datatype_id", "")).strip() or None

    if field_name == "dataset_specific":
        return ""

    if filename.endswith(".csv") and "sessioninfo" in filename:
        roundtrip_row, _ = _roundtrip_sessioninfo_row(row, dataset_dir, session_dir, snapshot.session_record)
        if field_name in MODALITY_BOOLEAN_FIELDS:
            return _normalize_modality_flag(roundtrip_row.get(field_name, ""))
        return _normalize_scalar(roundtrip_row.get(field_name, ""))

    roundtrip_resolved = _resolve_roundtrip_file(
        row,
        dataset_dir,
        session_dir,
        snapshot.session_record,
        datatype_id=datatype_id,
    )
    if roundtrip_resolved is None:
        return ""

    if row_type in {"data_array", "timestamps_array"}:
        if _is_spike_times_data_file(roundtrip_resolved.path):
            series = load_spike_times_by_unit(roundtrip_resolved.path)
            return str(len(series))
        array = load_numeric_array(roundtrip_resolved.path)
        return f"shape={array.shape}"

    if filename.endswith(".json"):
        payload = load_json(roundtrip_resolved.path)
        return _normalize_scalar(payload.get(field_name, ""))

    if filename.endswith(".csv"):
        values = _metadata_csv_column_values(roundtrip_resolved.path, field_name)
        if not values:
            return ""
        if len(values) == 1:
            return values[0]
        return "|".join(values[:5]) + ("|..." if len(values) > 5 else "")

    return ""


def _enrich_rows_with_triangulation(
    result: SessionComparisonResult,
    expanded_rows: List[Dict[str, str]],
    snapshot: OriginalSnapshot,
    dataset_dir: Path,
    session_dir: Path,
    config: ComparisonConfig,
) -> None:
    row_by_check = {_check_id(row): row for row in expanded_rows if not is_informational_row(row)}
    nwb_path = find_session_nwb(session_dir, snapshot.session_record)
    if nwb_path is None:
        for comp_row in result.rows:
            if comp_row.status in {STATUS_MISMATCH, STATUS_SKIPPED_ROUNDTRIP_MISSING}:
                comp_row.likely_owner = attribute_roundtrip_issue(
                    comp_row.status,
                    "",
                    "",
                    "",
                    "",
                    "nwb file missing",
                )
        return

    io_handle, nwbfile = load_nwb_file(nwb_path)
    try:
        for comp_row in result.rows:
            if comp_row.check.startswith("dataset_specific|"):
                column_name = comp_row.check.split("|")[-1]
                original_row = snapshot.session_session_row or snapshot.dataset_session_row
                roundtrip_row, _ = _roundtrip_sessioninfo_row(
                    {"surlab_filename": "sessionInfo_single_session.csv"},
                    dataset_dir,
                    session_dir,
                    snapshot.session_record,
                )
                comp_row.nwb_value = ""
                comp_row.nwb_note = "dataset_specific not in NWB table row"
                comp_row.likely_owner = attribute_roundtrip_issue(
                    comp_row.status,
                    column_name,
                    original_row.get(column_name, ""),
                    "",
                    roundtrip_row.get(column_name, ""),
                    comp_row.nwb_note,
                )
                continue

            table_row = row_by_check.get(comp_row.check)
            if table_row is None:
                continue

            field_name = str(table_row.get("fieldname_surlab", "")).strip()
            original_scalar = _original_scalar_for_row(table_row, snapshot, dataset_dir, session_dir)
            roundtrip_scalar = _roundtrip_scalar_for_row(table_row, snapshot, dataset_dir, session_dir)

            row_type = str(table_row.get("row_type", "")).strip()
            if row_type in {"data_array", "timestamps_array"} and "spike_times" in str(table_row.get("nwb_fieldname", "")):
                check = _check_id(table_row)
                original_resolved = snapshot.resolved_files.get(check)
                if original_resolved is not None:
                    matched, note = spike_times_match_in_nwb(
                        nwbfile,
                        original_resolved.path,
                        rtol=config.float_rtol,
                        atol=config.float_atol,
                    )
                    comp_row.nwb_value = "match" if matched else "mismatch"
                    comp_row.nwb_note = note
                else:
                    nwb_scalar, nwb_note = read_nwb_value_for_row(nwbfile, table_row)
                    comp_row.nwb_value = nwb_scalar or ""
                    comp_row.nwb_note = nwb_note
            else:
                nwb_scalar, nwb_note = read_nwb_value_for_row(nwbfile, table_row)
                comp_row.nwb_value = nwb_scalar if nwb_scalar is not None else ""
                comp_row.nwb_note = nwb_note

            comp_row.likely_owner = attribute_roundtrip_issue(
                comp_row.status,
                field_name,
                original_scalar,
                comp_row.nwb_value,
                roundtrip_scalar,
                comp_row.nwb_note,
            )
    finally:
        io_handle.close()


def compare_session_roundtrip(
    dataset_dir: Path,
    session_dir: Path,
    config: ComparisonConfig,
    snapshot: OriginalSnapshot,
) -> SessionComparisonResult:
    """Compare one session using a pre-captured original snapshot."""
    table_rows = read_conversion_table(config.conversion_table_path)
    expanded_rows = expand_rows_for_datatypes(table_rows, snapshot.discovered_datatypes)
    result = SessionComparisonResult(
        session_dir=session_dir,
        session_key=session_key(snapshot.session_record),
    )

    dataset_specific_done = False
    for row in expanded_rows:
        if is_informational_row(row):
            continue
        if not row_applies_to_session(row, snapshot.discovered_datatypes, datatype_id=row.get("datatype_id")):
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if field_name == "dataset_specific":
            if dataset_specific_done:
                continue
            dataset_specific_done = True
            known_fields = set(known_sessioninfo_fieldnames(table_rows))
            roundtrip_row, roundtrip_path = _roundtrip_sessioninfo_row(
                row,
                dataset_dir,
                session_dir,
                snapshot.session_record,
            )
            result.rows.extend(
                _compare_dataset_specific_columns(
                    snapshot,
                    roundtrip_row,
                    known_fields,
                    config,
                    roundtrip_path,
                )
            )
            continue
        comparison = _compare_table_row(row, snapshot, dataset_dir, session_dir, config)
        result.rows.append(comparison)

    _enrich_rows_with_triangulation(result, expanded_rows, snapshot, dataset_dir, session_dir, config)
    return result


def load_nwb_validation_status(dataset_dir: Path, session_dir: Path) -> Tuple[Optional[bool], str]:
    """Read Task 3 summary row for one session if present."""
    summary_path = dataset_dir / "nwb_validation_summary.csv"
    if not summary_path.exists():
        return None, "summary missing"
    with summary_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if Path(row.get("nwb_file", "")).parent.resolve() == session_dir.resolve():
                passed_text = str(row.get("passed", "")).strip().lower()
                if passed_text in {"true", "1", "yes"}:
                    return True, str(row.get("note", "")).strip()
                if passed_text in {"false", "0", "no"}:
                    return False, str(row.get("note", "")).strip()
    return None, "session not listed"


def write_session_report(result: SessionComparisonResult, output_csv: Path) -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "check",
                "original_path",
                "roundtrip_path",
                "status",
                "detail",
                "nwb_value",
                "nwb_note",
                "likely_owner",
            ],
        )
        writer.writeheader()
        for row in result.rows:
            writer.writerow(
                {
                    "check": row.check,
                    "original_path": row.original_path,
                    "roundtrip_path": row.roundtrip_path,
                    "status": row.status,
                    "detail": row.detail,
                    "nwb_value": row.nwb_value,
                    "nwb_note": row.nwb_note,
                    "likely_owner": row.likely_owner,
                }
            )
    return output_csv


def write_dataset_summary(
    dataset_dir: Path,
    results: Sequence[SessionComparisonResult],
    output_csv: Path,
    forward_ok: bool = True,
    reverse_ok: bool = True,
) -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "session",
        "session_key",
        "forward_ok",
        "reverse_ok",
        "n_match",
        "n_mismatch",
        "n_skipped_original_missing",
        "n_skipped_roundtrip_missing",
        "n_skipped_non_comparable",
        "nwb_validation_passed",
        "nwb_validation_note",
        "report_file",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            report_file = result.session_dir / "roundtrip_validation_report.csv"
            writer.writerow(
                {
                    "session": result.session_dir.name,
                    "session_key": result.session_key,
                    "forward_ok": forward_ok,
                    "reverse_ok": reverse_ok,
                    "n_match": sum(1 for row in result.rows if row.status == STATUS_MATCH),
                    "n_mismatch": sum(1 for row in result.rows if row.status == STATUS_MISMATCH),
                    "n_skipped_original_missing": sum(
                        1 for row in result.rows if row.status == STATUS_SKIPPED_ORIGINAL_MISSING
                    ),
                    "n_skipped_roundtrip_missing": sum(
                        1 for row in result.rows if row.status == STATUS_SKIPPED_ROUNDTRIP_MISSING
                    ),
                    "n_skipped_non_comparable": sum(
                        1 for row in result.rows if row.status == STATUS_SKIPPED_NON_COMPARABLE
                    ),
                    "nwb_validation_passed": result.nwb_validation_passed,
                    "nwb_validation_note": result.nwb_validation_note,
                    "report_file": str(report_file),
                }
            )
    return output_csv
