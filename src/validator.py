"""Table-driven SurLab format validation (presence, naming, types, consistency).

Uses the same filename resolver and file-first datatype discovery as forward
conversion. SessionInfo checks use canonical field names from the in-memory
session record (legacy headers are normalized on load for presence checks, but
on-disk legacy headers are reported as naming violations).

For ``data_array`` / ``timestamps_array`` table rows, loads ``.mat``/``.npz``
files when present and checks float64-compatible dtypes, 1-D timestamps,
axis-0 length vs paired timestamps, and ``X_size``/``Y_size``/index lengths
from the datatype schema when those keys exist.
"""

from __future__ import annotations

import csv
import copy
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from src.conversion_table import (
    condition_datatype_id,
    expand_rows_for_datatypes,
    filter_dev_stage,
    is_informational_row,
    known_sessioninfo_fieldnames,
    read_conversion_table,
    row_applies_to_session,
)
from src.data_io import (
    load_json,
    load_numeric_array,
    load_spike_times_by_unit,
    normalize_metadata_row,
    normalize_schema_keys,
)
from src.session_record import (
    LEGACY_TO_CANONICAL_FIELD_MAP,
    field_non_empty,
    find_session_info_csv,
    load_session_record,
    read_csv_rows,
    session_key,
    truthy_flag,
)
from src.surlab_paths import (
    discover_datatypes_from_files,
    dataset_id_from_dir,
    resolve_row_source_file,
)

logger = logging.getLogger(__name__)

STATUS_FOUND = "found"
STATUS_MISSING_REQUIRED = "missing (Required)"
STATUS_NOT_FOUND_RECOMMENDED = "not found (recommended)"
STATUS_NOT_APPLICABLE = "not applicable"
STATUS_TABLE_GAP = "table gap (unhandled)"

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_WARN = "warn"
STATUS_SKIP = "skip"
STATUS_TABLE_GAP_TYPED = "table_gap"

SEVERITY_FAIL = "fail"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"

_SCHEMA_MIRROR_RE = re.compile(
    r"Legacy optional mirror:\s*(\w+)_schema\.json key (\S+)",
    re.IGNORECASE,
)
_LEADING_NUMBER_RE = re.compile(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)(.*)$")
_UNIT_SUFFIX_RE = re.compile(
    r"(?i)\s*(Hz|kHz|MHz|dB|um|µm|mm|ms|s|sec|seconds|days?|deg|degrees|a\.?u\.?)\s*$"
)

# Pipeline / tool artifacts — not SurLab format files.
NON_FORMAT_NAME_MARKERS = (
    "roundtrip",
    "validation",
    "runlog",
    "conversion_table",
    "discovered",
    "pynwb",
    "nwb_validation",
)
NON_FORMAT_SUFFIXES = {".nwb", ".txt", ".md", ".bat", ".ipynb", ".pyc"}
SURLAB_DATA_SUFFIXES = {".csv", ".json", ".mat", ".npz", ".pdf"}

METADATA_LEGACY_HEADERS = {
    "spikesorting_ID": "spike_sorting_ID",
    "depth": "depth__um",
}
SCHEMA_LEGACY_KEYS = {
    "sampFreq": "sample_frequency__Hz",
    "data_unit_meas": "data_unit_measurement",
}
TRIALINFO_LEGACY_HEADERS = {
    "start_time": "start_time__s",
    "stop_time": "stop_time__s",
    "stim_onset": "stimulus_onset__s",
    "stim_offset": "stimulus_offset__s",
    "tone_freq": "tone_frequency__Hz",
    "tone_intensity": "tone_intensity__dB",
    "reaction_time": "reaction_time__s",
    "output": "action",
}

# nwb_type values that are not value-checked (informational / file-level).
UNTYPED_NWB_TYPES = {"", "n/a", "na", "same"}


def _as_sequence(value: object) -> Optional[List[object]]:
    """Normalize list-like values for array_* nwb_types; None if not a sequence."""
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if not inner:
                return []
            return [part.strip().strip("'\"") for part in inner.split(",")]
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        parts = [part for part in re.split(r"[\s;]+", text) if part.strip()]
        if len(parts) > 1:
            return parts
        number, remainder, _ = _split_number_and_suffix(text)
        if number is not None and remainder == "":
            return [number]
        return None
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            if value.ndim == 0:
                return [value.item()]
            return list(value.reshape(-1).tolist())
    except Exception:
        pass
    return None


def _element_is_number(element: object) -> bool:
    if isinstance(element, bool):
        return False
    if isinstance(element, (int, float)):
        return True
    text = str(element).strip()
    number, remainder, _ = _split_number_and_suffix(text)
    return number is not None and remainder == ""


def _element_is_int(element: object) -> bool:
    if isinstance(element, bool):
        return False
    if isinstance(element, int):
        return True
    if isinstance(element, float):
        return float(element).is_integer()
    text = str(element).strip()
    number, remainder, _ = _split_number_and_suffix(text)
    return number is not None and remainder == "" and float(number).is_integer()


@dataclass
class ValidationConfig:
    """Settings for discovery / format validation."""

    dataset_dir: Path
    session_dir: Path
    conversion_table_path: Path
    dev_max_stage: Optional[int] = None
    output_matrix_csv: Path = Path("demo_results/session_validation_matrix.csv")
    output_discovery_csv: Optional[Path] = None


@dataclass
class ConventionIssue:
    """One SurLab format convention check result."""

    check: str
    severity: str
    status: str
    detail: str = ""
    path: str = ""
    fieldname: str = ""
    expected: str = ""
    observed: str = ""
    table_gap: str = ""


@dataclass
class SessionFormatResult:
    """Full format-validation result for one session."""

    session_dir: Path
    session_key: str
    matrix_rows: List[Dict[str, str]] = field(default_factory=list)
    issues: List[ConventionIssue] = field(default_factory=list)

    @property
    def fail_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == SEVERITY_FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == SEVERITY_WARN)


def _get_requirement_level(row: Dict[str, str]) -> str:
    if row.get("requirement_level"):
        return row["requirement_level"].strip().lower()
    if "required" in row:
        return "required" if str(row["required"]).strip().lower() == "true" else "optional"
    return "optional"


def _is_required(row: Dict[str, str]) -> bool:
    return _get_requirement_level(row) == "required"


def _is_recommended(row: Dict[str, str]) -> bool:
    return _get_requirement_level(row) == "recommended"


def _is_not_recommended(row: Dict[str, str]) -> bool:
    return _get_requirement_level(row) == "not-recommended"


def _check_name_for_row(row: Dict[str, str]) -> str:
    level = _get_requirement_level(row)
    stage = str(row.get("stage", "")).strip() or "?"
    file_name = str(row.get("surlab_filename", "")).strip()
    field_name = str(row.get("fieldname_surlab", "")).strip() or "FILE_ONLY"
    datatype_id = str(row.get("datatype_id", "")).strip()
    if datatype_id:
        file_name = f"{file_name} [{datatype_id}]"
    return f"stage{stage}|{level}|{file_name}|{field_name}"


def _value_from_json(schema: Dict[str, object], field_name: str) -> object:
    if field_name in schema:
        return schema[field_name]
    normalized = normalize_schema_keys(schema)
    return normalized.get(field_name)


def _row_targets_sessioninfo(row: Dict[str, str], resolved_path: Path) -> bool:
    filename_pattern = str(row.get("surlab_filename", "")).lower()
    if "sessioninfo" in filename_pattern:
        return True
    resolved_name = resolved_path.name.lower()
    return "sessioninfo" in resolved_name or "sessionsinfo" in resolved_name


def _parse_schema_mirror(notes: str) -> Optional[Tuple[str, str]]:
    match = _SCHEMA_MIRROR_RE.search(notes or "")
    if match is None:
        return None
    return match.group(1), match.group(2).rstrip(".")


def _normalize_compare_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ",".join(str(part).strip() for part in value if str(part).strip())
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].replace("-", "", 1).isdigit():
        return text[:-2]
    return text


def _is_missing_token(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"", "nan", "na", "n/a", "none", "null", "//"}


def _split_number_and_suffix(text: str) -> Tuple[Optional[float], str, str]:
    match = _LEADING_NUMBER_RE.match(text.strip())
    if match is None:
        return None, "", text
    number = float(match.group(1))
    remainder = match.group(2).strip()
    return number, remainder, match.group(1)


def assess_value_type(
    value: object,
    nwb_type: str,
    field_name: str = "",
    units_hint: str = "",
) -> Tuple[str, str, str]:
    """Return (status, detail, table_gap). status in pass/fail/warn/table_gap/skip."""
    if _is_missing_token(value):
        return STATUS_SKIP, "empty", ""

    type_key = (nwb_type or "").strip().lower().replace("64", "").replace("32", "")
    text = str(value).strip()
    units_lower = (units_hint or "").lower()

    if type_key in UNTYPED_NWB_TYPES:
        return STATUS_TABLE_GAP_TYPED, f"nwb_type={nwb_type!r} not validated", f"nwb_type={nwb_type}"

    if type_key in {"str", "str_or_array_of_str", "array_of_str"}:
        if field_name == "sex" and text.upper() not in {"M", "F", "O", "U"}:
            return STATUS_FAIL, f"sex must be M/F/O/U, got {text!r}", ""
        lowered = text.lower()
        if field_name == "correct":
            if lowered in {"", "nan", "na", "n/a", "none", "null"}:
                return STATUS_PASS, "", ""
            if lowered == "early_press":
                return (
                    STATUS_FAIL,
                    "early_press must not appear in correct; use action=early_press and leave correct empty",
                    "",
                )
            if lowered in {"correct", "incorrect", "error", "0", "1"}:
                return STATUS_PASS, "", ""
            return STATUS_FAIL, f"correct must be correct|incorrect or missing; got {text!r}", ""
        if field_name == "trial_type":
            if lowered in {"", "nan", "na", "n/a", "none", "null"}:
                return STATUS_PASS, "", ""
            if lowered == "early_press":
                return (
                    STATUS_FAIL,
                    "early_press must not appear in trial_type; use action=early_press and trial_type=aborted",
                    "",
                )
            if lowered in {"hit", "miss", "fa", "cr", "aborted"}:
                return STATUS_PASS, "", ""
            return STATUS_FAIL, f"trial_type must be hit|miss|fa|cr|aborted or missing; got {text!r}", ""
        if "yyyy-mm-dd" in units_lower or field_name == "session_date":
            return _assess_date_value(text)
        if "boolean 0/1" in units_lower or "binary" in units_lower:
            if lowered not in {"0", "1", "true", "false", "yes", "no"}:
                return STATUS_FAIL, f"expected 0/1 boolean-like, got {text!r}", ""
        return STATUS_PASS, "", ""

    if type_key == "datetime":
        return _assess_date_value(text)

    if type_key == "bool":
        if text.lower() in {"0", "1", "true", "false", "yes", "no"}:
            return STATUS_PASS, "", ""
        return STATUS_FAIL, f"expected bool 0/1, got {text!r}", ""

    if type_key in {"int", "integer"}:
        number, remainder, _ = _split_number_and_suffix(text)
        if number is None:
            return STATUS_FAIL, f"expected int, got {text!r}", ""
        if remainder:
            return STATUS_FAIL, f"int cell has unit/text suffix {remainder!r}", ""
        if not float(number).is_integer():
            return STATUS_FAIL, f"expected int, got non-integer {text!r}", ""
        return STATUS_PASS, "", ""

    if type_key == "int_or_str":
        return STATUS_PASS, "", ""

    if type_key == "float_or_str":
        number, remainder, _ = _split_number_and_suffix(text)
        if number is not None and remainder == "":
            return STATUS_PASS, "", ""
        if text:
            return STATUS_PASS, "", ""
        return STATUS_FAIL, f"expected float or non-empty str, got {text!r}", ""

    if type_key in {"float", "float64"}:
        number, remainder, _ = _split_number_and_suffix(text)
        if number is None:
            return STATUS_FAIL, f"expected float, got {text!r}", ""
        if remainder and _UNIT_SUFFIX_RE.search(remainder):
            return (
                STATUS_FAIL,
                f"numeric cell includes unit suffix {remainder!r}; units belong in fieldname",
                "",
            )
        if remainder:
            return STATUS_FAIL, f"float cell has trailing text {remainder!r}", ""
        sanity = _sanity_range_detail(field_name, number, units_hint)
        if sanity:
            return STATUS_WARN, sanity, ""
        return STATUS_PASS, "", ""

    if type_key in {"array_of_float", "array_of_float64"}:
        sequence = _as_sequence(value)
        if sequence is None:
            return STATUS_FAIL, f"expected 1-D array of floats, got {type(value).__name__}", ""
        bad = [element for element in sequence if not _element_is_number(element)]
        if bad:
            return STATUS_FAIL, f"array_of_float has non-numeric elements (e.g. {bad[0]!r})", ""
        return STATUS_PASS, "", ""

    if type_key == "array_of_int":
        sequence = _as_sequence(value)
        if sequence is None:
            return STATUS_FAIL, f"expected 1-D array of ints, got {type(value).__name__}", ""
        bad = [element for element in sequence if not _element_is_int(element)]
        if bad:
            return STATUS_FAIL, f"array_of_int has non-integer elements (e.g. {bad[0]!r})", ""
        return STATUS_PASS, "", ""

    if type_key == "array_of_int_or_str":
        sequence = _as_sequence(value)
        if sequence is None:
            return STATUS_FAIL, f"expected 1-D array of int/str, got {type(value).__name__}", ""
        for element in sequence:
            if _element_is_int(element):
                continue
            if str(element).strip():
                continue
            return STATUS_FAIL, f"array_of_int_or_str has empty element", ""
        return STATUS_PASS, "", ""

    return STATUS_TABLE_GAP_TYPED, f"unhandled nwb_type={nwb_type!r}", f"nwb_type={nwb_type}"


def _assess_date_value(text: str) -> Tuple[str, str, str]:
    try:
        datetime.strptime(text, "%Y-%m-%d")
        return STATUS_PASS, "", ""
    except ValueError:
        pass
    for date_format in ("%m-%d-%Y", "%m/%d/%Y"):
        try:
            datetime.strptime(text, date_format)
            return STATUS_FAIL, f"session_date {text!r} not YYYY-MM-DD", ""
        except ValueError:
            continue
    return STATUS_FAIL, f"unparseable date {text!r}", ""


def _sanity_range_detail(field_name: str, number: float, units_hint: str) -> str:
    name = field_name.lower()
    units = (units_hint or "").lower()
    if "frequency" in name or name.endswith("__hz") or "hz" in units:
        if number <= 0:
            return f"frequency {number} should be > 0"
    if "age" in name and number < 0:
        return f"age {number} should be >= 0"
    if name.endswith("__um") or "micrometer" in units:
        if number < 0:
            return f"length {number} should be >= 0"
    return ""


def _check_row(
    row: Dict[str, str],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    discovered_datatypes: set[str],
) -> str:
    datatype_id = str(row.get("datatype_id", "")).strip() or None
    if not row_applies_to_session(row, discovered_datatypes, datatype_id=datatype_id):
        return STATUS_NOT_APPLICABLE

    field_name = str(row.get("fieldname_surlab", "")).strip()
    row_type = str(row.get("row_type", "")).strip()

    if field_name == "dataset_specific":
        return _check_dataset_specific_row(row, dataset_dir, session_dir, session_record, datatype_id)

    if field_name == "(derived_file_identifier)":
        has_ids = field_non_empty(session_record.get("animal_ID")) and field_non_empty(
            session_record.get("session_ID")
        )
        if has_ids:
            return STATUS_FOUND
        return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED

    resolved = resolve_row_source_file(row, dataset_dir, session_dir, session_record, datatype_id=datatype_id)
    if resolved is None:
        return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED

    if row_type in {"data_array", "timestamps_array"}:
        return STATUS_FOUND

    if resolved.path.suffix.lower() == ".json":
        schema = normalize_schema_keys(load_json(resolved.path))
        if field_name in {"NA", "N/A"}:
            return STATUS_FOUND
        value = _value_from_json(schema, field_name)
        if field_non_empty(value) or (isinstance(value, (int, float)) and value == 0):
            return STATUS_FOUND
        return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED

    file_rows = read_csv_rows(resolved.path)
    if not file_rows:
        return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED

    if field_name in {"NA", "N/A", "(all columns above)"}:
        return STATUS_FOUND

    if _row_targets_sessioninfo(row, resolved.path):
        value = session_record.get(field_name)
        if value is not None and str(value).strip() != "":
            return STATUS_FOUND
        if value is not None and str(value).strip() == "0":
            return STATUS_FOUND
        # Dual-read: legacy schema mirror can satisfy presence when sessionInfo is empty.
        mirror = _parse_schema_mirror(str(row.get("notes", "")))
        if mirror is not None:
            stream_id, schema_key = mirror
            schema_path = _find_schema_file(session_dir, stream_id)
            if schema_path is not None:
                schema = normalize_schema_keys(load_json(schema_path))
                schema_value = schema.get(schema_key)
                if field_non_empty(schema_value) or (
                    isinstance(schema_value, (int, float)) and schema_value == 0
                ):
                    return STATUS_FOUND
        return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED

    column_present = any(field_non_empty(record.get(field_name)) for record in file_rows)
    if not column_present and "trialinfo" in resolved.path.name.lower():
        legacy_name = next(
            (legacy for legacy, canonical in TRIALINFO_LEGACY_HEADERS.items() if canonical == field_name),
            None,
        )
        if legacy_name is not None:
            column_present = any(field_non_empty(record.get(legacy_name)) for record in file_rows)
    if column_present:
        return STATUS_FOUND
    return STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED


def _check_dataset_specific_row(
    row: Dict[str, str],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    datatype_id: Optional[str],
) -> str:
    from src.table_placement import collect_dataset_specific_session_fields

    resolved = resolve_row_source_file(row, dataset_dir, session_dir, session_record, datatype_id=datatype_id)
    if resolved is None:
        return STATUS_NOT_FOUND_RECOMMENDED

    if resolved.path.suffix.lower() == ".json":
        schema = normalize_schema_keys(load_json(resolved.path))
        extras = [key for key, value in schema.items() if field_non_empty(value)]
        return STATUS_FOUND if extras else STATUS_NOT_FOUND_RECOMMENDED

    if _row_targets_sessioninfo(row, resolved.path):
        extras = collect_dataset_specific_session_fields(session_record, [])
        return STATUS_FOUND if extras else STATUS_NOT_FOUND_RECOMMENDED

    rows = read_csv_rows(resolved.path)
    if not rows:
        return STATUS_NOT_FOUND_RECOMMENDED
    known_from_table = set(known_sessioninfo_fieldnames([]))
    extras_exist = any(
        key not in known_from_table and field_non_empty(value) for key, value in rows[0].items()
    )
    return STATUS_FOUND if extras_exist else STATUS_NOT_FOUND_RECOMMENDED


def build_session_validation_matrix(config: ValidationConfig) -> List[Dict[str, str]]:
    table_rows = read_conversion_table(config.conversion_table_path)
    table_rows = filter_dev_stage(table_rows, config.dev_max_stage)
    dataset_id = dataset_id_from_dir(config.dataset_dir)
    session_record = load_session_record(config.dataset_dir, config.session_dir, dataset_id)
    discovered_datatypes = discover_datatypes_from_files(
        config.session_dir,
        dataset_id,
        session_record,
    )
    expanded_rows = expand_rows_for_datatypes(table_rows, discovered_datatypes)
    session_column = session_key(session_record)

    matrix_rows: List[Dict[str, str]] = []
    for row in expanded_rows:
        if is_informational_row(row):
            continue
        matrix_rows.append(
            {
                "check": _check_name_for_row(row),
                session_column: _check_row(
                    row,
                    config.dataset_dir,
                    config.session_dir,
                    session_record,
                    discovered_datatypes,
                ),
            }
        )
    return matrix_rows


def build_discovery_ledger(
    config: ValidationConfig,
) -> List[Dict[str, str]]:
    table_rows = read_conversion_table(config.conversion_table_path)
    table_rows = filter_dev_stage(table_rows, config.dev_max_stage)
    dataset_id = dataset_id_from_dir(config.dataset_dir)
    session_record = load_session_record(config.dataset_dir, config.session_dir, dataset_id)
    discovered_datatypes = discover_datatypes_from_files(
        config.session_dir,
        dataset_id,
        session_record,
    )
    expanded_rows = expand_rows_for_datatypes(table_rows, discovered_datatypes)

    ledger_rows: List[Dict[str, str]] = []
    for row in expanded_rows:
        ledger_row = copy.deepcopy(row)
        datatype_id = str(row.get("datatype_id", "")).strip() or None
        applies = row_applies_to_session(row, discovered_datatypes, datatype_id=datatype_id)
        ledger_row["applies_to_session"] = str(applies)
        if is_informational_row(row):
            ledger_row["discovered"] = "informational"
            ledger_row["source_path"] = ""
            ledger_rows.append(ledger_row)
            continue

        resolved = resolve_row_source_file(
            row,
            config.dataset_dir,
            config.session_dir,
            session_record,
            datatype_id=datatype_id,
        )
        if not applies:
            ledger_row["discovered"] = STATUS_NOT_APPLICABLE
            ledger_row["source_path"] = ""
        elif resolved is None:
            ledger_row["discovered"] = (
                STATUS_MISSING_REQUIRED if _is_required(row) else STATUS_NOT_FOUND_RECOMMENDED
            )
            ledger_row["source_path"] = ""
        else:
            ledger_row["discovered"] = STATUS_FOUND
            ledger_row["source_path"] = str(resolved.path)
        ledger_rows.append(ledger_row)
    return ledger_rows


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


def write_discovery_ledger_csv(ledger_rows: List[Dict[str, str]], output_csv: Path) -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    if not ledger_rows:
        return output_csv
    headers = list(ledger_rows[0].keys())
    for row in ledger_rows:
        for key in row.keys():
            if key not in headers:
                headers.append(key)
    extra_headers = ["applies_to_session", "discovered", "source_path"]
    for header in extra_headers:
        if header not in headers:
            headers.append(header)

    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in ledger_rows:
            writer.writerow(row)
    return output_csv


def write_convention_report_csv(issues: Sequence[ConventionIssue], output_csv: Path) -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    headers = ["check", "severity", "status", "detail", "path", "fieldname", "expected", "observed", "table_gap"]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for issue in issues:
            writer.writerow(
                {
                    "check": issue.check,
                    "severity": issue.severity,
                    "status": issue.status,
                    "detail": issue.detail,
                    "path": issue.path,
                    "fieldname": issue.fieldname,
                    "expected": issue.expected,
                    "observed": issue.observed,
                    "table_gap": issue.table_gap,
                }
            )
    return output_csv


def write_format_summary_csv(results: Sequence[SessionFormatResult], output_csv: Path) -> Path:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "session",
        "session_dir",
        "fail_count",
        "warn_count",
        "pass_count",
        "table_gap_count",
        "report_file",
        "exit_should_fail",
    ]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for result in results:
            pass_count = sum(1 for issue in result.issues if issue.status == STATUS_PASS)
            gap_count = sum(1 for issue in result.issues if issue.status == STATUS_TABLE_GAP_TYPED)
            report_file = result.session_dir / "surlab_format_validation_report.csv"
            writer.writerow(
                {
                    "session": result.session_key,
                    "session_dir": str(result.session_dir),
                    "fail_count": result.fail_count,
                    "warn_count": result.warn_count,
                    "pass_count": pass_count,
                    "table_gap_count": gap_count,
                    "report_file": str(report_file),
                    "exit_should_fail": str(result.fail_count > 0),
                }
            )
    return output_csv


def _is_non_format_path(path: Path) -> bool:
    name_lower = path.name.lower()
    if path.suffix.lower() in NON_FORMAT_SUFFIXES:
        return True
    if any(marker in name_lower for marker in NON_FORMAT_NAME_MARKERS):
        return True
    if "roundtrip_surformat" in path.parts:
        return True
    return False


def _session_info_paths(dataset_dir: Path, session_dir: Path, dataset_id: str) -> List[Path]:
    paths: List[Path] = []
    local = find_session_info_csv(session_dir, "sessionInfo_single_session.csv")
    if local is not None:
        paths.append(local)
    dataset_expected = find_session_info_csv(dataset_dir, f"sessionInfo_{dataset_id}.csv")
    if dataset_expected is not None and dataset_expected not in paths:
        paths.append(dataset_expected)
    return paths


def _find_schema_file(session_dir: Path, datatype_id: str) -> Optional[Path]:
    for path in sorted(session_dir.glob(f"{datatype_id}_schema*.json")):
        if _is_non_format_path(path):
            continue
        return path
    return None


def _issues_from_presence_matrix(
    matrix_rows: List[Dict[str, str]],
    session_column: str,
) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    for row in matrix_rows:
        status = row.get(session_column, "")
        check = row.get("check", "")
        if status == STATUS_MISSING_REQUIRED:
            issues.append(
                ConventionIssue(
                    check=f"presence|{check}",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=STATUS_MISSING_REQUIRED,
                    expected="present",
                    observed="missing",
                )
            )
        elif status == STATUS_NOT_FOUND_RECOMMENDED:
            issues.append(
                ConventionIssue(
                    check=f"presence|{check}",
                    severity=SEVERITY_WARN,
                    status=STATUS_WARN,
                    detail=STATUS_NOT_FOUND_RECOMMENDED,
                    expected="present (recommended)",
                    observed="missing",
                )
            )
    return issues


def _issues_legacy_headers_on_disk(csv_path: Path, kind: str) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    rows = read_csv_rows(csv_path)
    if not rows:
        return issues
    headers = set(rows[0].keys())
    if kind == "sessionInfo":
        alias_map = LEGACY_TO_CANONICAL_FIELD_MAP
    elif kind == "trialInfo":
        alias_map = TRIALINFO_LEGACY_HEADERS
    else:
        alias_map = METADATA_LEGACY_HEADERS
    for legacy_name, canonical_name in alias_map.items():
        if legacy_name in headers:
            issues.append(
                ConventionIssue(
                    check=f"naming|legacy_header|{legacy_name}",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=f"on-disk header {legacy_name!r} should be {canonical_name!r}",
                    path=str(csv_path),
                    fieldname=legacy_name,
                    expected=canonical_name,
                    observed=legacy_name,
                )
            )
    return issues


def _issues_schema_legacy_keys(schema_path: Path) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    payload = load_json(schema_path)
    for legacy_key, canonical_key in SCHEMA_LEGACY_KEYS.items():
        if legacy_key in payload and canonical_key not in payload:
            issues.append(
                ConventionIssue(
                    check=f"naming|legacy_schema_key|{legacy_key}",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=f"schema key {legacy_key!r} should be {canonical_key!r}",
                    path=str(schema_path),
                    fieldname=legacy_key,
                    expected=canonical_key,
                    observed=legacy_key,
                )
            )
    return issues


def _issues_value_types_for_row(
    row: Dict[str, str],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    datatype_id = str(row.get("datatype_id", "")).strip() or None
    if not row_applies_to_session(row, discovered_datatypes, datatype_id=datatype_id):
        return issues
    if is_informational_row(row):
        return issues

    field_name = str(row.get("fieldname_surlab", "")).strip()
    if not field_name or field_name in {"NA", "N/A", "dataset_specific", "(derived_file_identifier)", "(all columns above)"}:
        return issues
    if field_name.startswith("("):
        return issues
    if _is_not_recommended(row):
        return issues

    row_type = str(row.get("row_type", "")).strip()
    if row_type in {"data_array", "timestamps_array"}:
        return issues

    nwb_type = str(row.get("nwb_type", "")).strip()
    units_hint = str(row.get("units", "")).strip()
    resolved = resolve_row_source_file(row, dataset_dir, session_dir, session_record, datatype_id=datatype_id)
    if resolved is None:
        return issues

    values: List[Tuple[object, str]] = []
    if resolved.path.suffix.lower() == ".json":
        schema = load_json(resolved.path)
        raw = schema.get(field_name)
        if raw is None:
            raw = normalize_schema_keys(schema).get(field_name)
        if raw is not None and not _is_missing_token(raw):
            values.append((raw, str(resolved.path)))
    elif _row_targets_sessioninfo(row, resolved.path):
        value = session_record.get(field_name, "")
        if not _is_missing_token(value):
            values.append((value, str(resolved.path)))
    else:
        file_rows = read_csv_rows(resolved.path)
        legacy_lookup = None
        if "trialinfo" in resolved.path.name.lower():
            legacy_lookup = {
                canonical: legacy for legacy, canonical in TRIALINFO_LEGACY_HEADERS.items()
            }
        for index, record in enumerate(file_rows):
            if field_name in METADATA_LEGACY_HEADERS.values() or field_name in METADATA_LEGACY_HEADERS:
                normalized = normalize_metadata_row(record)
                value = normalized.get(field_name, record.get(field_name, ""))
            elif legacy_lookup is not None and field_name in legacy_lookup:
                legacy_name = legacy_lookup[field_name]
                value = record.get(field_name, "")
                if _is_missing_token(value):
                    value = record.get(legacy_name, "")
            else:
                value = record.get(field_name, "")
            if _is_missing_token(value):
                continue
            values.append((value, f"{resolved.path}#row{index}"))

    for value, path_label in values:
        status, detail, table_gap = assess_value_type(value, nwb_type, field_name, units_hint)
        if status == STATUS_SKIP:
            continue
        if status == STATUS_PASS:
            issues.append(
                ConventionIssue(
                    check=f"type|{_check_name_for_row(row)}",
                    severity=SEVERITY_INFO,
                    status=STATUS_PASS,
                    detail="",
                    path=path_label,
                    fieldname=field_name,
                    expected=nwb_type,
                    observed=_normalize_compare_text(value),
                )
            )
        elif status == STATUS_FAIL:
            issues.append(
                ConventionIssue(
                    check=f"type|{_check_name_for_row(row)}",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=detail,
                    path=path_label,
                    fieldname=field_name,
                    expected=nwb_type,
                    observed=_normalize_compare_text(value),
                    table_gap=table_gap,
                )
            )
        elif status == STATUS_WARN:
            issues.append(
                ConventionIssue(
                    check=f"type|{_check_name_for_row(row)}",
                    severity=SEVERITY_WARN,
                    status=STATUS_WARN,
                    detail=detail,
                    path=path_label,
                    fieldname=field_name,
                    expected=nwb_type,
                    observed=_normalize_compare_text(value),
                )
            )
        elif status == STATUS_TABLE_GAP_TYPED:
            issues.append(
                ConventionIssue(
                    check=f"type|{_check_name_for_row(row)}",
                    severity=SEVERITY_WARN,
                    status=STATUS_TABLE_GAP_TYPED,
                    detail=detail,
                    path=path_label,
                    fieldname=field_name,
                    expected=nwb_type,
                    observed=_normalize_compare_text(value),
                    table_gap=table_gap or detail,
                )
            )
    return issues


def _issues_sessioninfo_schema_conflicts(
    table_rows: List[Dict[str, str]],
    session_dir: Path,
    session_record: Dict[str, str],
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    for row in table_rows:
        if is_informational_row(row):
            continue
        filename = str(row.get("surlab_filename", "")).lower()
        if "sessioninfo" not in filename:
            continue
        datatype_id = str(row.get("datatype_id", "")).strip() or None
        if not row_applies_to_session(row, discovered_datatypes, datatype_id=datatype_id):
            continue
        mirror = _parse_schema_mirror(str(row.get("notes", "")))
        if mirror is None:
            continue
        stream_id, schema_key = mirror
        field_name = str(row.get("fieldname_surlab", "")).strip()
        session_val = _normalize_compare_text(session_record.get(field_name, ""))
        schema_path = _find_schema_file(session_dir, stream_id)
        if schema_path is None:
            continue
        schema = normalize_schema_keys(load_json(schema_path))
        schema_val = _normalize_compare_text(schema.get(schema_key, ""))
        if session_val and schema_val and session_val != schema_val:
            issues.append(
                ConventionIssue(
                    check=f"conflict|sessionInfo_vs_schema|{field_name}",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail="sessionInfo and schema mirror disagree",
                    path=str(schema_path),
                    fieldname=field_name,
                    expected=session_val,
                    observed=schema_val,
                )
            )
        elif session_val and schema_val and session_val == schema_val:
            issues.append(
                ConventionIssue(
                    check=f"conflict|sessionInfo_vs_schema|{field_name}",
                    severity=SEVERITY_INFO,
                    status=STATUS_PASS,
                    detail="sessionInfo and schema agree",
                    path=str(schema_path),
                    fieldname=field_name,
                    expected=session_val,
                    observed=schema_val,
                )
            )
    return issues


def _issues_flag_file_consistency(
    session_dir: Path,
    session_record: Dict[str, str],
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    modality_flags = ("spikeTimes", "lfp", "spikeWaves", "trialInfo", "behEvents")
    for modality in modality_flags:
        flag_raw = session_record.get(modality, "")
        flag_on = truthy_flag(flag_raw)
        files_present = modality in discovered_datatypes
        if flag_on and not files_present:
            issues.append(
                ConventionIssue(
                    check=f"consistency|flag_vs_files|{modality}",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=f"sessionInfo {modality}=1 but no matching files discovered",
                    path=str(session_dir),
                    fieldname=modality,
                    expected="files present",
                    observed="missing files",
                )
            )
        elif files_present and not flag_on and str(flag_raw).strip() != "":
            issues.append(
                ConventionIssue(
                    check=f"consistency|flag_vs_files|{modality}",
                    severity=SEVERITY_WARN,
                    status=STATUS_WARN,
                    detail=f"files for {modality} present but sessionInfo flag is {flag_raw!r}",
                    path=str(session_dir),
                    fieldname=modality,
                    expected="1",
                    observed=str(flag_raw),
                )
            )
        elif files_present and str(flag_raw).strip() == "":
            issues.append(
                ConventionIssue(
                    check=f"consistency|flag_vs_files|{modality}",
                    severity=SEVERITY_WARN,
                    status=STATUS_WARN,
                    detail=f"files for {modality} present but sessionInfo flag column empty/absent",
                    path=str(session_dir),
                    fieldname=modality,
                    expected="1",
                    observed="",
                )
            )
    return issues


def _issues_not_recommended_columns_present(
    expanded_rows: Sequence[Dict[str, str]],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    """Warn when a not-recommended table column is present on disk."""
    issues: List[ConventionIssue] = []
    for row in expanded_rows:
        if not _is_not_recommended(row):
            continue
        if not row_applies_to_session(
            row,
            discovered_datatypes,
            datatype_id=str(row.get("datatype_id", "")).strip() or None,
        ):
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if not field_name:
            continue
        resolved = resolve_row_source_file(
            row,
            dataset_dir,
            session_dir,
            session_record,
            datatype_id=str(row.get("datatype_id", "")).strip() or None,
        )
        if resolved is None:
            continue
        file_rows = read_csv_rows(resolved.path)
        if not file_rows:
            continue
        if field_name not in file_rows[0]:
            continue
        rationale = str(row.get("mapping_rationale", "")).strip()
        notes = str(row.get("notes", "")).strip()
        detail = rationale or notes or f"column {field_name!r} is not-recommended for this file"
        issues.append(
            ConventionIssue(
                check=f"presence|not-recommended|{_check_name_for_row(row)}",
                severity=SEVERITY_WARN,
                status=STATUS_WARN,
                detail=detail,
                path=str(resolved.path),
                fieldname=field_name,
                expected="absent (not-recommended)",
                observed="column present",
            )
        )
    return issues


def _issues_spikewaves_area_vs_spiketimes(
    session_dir: Path,
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    """Warn on spikeWaves area column; fail when unit area disagrees with spikeTimes."""
    if "spikeWaves" not in discovered_datatypes:
        return []

    issues: List[ConventionIssue] = []
    waves_paths = [
        path
        for path in sorted(session_dir.glob("spikeWaves_metadata*.csv"))
        if not _is_non_format_path(path)
    ]
    if not waves_paths:
        return issues

    from src.data_io import normalize_metadata_row

    times_path = next(
        (path for path in sorted(session_dir.glob("spikeTimes_metadata*.csv")) if not _is_non_format_path(path)),
        None,
    )
    times_area_by_unit: Dict[str, str] = {}
    if times_path is not None:
        for index, record in enumerate(read_csv_rows(times_path)):
            normalized = normalize_metadata_row(record)
            unit_id = _normalize_compare_text(normalized.get("unit_ID", record.get("unit_ID", "")))
            area = _normalize_compare_text(normalized.get("area", record.get("area", "")))
            if unit_id and area:
                times_area_by_unit[unit_id] = area

    for waves_path in waves_paths:
        wave_rows = read_csv_rows(waves_path)
        if not wave_rows:
            continue
        if "area" not in wave_rows[0]:
            continue

        for index, record in enumerate(wave_rows):
            normalized = normalize_metadata_row(record)
            unit_id = _normalize_compare_text(normalized.get("unit_ID", record.get("unit_ID", "")))
            wave_area = _normalize_compare_text(normalized.get("area", record.get("area", "")))
            if not unit_id or not wave_area:
                continue
            times_area = times_area_by_unit.get(unit_id, "")
            if not times_area:
                continue
            if wave_area != times_area:
                issues.append(
                    ConventionIssue(
                        check=f"consistency|spikeWaves_area_vs_spikeTimes|unit_ID={unit_id}",
                        severity=SEVERITY_FAIL,
                        status=STATUS_FAIL,
                        detail=(
                            f"unit_ID {unit_id}: spikeWaves_metadata area={wave_area!r} "
                            f"!= spikeTimes_metadata area={times_area!r}"
                        ),
                        path=f"{waves_path}#row{index}",
                        fieldname="area",
                        expected=times_area,
                        observed=wave_area,
                    )
                )
    return issues


def _issues_unexpected_files(session_dir: Path, discovered_datatypes: Set[str]) -> List[ConventionIssue]:
    """Flag files that look like SurLab data but do not match known datatype stems."""
    issues: List[ConventionIssue] = []
    known_prefixes = set(discovered_datatypes)
    known_prefixes.update({"sessionInfo", "sessionsInfo", "trialInfo", "experimentDescr"})
    for path in sorted(session_dir.iterdir()):
        if not path.is_file():
            continue
        if _is_non_format_path(path):
            continue
        if path.suffix.lower() not in SURLAB_DATA_SUFFIXES:
            issues.append(
                ConventionIssue(
                    check=f"naming|unexpected_suffix|{path.name}",
                    severity=SEVERITY_WARN,
                    status=STATUS_WARN,
                    detail="file suffix not in SurLab data set (.csv/.json/.mat/.npz/.pdf)",
                    path=str(path),
                    observed=path.suffix,
                )
            )
            continue
        stem = path.name
        matched = False
        for prefix in known_prefixes:
            if stem.startswith(prefix):
                matched = True
                break
        # Common stream patterns: <prefix>_traces_*, <prefix>_behTSeries_*
        if not matched:
            for token in ("_traces_", "_behTSeries_", "_behEvents_"):
                if token in stem:
                    matched = True
                    break
        if not matched and path.suffix.lower() in {".mat", ".npz", ".csv", ".json"}:
            issues.append(
                ConventionIssue(
                    check=f"naming|unrecognized_file|{path.name}",
                    severity=SEVERITY_WARN,
                    status=STATUS_WARN,
                    detail="filename does not match a known datatype / sessionInfo / trialInfo pattern",
                    path=str(path),
                    observed=path.name,
                )
            )
    return issues


def _schema_int_value(schema: Dict[str, object], key: str) -> Optional[int]:
    raw = schema.get(key)
    if raw is None or _is_missing_token(raw):
        return None
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def _array_row_for_datatype(
    expanded_rows: Sequence[Dict[str, str]],
    datatype_id: str,
    row_type: str,
) -> Optional[Dict[str, str]]:
    for row in expanded_rows:
        if str(row.get("row_type", "")).strip() != row_type:
            continue
        if is_informational_row(row):
            continue
        bound_id = str(row.get("datatype_id", "")).strip()
        if bound_id and bound_id != datatype_id:
            continue
        if bound_id == datatype_id:
            return row
        condition_id = condition_datatype_id(str(row.get("requirement_condition", "")).strip())
        if condition_id == datatype_id:
            return row
        pattern = str(row.get("surlab_filename", "")).strip()
        if pattern.startswith(f"{datatype_id}_") or pattern.startswith(f"{datatype_id}."):
            return row
    return None


def _datatype_uses_object_array_layout(datatype_id: str, data_row: Optional[Dict[str, str]]) -> bool:
    if datatype_id == "spikeTimes":
        return True
    if datatype_id.endswith("_behEvents"):
        return True
    if data_row is not None:
        nwb_location = str(data_row.get("nwb_location", "")).strip()
        nwb_fieldname = str(data_row.get("nwb_fieldname", "")).strip()
        if nwb_location == "NWBFile/units" and nwb_fieldname == "spike_times":
            return True
        if nwb_fieldname == "timestamp" and "behEvents" in nwb_location:
            return True
    return False


def _numeric_array_is_float64_compatible(array: object) -> Tuple[bool, str]:
    values = np.asarray(array)
    if values.dtype == object:
        return False, "object dtype (expected numeric float64-compatible array)"
    if not np.issubdtype(values.dtype, np.number):
        return False, f"dtype {values.dtype} is not numeric"
    try:
        values.astype(float)
    except (TypeError, ValueError):
        return False, "values not castable to float"
    return True, ""


def _object_array_is_float64_compatible(array: object) -> Tuple[bool, str]:
    flat = np.asarray(array).ravel()
    for index, item in enumerate(flat):
        try:
            values = np.asarray(item, dtype=float).ravel()
        except (TypeError, ValueError):
            return False, f"object slot {index} not float-compatible"
        if values.size == 0:
            continue
        if not np.issubdtype(values.dtype, np.number):
            return False, f"object slot {index} has non-numeric dtype {values.dtype}"
    return True, ""


def _issues_schema_layout_indices(
    schema_path: Path,
    schema: Dict[str, object],
) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    x_size = _schema_int_value(schema, "X_size")
    y_size = _schema_int_value(schema, "Y_size")
    for key, expected_size in (("X_idx", x_size), ("Y_idx", y_size)):
        if expected_size is None:
            continue
        raw = schema.get(key)
        if raw is None or _is_missing_token(raw):
            continue
        sequence = _as_sequence(raw)
        if sequence is None:
            continue
        if len(sequence) != expected_size:
            issues.append(
                ConventionIssue(
                    check=f"layout|schema|len({key})",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=f"len({key})={len(sequence)} != {key.replace('_idx', '_size')}={expected_size}",
                    path=str(schema_path),
                    fieldname=key,
                    expected=str(expected_size),
                    observed=str(len(sequence)),
                )
            )
    return issues


def _metadata_row_count(session_dir: Path, datatype_id: str) -> Optional[int]:
    matches = sorted(session_dir.glob(f"{datatype_id}_metadata*.csv"))
    for path in matches:
        if _is_non_format_path(path):
            continue
        rows = read_csv_rows(path)
        return len(rows)
    return None


def _issues_array_files_for_datatype(
    datatype_id: str,
    expanded_rows: Sequence[Dict[str, str]],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    """Load .mat/.npz arrays and check dtype/shape against table nwb_type and schema."""
    issues: List[ConventionIssue] = []
    data_row = _array_row_for_datatype(expanded_rows, datatype_id, "data_array")
    timestamps_row = _array_row_for_datatype(expanded_rows, datatype_id, "timestamps_array")
    if data_row is None and timestamps_row is None:
        return issues

    schema_path = _find_schema_file(session_dir, datatype_id)
    schema: Dict[str, object] = {}
    if schema_path is not None:
        schema = normalize_schema_keys(load_json(schema_path))
        issues.extend(_issues_schema_layout_indices(schema_path, schema))

    x_size = _schema_int_value(schema, "X_size")
    y_size = _schema_int_value(schema, "Y_size")
    object_layout = _datatype_uses_object_array_layout(datatype_id, data_row)

    data_path: Optional[Path] = None
    if data_row is not None and row_applies_to_session(data_row, discovered_datatypes, datatype_id=datatype_id):
        resolved = resolve_row_source_file(
            data_row,
            dataset_dir,
            session_dir,
            session_record,
            datatype_id=datatype_id,
        )
        if resolved is not None:
            data_path = resolved.path

    timestamps_path: Optional[Path] = None
    if timestamps_row is not None and row_applies_to_session(
        timestamps_row, discovered_datatypes, datatype_id=datatype_id
    ):
        resolved = resolve_row_source_file(
            timestamps_row,
            dataset_dir,
            session_dir,
            session_record,
            datatype_id=datatype_id,
        )
        if resolved is not None:
            timestamps_path = resolved.path

    loaded_data = None
    data_time_length: Optional[int] = None
    data_axis1_length: Optional[int] = None

    if data_path is not None:
        try:
            if object_layout:
                unit_series = load_spike_times_by_unit(data_path) if datatype_id == "spikeTimes" else None
                if unit_series is not None:
                    container = np.empty((1, len(unit_series)), dtype=object)
                    for index, values in enumerate(unit_series):
                        container[0, index] = np.asarray(values, dtype=float).ravel()
                    loaded_data = container
                    data_axis1_length = len(unit_series)
                    ok, detail = _object_array_is_float64_compatible(loaded_data)
                else:
                    loaded_data = load_numeric_array(data_path)
                    ok, detail = _object_array_is_float64_compatible(loaded_data)
                    data_axis1_length = len(np.asarray(loaded_data).ravel())
            else:
                loaded_data = load_numeric_array(data_path)
                ok, detail = _numeric_array_is_float64_compatible(loaded_data)
                if loaded_data.ndim == 1:
                    data_time_length = int(loaded_data.shape[0])
                    data_axis1_length = 1
                elif loaded_data.ndim >= 2:
                    data_time_length = int(loaded_data.shape[0])
                    data_axis1_length = int(loaded_data.shape[1])
        except Exception as exc:
            ok, detail = False, f"not loadable: {exc}"
            loaded_data = None

        if ok:
            issues.append(
                ConventionIssue(
                    check=f"array|load|{datatype_id}|data",
                    severity=SEVERITY_INFO,
                    status=STATUS_PASS,
                    detail="loadable; float64-compatible",
                    path=str(data_path),
                    expected=str(data_row.get("nwb_type", "")) if data_row else "",
                    observed=str(getattr(loaded_data, "shape", "")),
                )
            )
        else:
            issues.append(
                ConventionIssue(
                    check=f"array|load|{datatype_id}|data",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=detail,
                    path=str(data_path),
                    expected=str(data_row.get("nwb_type", "")) if data_row else "array_of_float64",
                    observed="load failed" if loaded_data is None else str(getattr(loaded_data, "dtype", "")),
                )
            )

        if ok and loaded_data is not None:
            if object_layout and x_size is not None and data_axis1_length is not None:
                if data_axis1_length != x_size:
                    issues.append(
                        ConventionIssue(
                            check=f"array|shape|{datatype_id}|object_slots",
                            severity=SEVERITY_FAIL,
                            status=STATUS_FAIL,
                            detail=f"object-array slot count {data_axis1_length} != schema X_size={x_size}",
                            path=str(data_path),
                            fieldname="X_size",
                            expected=str(x_size),
                            observed=str(data_axis1_length),
                        )
                    )
            elif not object_layout and loaded_data.ndim >= 1:
                if x_size is not None and data_time_length is not None:
                    if data_time_length != x_size:
                        transposed = (
                            y_size is not None
                            and data_axis1_length is not None
                            and data_time_length == y_size
                            and data_axis1_length == x_size
                        )
                        detail = (
                            f"data axis-0 length {data_time_length} != schema X_size={x_size}"
                            + (" (possible transpose: axis 0=time)" if transposed else "")
                        )
                        issues.append(
                            ConventionIssue(
                                check=f"array|shape|{datatype_id}|X_size",
                                severity=SEVERITY_FAIL,
                                status=STATUS_FAIL,
                                detail=detail,
                                path=str(data_path),
                                fieldname="X_size",
                                expected=str(x_size),
                                observed=str(data_time_length),
                            )
                        )
                if y_size is not None and data_axis1_length is not None and data_axis1_length != y_size:
                    issues.append(
                        ConventionIssue(
                            check=f"array|shape|{datatype_id}|Y_size",
                            severity=SEVERITY_FAIL,
                            status=STATUS_FAIL,
                            detail=f"data axis-1 length {data_axis1_length} != schema Y_size={y_size}",
                            path=str(data_path),
                            fieldname="Y_size",
                            expected=str(y_size),
                            observed=str(data_axis1_length),
                        )
                    )
                metadata_count = _metadata_row_count(session_dir, datatype_id)
                if metadata_count is not None and data_axis1_length is not None and metadata_count != data_axis1_length:
                    issues.append(
                        ConventionIssue(
                            check=f"array|shape|{datatype_id}|metadata_rows",
                            severity=SEVERITY_WARN,
                            status=STATUS_WARN,
                            detail=(
                                f"metadata row count {metadata_count} != data axis-1 length "
                                f"{data_axis1_length}"
                            ),
                            path=str(data_path),
                            expected=str(data_axis1_length),
                            observed=str(metadata_count),
                        )
                    )

    loaded_timestamps = None
    if timestamps_path is not None:
        try:
            loaded_timestamps = load_numeric_array(timestamps_path)
            ok, detail = _numeric_array_is_float64_compatible(loaded_timestamps)
            if ok and loaded_timestamps.ndim > 1:
                squeezed = loaded_timestamps.squeeze()
                if squeezed.ndim != 1:
                    ok, detail = False, f"timestamps ndim={loaded_timestamps.ndim} (expected 1-D)"
                else:
                    loaded_timestamps = squeezed
        except Exception as exc:
            ok, detail = False, f"not loadable: {exc}"
            loaded_timestamps = None

        if ok:
            issues.append(
                ConventionIssue(
                    check=f"array|load|{datatype_id}|timestamps",
                    severity=SEVERITY_INFO,
                    status=STATUS_PASS,
                    detail="loadable; 1-D float64-compatible",
                    path=str(timestamps_path),
                    expected=str(timestamps_row.get("nwb_type", "")) if timestamps_row else "",
                    observed=str(getattr(loaded_timestamps, "shape", "")),
                )
            )
        else:
            issues.append(
                ConventionIssue(
                    check=f"array|load|{datatype_id}|timestamps",
                    severity=SEVERITY_FAIL,
                    status=STATUS_FAIL,
                    detail=detail,
                    path=str(timestamps_path),
                    expected="array_of_float64 1-D",
                    observed="load failed" if loaded_timestamps is None else str(getattr(loaded_timestamps, "shape", "")),
                )
            )

        if ok and loaded_timestamps is not None and loaded_data is not None and data_time_length is not None:
            ts_len = int(np.asarray(loaded_timestamps).ravel().shape[0])
            if ts_len != data_time_length:
                issues.append(
                    ConventionIssue(
                        check=f"array|shape|{datatype_id}|timestamps_vs_data",
                        severity=SEVERITY_FAIL,
                        status=STATUS_FAIL,
                        detail=f"len(timestamps)={ts_len} != data axis-0={data_time_length}",
                        path=str(timestamps_path),
                        expected=str(data_time_length),
                        observed=str(ts_len),
                    )
                )

    return issues


def _issues_array_files_for_session(
    expanded_rows: Sequence[Dict[str, str]],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    issues: List[ConventionIssue] = []
    for datatype_id in sorted(discovered_datatypes):
        if datatype_id == "trialInfo":
            continue
        issues.extend(
            _issues_array_files_for_datatype(
                datatype_id=datatype_id,
                expanded_rows=expanded_rows,
                dataset_dir=dataset_dir,
                session_dir=session_dir,
                session_record=session_record,
                discovered_datatypes=discovered_datatypes,
            )
        )
    return issues


def _issues_traces_microscope_consistency(
    session_record: Dict[str, str],
    discovered_datatypes: Set[str],
) -> List[ConventionIssue]:
    """Warn when multiple traces streams set microscope and values disagree."""
    traces_ids = sorted(dt for dt in discovered_datatypes if dt.endswith("_traces"))
    if len(traces_ids) < 2:
        return []

    values: Dict[str, str] = {}
    for datatype_id in traces_ids:
        field_name = f"{datatype_id}_microscope"
        text = _normalize_compare_text(session_record.get(field_name, ""))
        if text:
            values[datatype_id] = text

    if len(values) < 2 or len(set(values.values())) <= 1:
        return []

    detail = "; ".join(f"{datatype_id}={value!r}" for datatype_id, value in values.items())
    return [
        ConventionIssue(
            check="consistency|traces_microscope|cross_stream",
            severity=SEVERITY_WARN,
            status=STATUS_WARN,
            detail=f"traces streams disagree on microscope identity: {detail}",
            path="sessionInfo",
            fieldname="microscope",
            expected="same Device.name when streams share one rig",
            observed=detail,
        )
    ]


def validate_session_format(config: ValidationConfig) -> SessionFormatResult:
    """Run presence matrix plus naming/type/consistency convention checks."""
    dataset_id = dataset_id_from_dir(config.dataset_dir)
    session_record = load_session_record(config.dataset_dir, config.session_dir, dataset_id)
    discovered_datatypes = discover_datatypes_from_files(
        config.session_dir,
        dataset_id,
        session_record,
    )
    table_rows = read_conversion_table(config.conversion_table_path)
    table_rows = filter_dev_stage(table_rows, config.dev_max_stage)
    expanded_rows = expand_rows_for_datatypes(table_rows, discovered_datatypes)

    matrix_rows = build_session_validation_matrix(config)
    session_column = session_key(session_record)
    issues: List[ConventionIssue] = []
    issues.extend(_issues_from_presence_matrix(matrix_rows, session_column))

    for info_path in _session_info_paths(config.dataset_dir, config.session_dir, dataset_id):
        issues.extend(_issues_legacy_headers_on_disk(info_path, "sessionInfo"))

    for path in sorted(config.session_dir.glob("*metadata*.csv")):
        if _is_non_format_path(path):
            continue
        issues.extend(_issues_legacy_headers_on_disk(path, "metadata"))

    for path in sorted(config.session_dir.glob("*trialInfo*.csv")):
        if _is_non_format_path(path):
            continue
        issues.extend(_issues_legacy_headers_on_disk(path, "trialInfo"))

    for path in sorted(config.session_dir.glob("*schema*.json")):
        if _is_non_format_path(path):
            continue
        issues.extend(_issues_schema_legacy_keys(path))

    for row in expanded_rows:
        issues.extend(
            _issues_value_types_for_row(
                row,
                config.dataset_dir,
                config.session_dir,
                session_record,
                discovered_datatypes,
            )
        )

    issues.extend(
        _issues_sessioninfo_schema_conflicts(
            expanded_rows,
            config.session_dir,
            session_record,
            discovered_datatypes,
        )
    )
    issues.extend(_issues_flag_file_consistency(config.session_dir, session_record, discovered_datatypes))
    issues.extend(_issues_traces_microscope_consistency(session_record, discovered_datatypes))
    issues.extend(
        _issues_not_recommended_columns_present(
            expanded_rows,
            config.dataset_dir,
            config.session_dir,
            session_record,
            discovered_datatypes,
        )
    )
    issues.extend(_issues_spikewaves_area_vs_spiketimes(config.session_dir, discovered_datatypes))
    issues.extend(_issues_unexpected_files(config.session_dir, discovered_datatypes))
    issues.extend(
        _issues_array_files_for_session(
            expanded_rows=expanded_rows,
            dataset_dir=config.dataset_dir,
            session_dir=config.session_dir,
            session_record=session_record,
            discovered_datatypes=discovered_datatypes,
        )
    )

    # Deduplicate identical fail/warn rows (type checks can repeat per trial row).
    issues = _dedupe_issues(issues)

    return SessionFormatResult(
        session_dir=config.session_dir,
        session_key=session_column,
        matrix_rows=matrix_rows,
        issues=issues,
    )


def _dedupe_issues(issues: List[ConventionIssue]) -> List[ConventionIssue]:
    """Keep all passes sparse; collapse repeated fail/warn with same check+detail."""
    result: List[ConventionIssue] = []
    seen_fail_keys: Set[str] = set()
    pass_budget: Dict[str, int] = {}
    for issue in issues:
        if issue.status == STATUS_PASS:
            count = pass_budget.get(issue.check, 0)
            if count >= 1:
                continue
            pass_budget[issue.check] = count + 1
            result.append(issue)
            continue
        key = f"{issue.check}|{issue.detail}|{issue.observed}|{issue.severity}"
        if key in seen_fail_keys:
            continue
        seen_fail_keys.add(key)
        result.append(issue)
    return result


def collect_table_gaps(issues: Sequence[ConventionIssue]) -> List[str]:
    """Unique table_gap notes for Task 1 follow-up."""
    gaps: List[str] = []
    seen: Set[str] = set()
    for issue in issues:
        text = (issue.table_gap or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        gaps.append(text)
    return gaps
