"""Write SurLab trialInfo.csv into an NWB Trials (TimeIntervals) table.

Column placement is driven by conversion-table rows with
``nwb_location`` under ``NWBFile/intervals/trials``. Legacy demo headers are
normalized in memory only (same policy as sessionInfo).
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.session_record import field_non_empty, read_csv_rows
from src.surlab_paths import resolve_session_file
from src.table_placement import PlacementContext, coerce_scalar, record_warning

logger = logging.getLogger(__name__)

# Input-only aliases for older trialInfo exports; validator uses canonical names.
LEGACY_TRIALINFO_FIELD_MAP = {
    "start_time": "start_time__s",
    "stop_time": "stop_time__s",
    "stim_onset": "stimulus_onset__s",
    "stim_offset": "stimulus_offset__s",
    "tone_freq": "tone_frequency__Hz",
    "tone_intensity": "tone_intensity__dB",
    "reaction_time": "reaction_time__s",
}


def apply_trial_info(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
) -> None:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "trialInfo.csv",
        context.session_record,
        datatype_id="trialInfo",
    )
    if resolved is None:
        return

    trial_rows = [_normalize_trial_row(row) for row in read_csv_rows(resolved.path)]
    if not trial_rows:
        record_warning(context, f"trialInfo file is empty: {resolved.path}")
        return

    field_map = _trial_field_map_from_table(context.table_rows)
    known_fields = set(field_map.keys())
    extras_present = _collect_extra_column_names(trial_rows, known_fields)

    registered_columns = _register_trial_columns(
        nwbfile, field_map, extras_present, trial_rows, context
    )

    added = 0
    for trial_row in trial_rows:
        trial_kwargs, skip_reason = _trial_row_to_kwargs(
            trial_row, field_map, extras_present, registered_columns, context
        )
        if skip_reason:
            record_warning(context, skip_reason)
            continue
        nwbfile.add_trial(**trial_kwargs)
        added += 1

    logger.info("Added %d trials from %s", added, resolved.path.name)


def _normalize_trial_row(raw_row: Dict[str, str]) -> Dict[str, str]:
    normalized = dict(raw_row)
    for legacy_name, canonical_name in LEGACY_TRIALINFO_FIELD_MAP.items():
        if canonical_name not in normalized and legacy_name in normalized:
            normalized[canonical_name] = normalized[legacy_name]
    return normalized


def _trial_field_map_from_table(table_rows: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Map SurLab fieldname -> {nwb_column, nwb_type, requirement_level}."""
    field_map: Dict[str, Dict[str, str]] = {}
    for row in table_rows:
        location = str(row.get("nwb_location", "")).strip()
        if "intervals/trials" not in location:
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if not field_name or field_name == "dataset_specific":
            continue
        nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
        if not nwb_fieldname or nwb_fieldname == "custom_columns":
            continue
        nwb_column = nwb_fieldname
        if nwb_column.startswith("custom_column_"):
            nwb_column = nwb_column[len("custom_column_") :]
        field_map[field_name] = {
            "nwb_column": nwb_column,
            "nwb_type": str(row.get("nwb_type", "str")).strip() or "str",
            "requirement_level": str(row.get("requirement_level", "optional")).strip().lower(),
        }
    return field_map


def _collect_extra_column_names(trial_rows: List[Dict[str, str]], known_fields: set[str]) -> List[str]:
    extras: List[str] = []
    seen = set()
    for trial_row in trial_rows:
        for key, value in trial_row.items():
            if key in known_fields or key in LEGACY_TRIALINFO_FIELD_MAP:
                continue
            if key in seen:
                continue
            if field_non_empty(value):
                seen.add(key)
                extras.append(key)
    return extras


def _columns_used_in_data(
    field_map: Dict[str, Dict[str, str]],
    extras_present: List[str],
    trial_rows: List[Dict[str, str]],
) -> Dict[str, str]:
    """nwb_column -> description for columns that appear in at least one row."""
    needed: Dict[str, str] = {}
    for field_name, spec in field_map.items():
        column_name = spec["nwb_column"]
        if column_name in {"start_time", "stop_time"}:
            continue
        if any(field_non_empty(row.get(field_name, "")) and not _is_missing_token(row.get(field_name, "")) for row in trial_rows):
            needed[column_name] = f"SurLab trialInfo column {field_name}"
    for extra_name in extras_present:
        needed[extra_name] = f"SurLab trialInfo dataset_specific column {extra_name}"
    return needed


def _register_trial_columns(
    nwbfile,
    field_map: Dict[str, Dict[str, str]],
    extras_present: List[str],
    trial_rows: List[Dict[str, str]],
    context: PlacementContext,
) -> Dict[str, str]:
    needed = _columns_used_in_data(field_map, extras_present, trial_rows)
    existing = set()
    if nwbfile.trials is not None:
        existing = set(nwbfile.trials.colnames)

    for column_name, description in needed.items():
        if column_name not in existing:
            nwbfile.add_trial_column(name=column_name, description=description)
    return needed


def _default_for_type(nwb_type: str) -> object:
    type_key = nwb_type.lower().replace("64", "").replace("32", "")
    if type_key in {"float", "float64"}:
        return float("nan")
    if type_key in {"int", "integer"}:
        return -1
    if type_key == "bool":
        return False
    return ""


def _trial_row_to_kwargs(
    trial_row: Dict[str, str],
    field_map: Dict[str, Dict[str, str]],
    extras_present: List[str],
    registered_columns: Dict[str, str],
    context: PlacementContext,
) -> Tuple[Dict[str, object], Optional[str]]:
    kwargs: Dict[str, object] = {}

    for required_field, nwb_name in (("start_time__s", "start_time"), ("stop_time__s", "stop_time")):
        raw = trial_row.get(required_field, "")
        if not field_non_empty(raw) or _is_missing_token(raw):
            return {}, f"Skipping trial row missing required {required_field}"
        try:
            kwargs[nwb_name] = float(str(raw).strip())
        except ValueError:
            return {}, f"Skipping trial row: {required_field}={raw!r} is not numeric"

    surlab_by_nwb = {spec["nwb_column"]: (field_name, spec) for field_name, spec in field_map.items()}
    for column_name in registered_columns:
        if column_name in surlab_by_nwb:
            field_name, spec = surlab_by_nwb[column_name]
            raw = trial_row.get(field_name, "")
            if not field_non_empty(raw) or _is_missing_token(raw):
                kwargs[column_name] = _default_for_type(spec["nwb_type"])
                continue
            coerced, ok = _coerce_trial_value(str(raw), spec["nwb_type"], field_name)
            if not ok:
                message = (
                    f"Could not coerce trialInfo.{field_name}={raw!r} to {spec['nwb_type']}; using default."
                )
                if message not in context.warnings:
                    record_warning(context, message)
                kwargs[column_name] = _default_for_type(spec["nwb_type"])
                continue
            kwargs[column_name] = coerced
            continue

        raw = trial_row.get(column_name, "")
        if field_non_empty(raw) and not _is_missing_token(raw):
            kwargs[column_name] = str(raw).strip()
        else:
            kwargs[column_name] = ""

    return kwargs, None


def _is_missing_token(value: object) -> bool:
    text = str(value).strip().lower()
    return text in {"", "nan", "na", "n/a", "none", "null"}


def _coerce_trial_value(raw: str, nwb_type: str, field_name: str) -> Tuple[object, bool]:
    cleaned = raw.strip()
    type_key = nwb_type.lower().replace("64", "").replace("32", "")

    if field_name == "correct":
        lowered = cleaned.lower()
        if lowered in {"1", "true", "yes", "correct"}:
            return 1, True
        if lowered in {"0", "false", "no", "error", "incorrect"}:
            return 0, True

    if type_key in {"float", "float64"}:
        parsed = _parse_leading_number(cleaned)
        if parsed is None:
            return cleaned, False
        return parsed, True

    if type_key in {"int", "integer"}:
        parsed = _parse_leading_number(cleaned)
        if parsed is None:
            return cleaned, False
        return int(parsed), True

    if type_key == "bool":
        return coerce_scalar(cleaned, "bool"), True

    try:
        return coerce_scalar(cleaned, type_key if type_key else "str"), True
    except (ValueError, TypeError):
        return cleaned, False


def _parse_leading_number(text: str) -> Optional[float]:
    match = re.match(r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)", text)
    if not match:
        return None
    value = float(match.group(1))
    if math.isnan(value):
        return None
    return value
