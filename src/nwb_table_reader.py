"""Table-driven NWB reads for reverse export (Task 4) and triangulation (Task 5)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ZERO_TIME_NOTES_PREFIX = "SurLab zero_time="

_SCHEMA_MIRROR_KEY_RE = re.compile(
    r"Legacy optional mirror:\s*\S+_schema\.json key (\S+)",
    re.IGNORECASE,
)
_SESSIONINFO_MIRROR_KEY_RE = re.compile(
    r"Legacy optional mirror of sessionInfo\s+(\S+)",
    re.IGNORECASE,
)

# Known modality prefixes for stream-scalar sessionInfo columns ({datatypeID}_{field}).
STREAM_SCALAR_PREFIXES = ("spikeTimes", "lfp", "spikeWaves")

# Maps conversion_table ``nwb_fieldname`` tokens to PyNWB Units column names (if present).
UNITS_COLUMN_LOOKUP: Dict[str, List[str]] = {
    "id": ["__units_id__"],
    "custom_column_depth__um": ["depth__um", "depth"],
    "custom_column_brain_area": ["brain_area", "area"],
    "custom_column_spike_sorting_ID": ["spike_sorting_ID", "sorting_id", "spikesorting_ID"],
    "custom_column_quality": ["quality"],
    "custom_column_grid_location": ["grid_location"],
    "custom_column_sampling_rate__Hz": ["sampling_rate__Hz", "sampling_rate"],
    "custom_column_data_unit_measurement": ["data_unit_measurement"],
    "custom_column_quality_metric_description": ["quality_metric", "quality_metric_description"],
    "custom_column_num_units": ["num_units"],
}


def schema_key_candidates(fieldname_surlab: str, notes: str = "") -> List[str]:
    """Derive unprefixed schema / key=value lookup keys from a table field + notes."""
    candidates: List[str] = []
    notes = notes or ""
    mirror_match = _SCHEMA_MIRROR_KEY_RE.search(notes)
    if mirror_match:
        candidates.append(mirror_match.group(1).rstrip("."))
    session_match = _SESSIONINFO_MIRROR_KEY_RE.search(notes)
    if session_match:
        session_field = session_match.group(1).rstrip(".")
        for prefix in STREAM_SCALAR_PREFIXES:
            token = prefix + "_"
            if session_field.startswith(token):
                candidates.append(session_field[len(token) :])
                break
        else:
            candidates.append(session_field)
    field = fieldname_surlab.strip()
    if field:
        candidates.append(field)
        for prefix in STREAM_SCALAR_PREFIXES:
            token = prefix + "_"
            if field.startswith(token):
                candidates.append(field[len(token) :])
                break
    # Preserve order, drop empties/duplicates.
    ordered: List[str] = []
    seen = set()
    for key in candidates:
        key = key.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def lookup_key_value_text(text: object, fieldname_surlab: str, notes: str = "") -> str:
    """Parse key=value;... text and return the value for this SurLab field."""
    description_map = parse_key_value_text(text)
    if not description_map:
        return ""
    for key in schema_key_candidates(fieldname_surlab, notes):
        if key in description_map:
            return description_map[key]
    return ""


def parse_nwb_target(nwb_location: str, nwb_fieldname: str) -> Tuple[str, str]:
    location = nwb_location.strip()
    attribute = nwb_fieldname.strip()
    if location == "NWBFile":
        return "file", attribute
    if location.startswith("NWBFile/general/subject"):
        return "subject", attribute
    if location.startswith("NWBFile/"):
        container = location.split("/", 1)[1]
        return container.lower(), attribute
    return location, attribute


def age_duration_to_days(age_value: str) -> str:
    normalized = age_value.strip()
    if not (normalized.startswith("P") and normalized.endswith("D")):
        return ""
    inner = normalized[1:-1]
    if inner.isdigit():
        return inner
    try:
        return str(int(float(inner)))
    except ValueError:
        return ""


def safe_join_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value if str(part).strip()]
        return ",".join(parts)
    return str(value).strip()


def format_nwb_scalar(value: object, nwb_type: str, fieldname_surlab: str = "") -> str:
    if value is None:
        return ""
    nwb_type = nwb_type.strip().lower()
    if nwb_type == "datetime" and isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if fieldname_surlab == "age__days" and nwb_type == "str":
        return age_duration_to_days(str(value))
    if isinstance(value, bool):
        return "1" if value else "0"
    return safe_join_text(value)


def parse_key_value_text(text: object) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    raw = safe_join_text(text)
    if not raw:
        return parsed
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment or "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            parsed[key] = value
    return parsed


def parse_zero_time_from_notes(notes: object) -> str:
    text = safe_join_text(notes)
    if not text:
        return ""
    for line in text.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line.startswith(ZERO_TIME_NOTES_PREFIX):
            return line[len(ZERO_TIME_NOTES_PREFIX) :].strip()
    if ZERO_TIME_NOTES_PREFIX in text:
        return text.split(ZERO_TIME_NOTES_PREFIX, 1)[1].strip().split()[0]
    return ""


def parse_experiment_description(text: object) -> Dict[str, str]:
    return parse_key_value_text(text)


def read_legacy_lab_meta_extras(nwbfile) -> Dict[str, str]:
    """Support older NWB files that used SurLabSessionInfoExtras LabMetaData."""
    import json

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
            extras[str(key)] = str(value)
    return extras


def _first_device(nwbfile):
    devices = getattr(nwbfile, "devices", None) or {}
    if not devices:
        return None
    units = getattr(nwbfile, "units", None)
    if units is not None:
        try:
            unit_count = len(units)
        except TypeError:
            unit_count = 0
        if unit_count > 0 and "device" in getattr(units, "colnames", []):
            device = units["device"][0]
            if device is not None:
                return device
    return next(iter(devices.values()))


def _first_processing_module(nwbfile):
    processing = getattr(nwbfile, "processing", None) or {}
    if not processing:
        return None
    return next(iter(processing.values()))


def _is_acquisition_software_field(fieldname_surlab: str, notes: str = "") -> bool:
    keys = schema_key_candidates(fieldname_surlab, notes)
    return "acquisition_software" in keys or fieldname_surlab.endswith("acquisition_software")


def _is_sorting_software_field(fieldname_surlab: str, notes: str = "") -> bool:
    keys = schema_key_candidates(fieldname_surlab, notes)
    return "sorting_software" in keys or fieldname_surlab.endswith("sorting_software")


def _read_device_field(nwbfile, nwb_fieldname: str, fieldname_surlab: str, notes: str = "") -> str:
    device = _first_device(nwbfile)
    if device is None:
        return ""
    if nwb_fieldname == "Device.name":
        return safe_join_text(getattr(device, "name", ""))
    if nwb_fieldname == "Device.description":
        raw = getattr(device, "description", "")
        parsed = lookup_key_value_text(raw, fieldname_surlab, notes)
        if parsed:
            return parsed
        # Plain software name (no key=value) only applies to acquisition_software fields.
        plain = safe_join_text(raw)
        if plain and "=" not in plain and _is_acquisition_software_field(fieldname_surlab, notes):
            return plain
        return ""
    return ""


def _read_processing_field(nwbfile, nwb_fieldname: str, fieldname_surlab: str, notes: str = "") -> str:
    if nwb_fieldname != "processing_module_description":
        return ""

    module = _first_processing_module(nwbfile)
    if module is not None:
        module_text = safe_join_text(getattr(module, "description", ""))
        parsed = lookup_key_value_text(module_text, fieldname_surlab, notes)
        if parsed:
            return parsed
        if module_text and "=" not in module_text and _is_sorting_software_field(fieldname_surlab, notes):
            return module_text

    # Fall back to Device.description key=value (common Task 2 interim storage).
    device = _first_device(nwbfile)
    if device is not None:
        return lookup_key_value_text(getattr(device, "description", ""), fieldname_surlab, notes)
    return ""


def _units_colnames(nwbfile) -> List[str]:
    if nwbfile.units is None:
        return []
    return list(getattr(nwbfile.units, "colnames", []) or [])


def _resolve_units_column(nwb_fieldname: str) -> List[str]:
    if nwb_fieldname in UNITS_COLUMN_LOOKUP:
        return UNITS_COLUMN_LOOKUP[nwb_fieldname]
    if nwb_fieldname.startswith("custom_column_"):
        token = nwb_fieldname.replace("custom_column_", "", 1)
        return [token]
    if nwb_fieldname:
        return [nwb_fieldname]
    return []


def read_nwb_unit_values_for_row(nwbfile, row: Dict[str, str]) -> List[str]:
    """Return one formatted string per unit for a metadata table row."""
    if nwbfile.units is None or len(nwbfile.units) == 0:
        return []

    nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
    nwb_type = str(row.get("nwb_type", "str")).strip()
    colnames = _units_colnames(nwbfile)
    for candidate in _resolve_units_column(nwb_fieldname):
        if candidate == "__units_id__":
            return [format_nwb_scalar(value, nwb_type) for value in nwbfile.units.id[:]]
        if candidate in colnames:
            return [format_nwb_scalar(value, nwb_type) for value in nwbfile.units[candidate][:]]
    return []


def read_nwb_keyword_flag(nwbfile, row: Dict[str, str]) -> str:
    """Return '1'/'0' for fixed modality keywords; identity streams blank when absent."""
    from src.nwb_keyword_map import keywords_from_nwb

    nwb_keyword = str(row.get("nwb_keyword", "")).strip()
    fieldname_surlab = str(row.get("fieldname_surlab", "")).strip()
    keywords = keywords_from_nwb(nwbfile)
    if not nwb_keyword:
        return ""
    if nwb_keyword == "identity":
        return "1" if fieldname_surlab in keywords else ""
    return "1" if nwb_keyword in keywords else "0"


def read_nwb_value_for_row(nwbfile, row: Dict[str, str]) -> str:
    """Return one SurLab scalar string for a metadata_field table row."""
    fieldname = str(row.get("fieldname_surlab", "")).strip()
    nwb_location = str(row.get("nwb_location", "")).strip()
    nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
    nwb_type = str(row.get("nwb_type", "str")).strip()
    notes = str(row.get("notes", "")).strip()

    if nwb_fieldname == "keywords":
        return read_nwb_keyword_flag(nwbfile, row)

    if fieldname == "zero_time" and nwb_location == "NWBFile" and nwb_fieldname == "notes":
        return parse_zero_time_from_notes(getattr(nwbfile, "notes", ""))

    if nwb_fieldname in {"N/A", "same_as_dataset_dir_mapping"}:
        return ""

    if nwb_location == "NWBFile/devices":
        return _read_device_field(nwbfile, nwb_fieldname, fieldname, notes=notes)

    if nwb_location == "NWBFile/processing":
        return _read_processing_field(nwbfile, nwb_fieldname, fieldname, notes=notes)

    if nwb_location == "NWBFile/units":
        unit_values = read_nwb_unit_values_for_row(nwbfile, row)
        if not unit_values:
            return ""
        if len(unit_values) == 1:
            return unit_values[0]
        return "|".join(unit_values)

    container, attribute = parse_nwb_target(nwb_location, nwb_fieldname)
    if container == "file":
        if attribute == "session_start_time":
            start_time = getattr(nwbfile, "session_start_time", None)
            return format_nwb_scalar(start_time, nwb_type, fieldname_surlab=fieldname)
        value = getattr(nwbfile, attribute, None)
        return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)
    if container == "subject":
        if nwbfile.subject is None:
            return ""
        value = getattr(nwbfile.subject, attribute, None)
        return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)

    logger.debug("No reverse reader for %s / %s", nwb_location, nwb_fieldname)
    return ""


def read_nwb_triangulation_value(nwbfile, row: Dict[str, str]) -> Tuple[Optional[str], str]:
    """Return (value, note) for Task 5 triangulation reads."""
    row_type = str(row.get("row_type", "")).strip()
    nwb_location = str(row.get("nwb_location", "")).strip()
    nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()

    if row_type in {"data_array", "timestamps_array"}:
        if nwb_location == "NWBFile/units" and nwb_fieldname == "spike_times":
            if nwbfile.units is None:
                return None, "units missing"
            count = len(nwbfile.units)
            return str(count), f"{count} units"
        return None, "array triangulation not scalar"

    if nwb_fieldname == "keywords":
        value = read_nwb_keyword_flag(nwbfile, row)
        nwb_keyword = str(row.get("nwb_keyword", "")).strip()
        return value, f"keyword {nwb_keyword or 'identity'}"

    if nwb_location == "NWBFile/units":
        values = read_nwb_unit_values_for_row(nwbfile, row)
        if not values:
            return "", "units column missing"
        if len(values) == 1:
            return values[0], "units single value"
        preview = "|".join(values[:5])
        if len(values) > 5:
            preview += "|..."
        return preview, f"{len(values)} unit values"

    if nwb_location == "NWBFile/devices":
        value = _read_device_field(
            nwbfile,
            nwb_fieldname,
            str(row.get("fieldname_surlab", "")),
            notes=str(row.get("notes", "")),
        )
        return value, "device"

    if nwb_location == "NWBFile/processing":
        value = _read_processing_field(
            nwbfile,
            nwb_fieldname,
            str(row.get("fieldname_surlab", "")),
            notes=str(row.get("notes", "")),
        )
        return value, "processing"

    if nwb_location == "NWBFile/general/subject":
        return read_nwb_value_for_row(nwbfile, row), "subject"

    if nwb_location == "NWBFile":
        return read_nwb_value_for_row(nwbfile, row), "nwbfile"

    return None, f"unsupported nwb_location={nwb_location}"
