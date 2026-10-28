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
STREAM_SCALAR_SUFFIX_MARKERS = ("_traces_", "_behTSeries_", "_behEvents_")

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
    "custom_column_primary_channel": ["primary_channel"],
    "custom_column_quality_metric_description": ["quality_metric", "quality_metric_description"],
    "quality_metric_description": ["quality_metric_description", "quality_metric"],
    "custom_column_num_units": ["num_units"],
}

LFP_SERIES_NAME = "lfp"
LFP_DATATYPE_ID = "lfp"
SPIKE_TIMES_DATATYPE_ID = "spikeTimes"
SPIKE_WAVES_DATATYPE_ID = "spikeWaves"
MISSING_DEVICE_MARKER = "MISSING_REQUIRED_FOR_NWB"

ELECTRODE_COLUMN_LOOKUP: Dict[str, List[str]] = {
    "id": ["__electrode_id__"],
    "location": ["location", "area"],
    "z": ["z", "depth__um"],
    "x": ["x", "channel_x_coordinate"],
    "y": ["y", "channel_y_coordinate"],
    "custom_column_channel_label": ["channel_label"],
    "custom_column_grid_location": ["grid_location"],
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
        for marker in STREAM_SCALAR_SUFFIX_MARKERS:
            if marker in field:
                candidates.append(field.split(marker, 1)[1])
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


def _device_from_electrode_group(nwbfile, group_name_prefix: str):
    electrodes = getattr(nwbfile, "electrodes", None)
    if electrodes is None:
        return None
    try:
        row_count = len(electrodes)
    except TypeError:
        return None
    if row_count == 0:
        return None
    group = electrodes["group"][0]
    if group is None:
        return None
    group_name = str(getattr(group, "name", "")).strip()
    if group_name_prefix and not group_name.startswith(group_name_prefix):
        return None
    return getattr(group, "device", None)


def _device_for_lfp_linked(nwbfile):
    """Return Device linked to LFP electrodes/ElectricalSeries only."""
    series = find_lfp_electrical_series(nwbfile)
    if series is not None:
        region = getattr(series, "electrodes", None)
        electrodes = getattr(nwbfile, "electrodes", None)
        if region is not None and electrodes is not None:
            try:
                indices = list(region.data[:])
            except (TypeError, AttributeError):
                indices = []
            if indices:
                group = electrodes["group"][int(indices[0])]
                device = getattr(group, "device", None)
                if device is not None:
                    return device
    return _device_from_electrode_group(nwbfile, "lfp")


def _device_for_lfp(nwbfile):
    device = _device_for_lfp_linked(nwbfile)
    if device is not None:
        return device
    return _device_for_ecephys_probe(nwbfile)


def _is_ophys_placeholder_device(device) -> bool:
    name = str(getattr(device, "name", ""))
    description = str(getattr(device, "description", "") or "")
    return name.endswith("_device") and MISSING_DEVICE_MARKER in description


def _device_for_ecephys_probe(nwbfile):
    """Return shared ecephys probe Device (not ophys placeholder devices)."""
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

    lfp_device = _device_for_lfp_linked(nwbfile)
    if lfp_device is not None and not _is_ophys_placeholder_device(lfp_device):
        return lfp_device

    devices = getattr(nwbfile, "devices", None) or {}
    for device in devices.values():
        description = str(getattr(device, "description", "") or "")
        if "acquisition_software=" in description or "sorting_software=" in description:
            return device

    for device in devices.values():
        if not _is_ophys_placeholder_device(device):
            return device
    logger.warning("ecephys probe resolver: no non-placeholder device found; using first device")
    return _first_device(nwbfile)


def _device_for_spike_waves(nwbfile):
    return _device_for_ecephys_probe(nwbfile)


def _device_for_traces(nwbfile, datatype_id: str):
    """Return microscope Device linked from this stream's ImagingPlane."""
    series = find_roi_response_series(nwbfile, datatype_id)
    if series is None:
        return None
    plane = _imaging_plane_from_series(series)
    if plane is None:
        return None
    return getattr(plane, "device", None)


def _device_for_datatype(nwbfile, datatype_id: str):
    if datatype_id.endswith("_traces"):
        device = _device_for_traces(nwbfile, datatype_id)
        if device is not None:
            return device
    if datatype_id == LFP_DATATYPE_ID:
        return _device_for_lfp(nwbfile)
    if datatype_id in {SPIKE_WAVES_DATATYPE_ID, SPIKE_TIMES_DATATYPE_ID}:
        return _device_for_ecephys_probe(nwbfile)
    if datatype_id.startswith("spikeTimes") or datatype_id.startswith("spikeWaves"):
        return _device_for_ecephys_probe(nwbfile)
    return _first_device(nwbfile)


def _parse_data_unit_from_description(description: object) -> str:
    parsed = parse_key_value_text(description)
    unit = parsed.get("data_unit_measurement", "") or parsed.get("unit", "")
    return unit.strip()


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


def _is_microscope_name_field(fieldname_surlab: str, notes: str = "") -> bool:
    if fieldname_surlab.endswith("_microscope_description"):
        return False
    keys = schema_key_candidates(fieldname_surlab, notes)
    return (
        fieldname_surlab.endswith("_microscope")
        or fieldname_surlab == "microscope"
        or ("microscope" in keys and "microscope_description" not in keys)
    )


def _is_microscope_description_field(fieldname_surlab: str, notes: str = "") -> bool:
    keys = schema_key_candidates(fieldname_surlab, notes)
    return (
        fieldname_surlab.endswith("_microscope_description")
        or fieldname_surlab == "microscope_description"
        or "microscope_description" in keys
    )


def datatype_id_from_row(row: Dict[str, str]) -> str:
    """Return bound datatype_id, or infer from a prefixed SurLab field name."""
    bound = str(row.get("datatype_id", "")).strip()
    if bound:
        return bound
    field = str(row.get("fieldname_surlab", "")).strip()
    for marker in STREAM_SCALAR_SUFFIX_MARKERS:
        if marker in field:
            return field.split(marker, 1)[0] + marker.rstrip("_")
    for prefix in STREAM_SCALAR_PREFIXES:
        token = prefix + "_"
        if field.startswith(token):
            return prefix
    if field.endswith("_traces") or field.endswith("_behTSeries") or field.endswith("_behEvents"):
        return field

    from src.conversion_table import condition_datatype_id

    condition = str(row.get("requirement_condition", "")).strip()
    condition_dtype = condition_datatype_id(condition)
    if condition_dtype:
        return condition_dtype

    filename = str(row.get("surlab_filename", "")).strip()
    filename_lower = filename.lower()
    for prefix in STREAM_SCALAR_PREFIXES:
        if filename_lower.startswith(f"{prefix}_") or filename_lower.startswith(f"{prefix}."):
            return prefix
    if "_behevents" in filename_lower:
        end = filename_lower.index("_behevents") + len("_behEvents")
        return filename[:end]
    return ""


def iter_named_roi_response_series(nwbfile) -> List[Tuple[str, object]]:
    """Yield (name, RoiResponseSeries-like) from processing and acquisition."""
    found: List[Tuple[str, object]] = []
    seen_ids: set[int] = set()

    def _maybe_add(name: str, obj: object) -> None:
        if obj is None:
            return
        obj_id = id(obj)
        if obj_id in seen_ids:
            return
        if not (hasattr(obj, "data") and (hasattr(obj, "timestamps") or hasattr(obj, "rate"))):
            return
        # Prefer objects that look like ROI response series (have rois) or explicit name.
        class_name = type(obj).__name__
        if "RoiResponse" not in class_name and not hasattr(obj, "rois"):
            return
        seen_ids.add(obj_id)
        found.append((str(name), obj))

    processing = getattr(nwbfile, "processing", None) or {}
    for module in processing.values():
        interfaces = getattr(module, "data_interfaces", None) or {}
        for iface_name, iface in interfaces.items():
            roi_map = getattr(iface, "roi_response_series", None)
            if isinstance(roi_map, dict):
                for series_name, series in roi_map.items():
                    _maybe_add(series_name, series)
            elif hasattr(iface, "items"):
                try:
                    for series_name, series in iface.items():
                        _maybe_add(series_name, series)
                except TypeError:
                    pass
            _maybe_add(getattr(iface, "name", iface_name), iface)

    acquisition = getattr(nwbfile, "acquisition", None) or {}
    if hasattr(acquisition, "items"):
        for acq_name, acq_obj in acquisition.items():
            roi_map = getattr(acq_obj, "roi_response_series", None)
            if isinstance(roi_map, dict):
                for series_name, series in roi_map.items():
                    _maybe_add(series_name, series)
            _maybe_add(acq_name, acq_obj)

    return found


def discover_traces_datatypes(nwbfile) -> List[str]:
    """Discover ``*_traces`` stream IDs from keywords and named RoiResponseSeries."""
    from src.nwb_keyword_map import keywords_from_nwb

    found: List[str] = []
    seen = set()
    for keyword in keywords_from_nwb(nwbfile):
        if keyword.endswith("_traces") and keyword not in seen:
            seen.add(keyword)
            found.append(keyword)
    for name, _series in iter_named_roi_response_series(nwbfile):
        if name.endswith("_traces") and name not in seen:
            seen.add(name)
            found.append(name)
        elif name and name not in seen and "RoiResponse" in type(_series).__name__:
            # Named series without suffix still counts when it is a RoiResponseSeries.
            seen.add(name)
            found.append(name)
    return found


def find_roi_response_series(nwbfile, datatype_id: str):
    if not datatype_id:
        return None
    for name, series in iter_named_roi_response_series(nwbfile):
        if name == datatype_id:
            return series
    return None


def plane_segmentation_for_datatype(nwbfile, datatype_id: str):
    series = find_roi_response_series(nwbfile, datatype_id)
    if series is None:
        return None
    return _plane_segmentation_from_series(series)


def _plane_segmentation_from_series(series) -> Optional[object]:
    rois = getattr(series, "rois", None)
    if rois is None:
        return None
    table = getattr(rois, "table", None)
    if table is not None:
        return table
    return rois


def _imaging_plane_from_series(series) -> Optional[object]:
    plane = getattr(series, "imaging_plane", None)
    if plane is not None:
        return plane
    plane_seg = _plane_segmentation_from_series(series)
    if plane_seg is None:
        return None
    return getattr(plane_seg, "imaging_plane", None)


def _optical_channel_from_series(series) -> Optional[object]:
    plane = _imaging_plane_from_series(series)
    if plane is None:
        return None
    channels = getattr(plane, "optical_channel", None)
    if channels is None:
        return None
    if isinstance(channels, (list, tuple)):
        return channels[0] if channels else None
    if hasattr(channels, "__len__") and not isinstance(channels, (str, bytes)):
        try:
            return channels[0] if len(channels) else None
        except TypeError:
            pass
    return channels


def _lab_meta_schema_container(nwbfile, datatype_id: str):
    if not datatype_id:
        return None
    lab_meta = getattr(nwbfile, "lab_meta_data", None) or {}
    target_name = f"SurLabSchema_{datatype_id}"
    if hasattr(lab_meta, "get"):
        obj = lab_meta.get(target_name)
        if obj is not None:
            return obj
    if isinstance(lab_meta, dict):
        return lab_meta.get(target_name)
    for name, obj in getattr(lab_meta, "items", lambda: [])():
        if str(name) == target_name:
            return obj
    return None


def read_lab_meta_schema_fields(nwbfile, datatype_id: str) -> Dict[str, str]:
    """Return key/value fields from SurLabSchema_<datatypeID> LabMetaData."""
    import json

    container = _lab_meta_schema_container(nwbfile, datatype_id)
    if container is None:
        return {}

    fields: Dict[str, str] = {}
    for attr_name in ("schema_json", "extras_json", "fields_json"):
        raw = getattr(container, attr_name, None)
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                fields[str(key)] = safe_join_text(value)

    fields_attr = getattr(container, "fields", None)
    if isinstance(fields_attr, dict):
        for key, value in fields_attr.items():
            fields[str(key)] = safe_join_text(value)

    # Direct attributes (skip NWB/HDMF internals).
    skip = {
        "name",
        "description",
        "fields",
        "schema_json",
        "extras_json",
        "fields_json",
        "parent",
        "object_id",
    }
    for key, value in getattr(container, "__dict__", {}).items():
        if key.startswith("_") or key in skip:
            continue
        text = safe_join_text(value)
        if text:
            fields[str(key)] = text

    desc = getattr(container, "description", "")
    fields.update(parse_key_value_text(desc))
    return fields


def _read_lab_meta_field(nwbfile, datatype_id: str, nwb_fieldname: str) -> str:
    fields = read_lab_meta_schema_fields(nwbfile, datatype_id)
    if nwb_fieldname in {"*", ""}:
        return ""
    return fields.get(nwb_fieldname, "")


def _read_roi_response_attr(nwbfile, datatype_id: str, attribute: str, nwb_type: str, fieldname: str) -> str:
    series = find_roi_response_series(nwbfile, datatype_id)
    if series is None:
        return ""
    value = getattr(series, attribute, None)
    return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)


def _read_imaging_plane_attr(nwbfile, datatype_id: str, attribute: str, nwb_type: str, fieldname: str) -> str:
    series = find_roi_response_series(nwbfile, datatype_id)
    if series is None:
        return ""
    plane = _imaging_plane_from_series(series)
    if plane is None:
        return ""
    # Table uses imaging_rate; accept legacy alias "rate" on older NWB files.
    candidates = [attribute]
    if attribute == "rate":
        candidates.append("imaging_rate")
    elif attribute == "imaging_rate":
        candidates.append("rate")
    for candidate in candidates:
        value = getattr(plane, candidate, None)
        text = format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)
        if text != "" and text.lower() != "nan":
            return text
    return ""


def _read_optical_channel_attr(nwbfile, datatype_id: str, attribute: str, nwb_type: str, fieldname: str) -> str:
    series = find_roi_response_series(nwbfile, datatype_id)
    if series is None:
        return ""
    channel = _optical_channel_from_series(series)
    if channel is None:
        return ""
    value = getattr(channel, attribute, None)
    return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)


def _resolve_roi_column(nwb_fieldname: str) -> List[str]:
    if nwb_fieldname == "id":
        return ["__roi_id__"]
    if nwb_fieldname.startswith("custom_column_"):
        token = nwb_fieldname.replace("custom_column_", "", 1)
        return [token]
    if nwb_fieldname:
        return [nwb_fieldname]
    return []


def read_nwb_roi_values_for_row(nwbfile, row: Dict[str, str]) -> List[str]:
    """Return one formatted string per ROI for a traces metadata table row."""
    datatype_id = datatype_id_from_row(row)
    series = find_roi_response_series(nwbfile, datatype_id)
    if series is None:
        return []
    plane_seg = _plane_segmentation_from_series(series)
    if plane_seg is None:
        return []

    nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
    nwb_type = str(row.get("nwb_type", "str")).strip()
    colnames = list(getattr(plane_seg, "colnames", []) or [])
    try:
        row_count = len(plane_seg)
    except TypeError:
        return []

    for candidate in _resolve_roi_column(nwb_fieldname):
        if candidate == "__roi_id__":
            ids = getattr(plane_seg, "id", None)
            if ids is None:
                return [str(index) for index in range(row_count)]
            return [format_nwb_scalar(value, nwb_type) for value in ids[:]]
        if candidate in colnames:
            return [format_nwb_scalar(value, nwb_type) for value in plane_seg[candidate][:]]
    return []


def read_roi_response_arrays(nwbfile, datatype_id: str) -> Tuple[Optional[object], Optional[object]]:
    """Return (data, timestamps) arrays for one traces stream, time x ROI orientation."""
    import numpy as np

    series = find_roi_response_series(nwbfile, datatype_id)
    if series is None:
        return None, None
    data = np.asarray(series.data[:])
    timestamps = None
    if getattr(series, "timestamps", None) is not None:
        timestamps = np.asarray(series.timestamps[:], dtype=float).ravel()
    data = ensure_time_by_roi(data, timestamps)
    return data, timestamps


def ensure_time_by_roi(data, timestamps=None):
    """Ensure axis0=time, axis1=ROI using timestamps length when available."""
    import numpy as np

    array = np.asarray(data)
    if array.ndim != 2:
        return array
    if timestamps is not None:
        n_time = len(np.asarray(timestamps).ravel())
        if array.shape[0] == n_time:
            return array
        if array.shape[1] == n_time:
            return array.T
    return array


def acquisition_datatype_from_location(nwb_location: str) -> str:
    """Extract stream id from ``NWBFile/acquisition/<datatypeID>``."""
    prefix = "NWBFile/acquisition/"
    if nwb_location.startswith(prefix) and nwb_location.count("/") == 2:
        return nwb_location[len(prefix) :]
    return ""


def find_acquisition_timeseries(nwbfile, datatype_id: str):
    if not datatype_id:
        return None
    acquisition = getattr(nwbfile, "acquisition", None) or {}
    if hasattr(acquisition, "get"):
        return acquisition.get(datatype_id)
    return None


def discover_beh_tseries_datatypes(nwbfile) -> List[str]:
    """Discover ``*_behTSeries`` stream IDs from keywords and acquisition."""
    from src.nwb_keyword_map import keywords_from_nwb

    found: List[str] = []
    seen: set[str] = set()
    for keyword in keywords_from_nwb(nwbfile):
        if keyword.endswith("_behTSeries") and keyword not in seen:
            seen.add(keyword)
            found.append(keyword)
    acquisition = getattr(nwbfile, "acquisition", None) or {}
    for name in acquisition.keys():
        text = str(name)
        if text.endswith("_behTSeries") and text not in seen:
            seen.add(text)
            found.append(text)
    return found


def find_behavior_features_table(nwbfile, datatype_id: str):
    if not datatype_id:
        return None
    processing = getattr(nwbfile, "processing", None) or {}
    behavior = processing.get("behavior") if hasattr(processing, "get") else None
    if behavior is None:
        return None
    table_name = f"{datatype_id}_features"
    interfaces = getattr(behavior, "data_interfaces", None) or {}
    if hasattr(interfaces, "get"):
        return interfaces.get(table_name)
    return None


def ensure_time_by_feature(data, timestamps=None, n_features: Optional[int] = None):
    """Ensure axis0=time, axis1=features (reverse of forward transpose)."""
    import numpy as np

    array = np.asarray(data)
    if array.ndim == 1:
        return array.reshape(-1, 1)
    if array.ndim != 2:
        return array
    if timestamps is not None:
        n_time = len(np.asarray(timestamps).ravel())
        if array.shape[0] == n_time:
            return array
        if array.shape[1] == n_time:
            return array.T
    if n_features is not None and n_features > 0:
        if array.shape[1] == n_features:
            return array
        if array.shape[0] == n_features:
            return array.T
    return array


def read_acquisition_timeseries_arrays(nwbfile, datatype_id: str) -> Tuple[Optional[object], Optional[object]]:
    """Return (data, timestamps) for one behTSeries acquisition TimeSeries."""
    import numpy as np

    series = find_acquisition_timeseries(nwbfile, datatype_id)
    if series is None:
        return None, None
    data = np.asarray(series.data[:]) if getattr(series, "data", None) is not None else None
    timestamps = None
    if getattr(series, "timestamps", None) is not None:
        timestamps = np.asarray(series.timestamps[:], dtype=float).ravel()
    n_features = None
    features_table = find_behavior_features_table(nwbfile, datatype_id)
    if features_table is not None:
        try:
            n_features = len(features_table)
        except TypeError:
            n_features = None
    if data is not None:
        data = ensure_time_by_feature(data, timestamps, n_features)
    return data, timestamps


def find_lfp_electrical_series(nwbfile):
    acquisition = getattr(nwbfile, "acquisition", None) or {}
    if hasattr(acquisition, "get"):
        return acquisition.get(LFP_SERIES_NAME)
    return None


def lfp_electrode_indices(nwbfile) -> List[int]:
    """Return electrode table row indices linked to acquisition/lfp, in region order."""
    series = find_lfp_electrical_series(nwbfile)
    if series is None:
        return []
    region = getattr(series, "electrodes", None)
    if region is None:
        return []
    try:
        return [int(value) for value in region.data[:]]
    except (TypeError, AttributeError, ValueError):
        return []


def ensure_time_by_channel(data, timestamps=None, n_channels: Optional[int] = None):
    """Ensure axis0=time, axis1=channels (reverse of forward transpose)."""
    import numpy as np

    array = np.asarray(data)
    if array.ndim == 1:
        return array.reshape(-1, 1)
    if array.ndim != 2:
        return array
    if timestamps is not None:
        n_time = len(np.asarray(timestamps).ravel())
        if array.shape[0] == n_time:
            return array
        if array.shape[1] == n_time:
            return array.T
    if n_channels is not None and n_channels > 0:
        if array.shape[1] == n_channels:
            return array
        if array.shape[0] == n_channels:
            return array.T
    return array


def read_lfp_arrays(nwbfile) -> Tuple[Optional[object], Optional[object]]:
    """Return (data, timestamps) for acquisition/lfp ElectricalSeries."""
    import numpy as np

    series = find_lfp_electrical_series(nwbfile)
    if series is None:
        return None, None
    data = np.asarray(series.data[:], dtype=float)
    timestamps = None
    if getattr(series, "timestamps", None) is not None:
        timestamps = np.asarray(series.timestamps[:], dtype=float).ravel()
    indices = lfp_electrode_indices(nwbfile)
    n_channels = len(indices) if indices else None
    data = ensure_time_by_channel(data, timestamps, n_channels)
    return data, timestamps


def units_has_waveforms(nwbfile) -> bool:
    units = getattr(nwbfile, "units", None)
    if units is None:
        return False
    try:
        unit_count = len(units)
    except TypeError:
        return False
    if unit_count == 0:
        return False
    return "waveforms" in getattr(units, "colnames", [])


def read_spike_waves_arrays(nwbfile) -> Tuple[Optional[object], Optional[object]]:
    """Return (waveforms [samples x units], optional snippet_timestamps)."""
    import numpy as np

    if not units_has_waveforms(nwbfile):
        return None, None
    waveforms = nwbfile.units["waveforms"]
    columns = []
    for unit_index in range(len(nwbfile.units)):
        snippet = np.asarray(waveforms[unit_index], dtype=float).ravel()
        columns.append(snippet)
    if not columns:
        return None, None
    sample_lengths = {snippet.shape[0] for snippet in columns}
    if len(sample_lengths) == 1:
        data = np.column_stack(columns)
    else:
        max_len = max(sample_lengths)
        matrix = np.full((max_len, len(columns)), np.nan, dtype=float)
        for index, snippet in enumerate(columns):
            matrix[: snippet.shape[0], index] = snippet
        data = matrix

    snippet_timestamps = None
    container = _lab_meta_schema_container(nwbfile, SPIKE_WAVES_DATATYPE_ID)
    if container is not None:
        raw_json = getattr(container, "schema_json", "")
        if raw_json:
            try:
                import json

                parsed = json.loads(raw_json)
                if isinstance(parsed, dict) and "snippet_timestamps" in parsed:
                    snippet_timestamps = np.asarray(parsed["snippet_timestamps"], dtype=float).ravel()
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        if snippet_timestamps is None:
            direct = getattr(container, "snippet_timestamps", None)
            if direct is not None:
                snippet_timestamps = np.asarray(direct[:], dtype=float).ravel()
    if snippet_timestamps is None:
        lab_fields = read_lab_meta_schema_fields(nwbfile, SPIKE_WAVES_DATATYPE_ID)
        raw_ts = lab_fields.get("snippet_timestamps", "")
        if raw_ts:
            try:
                import json

                parsed = json.loads(raw_ts)
                snippet_timestamps = np.asarray(parsed, dtype=float).ravel()
            except (TypeError, ValueError, json.JSONDecodeError):
                parts = [part.strip() for part in raw_ts.split(",") if part.strip()]
                if parts:
                    snippet_timestamps = np.asarray([float(part) for part in parts], dtype=float)
    return data, snippet_timestamps


def discover_beh_events_datatypes(nwbfile) -> List[str]:
    """Discover ``*_behEvents`` stream IDs from keywords, events, and acquisition."""
    from src.nwb_keyword_map import keywords_from_nwb

    found: set[str] = set()
    for keyword in keywords_from_nwb(nwbfile):
        if keyword.endswith("_behEvents"):
            found.add(keyword)

    events = getattr(nwbfile, "events", None) or {}
    for name in events.keys():
        text = str(name)
        if text.endswith("_behEvents"):
            found.add(text)

    acquisition = getattr(nwbfile, "acquisition", None) or {}
    for name in acquisition.keys():
        text = str(name)
        if text.endswith("_behEvents"):
            found.add(text)
            continue
        marker = "_behEvents_"
        if marker in text:
            found.add(text.split(marker, 1)[0] + "_behEvents")
    return sorted(found)


def find_behavior_events_table(nwbfile, datatype_id: str):
    if not datatype_id:
        return None
    processing = getattr(nwbfile, "processing", None) or {}
    behavior = processing.get("behavior") if hasattr(processing, "get") else None
    if behavior is None:
        return None
    table_name = f"{datatype_id}_events"
    interfaces = getattr(behavior, "data_interfaces", None) or {}
    if hasattr(interfaces, "get"):
        return interfaces.get(table_name)
    return None


def _annotation_series_names_for_beh_events(nwbfile, datatype_id: str) -> List[str]:
    acquisition = getattr(nwbfile, "acquisition", None) or {}
    names: List[str] = []
    if datatype_id in acquisition:
        names.append(datatype_id)
    prefix = f"{datatype_id}_"
    for name in acquisition.keys():
        text = str(name)
        if text.startswith(prefix):
            names.append(text)
    return names


def read_beh_events_object_array(nwbfile, datatype_id: str):
    """Return SurLab-style (1, n_event_types) object array of event time vectors."""
    import numpy as np

    events = getattr(nwbfile, "events", None) or {}
    if datatype_id in events:
        slots = _beh_events_slots_from_events_table(events[datatype_id])
        if slots:
            container = np.empty((1, len(slots)), dtype=object)
            for index, values in enumerate(slots):
                container[0, index] = values
            return container

    events_table = find_behavior_events_table(nwbfile, datatype_id)
    event_labels: List[str] = []
    if events_table is not None:
        colnames = list(getattr(events_table, "colnames", []) or [])
        if "event_label" in colnames:
            event_labels = [str(value).strip() for value in events_table["event_label"][:]]
        else:
            try:
                event_labels = [str(index) for index in range(len(events_table))]
            except TypeError:
                event_labels = []

    acquisition = getattr(nwbfile, "acquisition", None) or {}
    series_names = _annotation_series_names_for_beh_events(nwbfile, datatype_id)
    if not series_names:
        return None

    slots: List[np.ndarray] = []
    if len(series_names) == 1 and series_names[0] == datatype_id:
        series = acquisition[datatype_id]
        timestamps = getattr(series, "timestamps", None)
        if timestamps is None:
            return None
        slots.append(np.asarray(timestamps[:], dtype=float).ravel())
    else:
        label_to_series = {}
        for name in series_names:
            if name == datatype_id:
                label_to_series[""] = acquisition[name]
                continue
            suffix = name[len(datatype_id) + 1 :]
            label_to_series[suffix] = acquisition[name]
        ordered_labels = event_labels or sorted(label_to_series.keys())
        for label in ordered_labels:
            series = label_to_series.get(label)
            if series is None:
                series = label_to_series.get(label.replace(" ", "_"))
            if series is None:
                continue
            timestamps = getattr(series, "timestamps", None)
            if timestamps is None:
                continue
            slots.append(np.asarray(timestamps[:], dtype=float).ravel())

    if not slots:
        return None
    container = np.empty((1, len(slots)), dtype=object)
    for index, values in enumerate(slots):
        container[0, index] = values
    return container


def _beh_events_slots_from_events_table(events_table) -> List[np.ndarray]:
    """Group EventsTable rows by annotation label (SurLab event-type slots)."""
    import numpy as np

    colnames = list(getattr(events_table, "colnames", []) or [])
    if "timestamp" not in colnames:
        return []
    timestamps = np.asarray(events_table["timestamp"][:], dtype=float)
    if "annotation" not in colnames:
        return [timestamps.ravel()] if timestamps.size else []

    labels = [str(value).strip() for value in events_table["annotation"][:]]
    order: List[str] = []
    grouped: Dict[str, List[float]] = {}
    for timestamp, label in zip(timestamps, labels):
        key = label or "event0"
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(float(timestamp))
    return [np.asarray(grouped[label], dtype=float) for label in order]


def _resolve_electrode_column(nwb_fieldname: str) -> List[str]:
    if nwb_fieldname in ELECTRODE_COLUMN_LOOKUP:
        return ELECTRODE_COLUMN_LOOKUP[nwb_fieldname]
    if nwb_fieldname.startswith("custom_column_"):
        return [nwb_fieldname.replace("custom_column_", "", 1)]
    if nwb_fieldname:
        return [nwb_fieldname]
    return []


def read_nwb_electrode_values_for_row(nwbfile, row: Dict[str, str]) -> List[str]:
    """Return one formatted string per LFP-linked electrode for a metadata row."""
    electrodes = getattr(nwbfile, "electrodes", None)
    if electrodes is None:
        return []
    indices = lfp_electrode_indices(nwbfile)
    if not indices:
        try:
            indices = list(range(len(electrodes)))
        except TypeError:
            return []

    nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
    nwb_type = str(row.get("nwb_type", "str")).strip()
    colnames = list(getattr(electrodes, "colnames", []) or [])
    values: List[str] = []
    for candidate in _resolve_electrode_column(nwb_fieldname):
        if candidate == "__electrode_id__":
            return [
                format_nwb_scalar(electrodes.id[row_index], nwb_type)
                for row_index in indices
            ]
        if candidate not in colnames:
            continue
        for row_index in indices:
            raw = electrodes[candidate][row_index]
            if isinstance(raw, float) and raw != raw:
                values.append("")
            else:
                values.append(format_nwb_scalar(raw, nwb_type))
        return values
    return values


def _resolve_event_column(nwb_fieldname: str) -> List[str]:
    if nwb_fieldname in {"event_ID", "event_label"}:
        return [nwb_fieldname]
    if nwb_fieldname.startswith("custom_column_"):
        return [nwb_fieldname[len("custom_column_") :]]
    if nwb_fieldname:
        return [nwb_fieldname]
    return []


def read_nwb_event_values_for_row(nwbfile, row: Dict[str, str]) -> List[str]:
    """Return one formatted string per event-type row for behEvents metadata."""
    datatype_id = datatype_id_from_row(row)
    table = find_behavior_events_table(nwbfile, datatype_id)
    if table is None:
        return []

    nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
    nwb_type = str(row.get("nwb_type", "str")).strip()
    colnames = list(getattr(table, "colnames", []) or [])
    for candidate in _resolve_event_column(nwb_fieldname):
        if candidate in colnames:
            return [format_nwb_scalar(value, nwb_type) for value in table[candidate][:]]
    return []


def _read_lfp_acquisition_attr(
    nwbfile,
    attribute: str,
    nwb_type: str,
    fieldname: str,
) -> str:
    series = find_lfp_electrical_series(nwbfile)
    if series is None:
        return ""
    if attribute == "unit":
        text = format_nwb_scalar(getattr(series, "unit", None), nwb_type, fieldname_surlab=fieldname)
        parsed = _parse_data_unit_from_description(getattr(series, "description", ""))
        if parsed:
            return parsed
        return text
    value = getattr(series, attribute, None)
    return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)


def _read_annotation_series_attr(
    nwbfile,
    datatype_id: str,
    attribute: str,
    nwb_type: str,
    fieldname: str,
) -> str:
    import numpy as np

    series = find_acquisition_timeseries(nwbfile, datatype_id)
    if series is None:
        names = _annotation_series_names_for_beh_events(nwbfile, datatype_id)
        acquisition = getattr(nwbfile, "acquisition", None) or {}
        if names and hasattr(acquisition, "get"):
            series = acquisition.get(names[0])
    if series is None:
        return ""
    if attribute == "description":
        parsed = _parse_data_unit_from_description(getattr(series, "description", ""))
        if parsed:
            return parsed
        return safe_join_text(getattr(series, "description", ""))
    if attribute == "timestamps":
        timestamps = getattr(series, "timestamps", None)
        if timestamps is None:
            return ""
        return str(len(np.asarray(timestamps[:]).ravel()))
    value = getattr(series, attribute, None)
    return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)


def _read_events_table_attr(
    nwbfile,
    datatype_id: str,
    attribute: str,
    nwb_type: str,
    fieldname: str,
) -> str:
    events = getattr(nwbfile, "events", None) or {}
    events_table = events.get(datatype_id) if hasattr(events, "get") else None
    if events_table is None:
        return _read_annotation_series_attr(nwbfile, datatype_id, attribute, nwb_type, fieldname)
    if attribute == "description":
        parsed = _parse_data_unit_from_description(getattr(events_table, "description", ""))
        if parsed:
            return parsed
        return safe_join_text(getattr(events_table, "description", ""))
    if attribute == "timestamps":
        if "timestamp" not in getattr(events_table, "colnames", []):
            return ""
        return str(len(events_table["timestamp"][:]))
    value = getattr(events_table, attribute, None)
    return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)


def _read_acquisition_timeseries_attr(
    nwbfile,
    datatype_id: str,
    attribute: str,
    nwb_type: str,
    fieldname: str,
) -> str:
    series = find_acquisition_timeseries(nwbfile, datatype_id)
    if series is None:
        return ""
    if attribute in {"rate", "sample_frequency__Hz"}:
        value = getattr(series, "rate", None)
        text = format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)
        if text and text.lower() not in {"nan", ""}:
            return text
        lab_fields = read_lab_meta_schema_fields(nwbfile, datatype_id)
        return lab_fields.get("sample_frequency__Hz", "")
    value = getattr(series, attribute, None)
    return format_nwb_scalar(value, nwb_type, fieldname_surlab=fieldname)


def _resolve_feature_column(nwb_fieldname: str) -> List[str]:
    if nwb_fieldname in {"feature_ID", "feature_label"}:
        return [nwb_fieldname]
    if nwb_fieldname.startswith("custom_column_"):
        return [nwb_fieldname[len("custom_column_") :]]
    if nwb_fieldname:
        return [nwb_fieldname]
    return []


def read_nwb_feature_values_for_row(nwbfile, row: Dict[str, str]) -> List[str]:
    """Return one formatted string per feature row for behTSeries metadata."""
    datatype_id = datatype_id_from_row(row)
    table = find_behavior_features_table(nwbfile, datatype_id)
    if table is None:
        return []

    nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
    nwb_type = str(row.get("nwb_type", "str")).strip()
    colnames = list(getattr(table, "colnames", []) or [])
    try:
        row_count = len(table)
    except TypeError:
        return []

    for candidate in _resolve_feature_column(nwb_fieldname):
        if candidate in colnames:
            return [format_nwb_scalar(value, nwb_type) for value in table[candidate][:]]
    return []


def _read_device_field(
    nwbfile,
    nwb_fieldname: str,
    fieldname_surlab: str,
    notes: str = "",
    datatype_id: str = "",
) -> str:
    is_microscope_name = _is_microscope_name_field(fieldname_surlab, notes)
    is_microscope_desc = _is_microscope_description_field(fieldname_surlab, notes)
    is_microscope_field = is_microscope_name or is_microscope_desc

    device = None
    if is_microscope_field and datatype_id.endswith("_traces"):
        device = _device_for_traces(nwbfile, datatype_id)
    elif datatype_id:
        device = _device_for_datatype(nwbfile, datatype_id)
    else:
        device = _device_for_ecephys_probe(nwbfile)

    if device is None and not is_microscope_field:
        device = _first_device(nwbfile)
    if device is None:
        return ""

    if is_microscope_field and _is_ophys_placeholder_device(device):
        return ""

    if nwb_fieldname == "Device.name":
        return safe_join_text(getattr(device, "name", ""))
    if nwb_fieldname == "Device.description":
        raw = getattr(device, "description", "")
        if is_microscope_desc:
            plain = safe_join_text(raw)
            if not plain or plain == MISSING_DEVICE_MARKER or MISSING_DEVICE_MARKER in plain:
                return ""
            if "=" not in plain:
                return plain
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

    if _is_sorting_software_field(fieldname_surlab, notes):
        device = _device_for_ecephys_probe(nwbfile)
        if device is not None:
            parsed = lookup_key_value_text(getattr(device, "description", ""), fieldname_surlab, notes)
            if parsed:
                return parsed

    module = _first_processing_module(nwbfile)
    if module is not None:
        module_text = safe_join_text(getattr(module, "description", ""))
        parsed = lookup_key_value_text(module_text, fieldname_surlab, notes)
        if parsed:
            return parsed
        if module_text and "=" not in module_text and _is_sorting_software_field(fieldname_surlab, notes):
            return module_text

    device = _device_for_ecephys_probe(nwbfile) or _first_device(nwbfile)
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
    datatype_id = datatype_id_from_row(row)

    if nwb_fieldname in {"validate_only", "N/A", "same_as_dataset_dir_mapping"}:
        return ""

    if nwb_fieldname == "keywords":
        return read_nwb_keyword_flag(nwbfile, row)

    if fieldname == "zero_time" and nwb_location == "NWBFile" and nwb_fieldname == "notes":
        return parse_zero_time_from_notes(getattr(nwbfile, "notes", ""))

    if nwb_location == "NWBFile/devices":
        return _read_device_field(
            nwbfile, nwb_fieldname, fieldname, notes=notes, datatype_id=datatype_id
        )

    if nwb_location == "NWBFile/processing":
        return _read_processing_field(nwbfile, nwb_fieldname, fieldname, notes=notes)

    if nwb_location == "NWBFile/units":
        if nwb_fieldname == "waveform_rate":
            units = getattr(nwbfile, "units", None)
            if units is not None:
                rate = getattr(units, "waveform_rate", None)
                if rate is not None:
                    return format_nwb_scalar(rate, nwb_type, fieldname_surlab=fieldname)
        if (
            nwb_fieldname == "custom_column_sampling_rate__Hz"
            and (datatype_id == SPIKE_WAVES_DATATYPE_ID or fieldname.startswith("spikeWaves_"))
        ):
            units = getattr(nwbfile, "units", None)
            if units is not None:
                rate = getattr(units, "waveform_rate", None)
                if rate is not None:
                    return format_nwb_scalar(rate, nwb_type, fieldname_surlab=fieldname)
        if (
            nwb_fieldname == "custom_column_sampling_rate__Hz"
            and (datatype_id == SPIKE_TIMES_DATATYPE_ID or fieldname.startswith("spikeTimes_"))
        ):
            schema_rate = _read_lab_meta_field(nwbfile, SPIKE_TIMES_DATATYPE_ID, "sample_frequency__Hz")
            if schema_rate:
                return schema_rate
        if nwb_fieldname in {"custom_column_quality_metric_description", "quality_metric_description"}:
            unit_values = read_nwb_unit_values_for_row(nwbfile, row)
            if unit_values:
                unique = sorted({str(value).strip() for value in unit_values if str(value).strip()})
                if len(unique) == 1:
                    return unique[0]
        if (
            nwb_fieldname in {"custom_column_data_unit_measurement"}
            and (datatype_id == SPIKE_TIMES_DATATYPE_ID or fieldname.startswith("spikeTimes_"))
        ):
            schema_value = _read_lab_meta_field(nwbfile, SPIKE_TIMES_DATATYPE_ID, "data_unit_measurement")
            if schema_value:
                return schema_value
            return "time__s"
        if (
            nwb_fieldname in {"custom_column_data_unit_measurement"}
            and (datatype_id == SPIKE_WAVES_DATATYPE_ID or fieldname.startswith("spikeWaves_"))
        ):
            unit_values = read_nwb_unit_values_for_row(nwbfile, row)
            if unit_values:
                unique = sorted({str(value).strip() for value in unit_values if str(value).strip()})
                if len(unique) == 1:
                    return unique[0]
            schema_value = _read_lab_meta_field(
                nwbfile, SPIKE_WAVES_DATATYPE_ID, "data_unit_measurement"
            )
            if schema_value:
                return schema_value
            return ""
        unit_values = read_nwb_unit_values_for_row(nwbfile, row)
        if not unit_values:
            return ""
        if nwb_fieldname in {
            "custom_column_sampling_rate__Hz",
            "custom_column_data_unit_measurement",
        }:
            unique = sorted({str(value).strip() for value in unit_values if str(value).strip()})
            if len(unique) == 1:
                return unique[0]
        if len(unit_values) == 1:
            return unit_values[0]
        return "|".join(unit_values)

    if nwb_location == "NWBFile/general/extracellular_ephys/electrodes":
        electrode_values = read_nwb_electrode_values_for_row(nwbfile, row)
        if not electrode_values:
            return ""
        if len(electrode_values) == 1:
            return electrode_values[0]
        return "|".join(electrode_values)

    if nwb_location == "NWBFile/ophys/RoiResponseSeries":
        return _read_roi_response_attr(nwbfile, datatype_id, nwb_fieldname, nwb_type, fieldname)

    if nwb_location == "NWBFile/ophys/ImagingPlane":
        return _read_imaging_plane_attr(nwbfile, datatype_id, nwb_fieldname, nwb_type, fieldname)

    if nwb_location == "NWBFile/ophys/OpticalChannel":
        return _read_optical_channel_attr(nwbfile, datatype_id, nwb_fieldname, nwb_type, fieldname)

    if nwb_location in {"NWBFile/ophys/PlaneSegmentation", "NWBFile/ophys/ROI"}:
        roi_values = read_nwb_roi_values_for_row(nwbfile, row)
        if not roi_values:
            return ""
        if len(roi_values) == 1:
            return roi_values[0]
        return "|".join(roi_values)

    if nwb_location.startswith("NWBFile/acquisition/") and "/ophys" not in nwb_location:
        acq_dtype = acquisition_datatype_from_location(nwb_location) or datatype_id
        if acq_dtype == LFP_DATATYPE_ID or nwb_location == "NWBFile/acquisition/lfp":
            return _read_lfp_acquisition_attr(nwbfile, nwb_fieldname, nwb_type, fieldname)
        if acq_dtype.endswith("_behEvents"):
            return _read_events_table_attr(
                nwbfile, acq_dtype, nwb_fieldname, nwb_type, fieldname
            )
        if acq_dtype:
            return _read_acquisition_timeseries_attr(
                nwbfile, acq_dtype, nwb_fieldname, nwb_type, fieldname
            )

    if "processing/behavior" in nwb_location:
        if "_events" in nwb_location:
            event_values = read_nwb_event_values_for_row(nwbfile, row)
            if not event_values:
                return ""
            if len(event_values) == 1:
                return event_values[0]
            return "|".join(event_values)
        feature_values = read_nwb_feature_values_for_row(nwbfile, row)
        if not feature_values:
            return ""
        if len(feature_values) == 1:
            return feature_values[0]
        return "|".join(feature_values)

    if "lab_meta_data/SurLabSchema" in nwb_location or nwb_location.startswith("NWBFile/lab_meta_data"):
        value = _read_lab_meta_field(nwbfile, datatype_id, nwb_fieldname)
        if str(value).strip():
            return value
        if (
            datatype_id == SPIKE_TIMES_DATATYPE_ID
            and nwb_fieldname == "data_unit_measurement"
        ):
            return "time__s"
        return ""

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
    datatype_id = datatype_id_from_row(row)

    if nwb_fieldname == "validate_only":
        return None, "validate_only (impute from arrays)"

    if row_type in {"data_array", "timestamps_array"}:
        if nwb_location == "NWBFile/units" and nwb_fieldname == "spike_times":
            if nwbfile.units is None:
                return None, "units missing"
            count = len(nwbfile.units)
            return str(count), f"{count} units"
        if nwb_location == "NWBFile/units" and nwb_fieldname == "waveforms":
            data, _snippet_ts = read_spike_waves_arrays(nwbfile)
            if data is None:
                return None, "units waveforms missing"
            return f"shape={tuple(data.shape)}", "units.waveforms"
        if nwb_location == "NWBFile/acquisition/lfp":
            data, timestamps = read_lfp_arrays(nwbfile)
            if data is None:
                return None, "LFP ElectricalSeries missing"
            if row_type == "timestamps_array":
                if timestamps is None:
                    return None, "timestamps missing"
                return str(len(timestamps)), f"{len(timestamps)} timestamps"
            return f"shape={tuple(data.shape)}", "ElectricalSeries.data"
        if nwb_location == "NWBFile/ophys/RoiResponseSeries":
            data, timestamps = read_roi_response_arrays(nwbfile, datatype_id)
            if data is None:
                return None, "RoiResponseSeries missing"
            if row_type == "timestamps_array":
                if timestamps is None:
                    return None, "timestamps missing"
                return str(len(timestamps)), f"{len(timestamps)} timestamps"
            return f"shape={tuple(data.shape)}", "RoiResponseSeries.data"
        if nwb_location.startswith("NWBFile/events/"):
            events_dtype = nwb_location.split("/", 2)[-1]
            if events_dtype.endswith("_behEvents") and nwb_fieldname == "timestamps":
                event_data = read_beh_events_object_array(nwbfile, events_dtype)
                if event_data is None:
                    return None, "EventsTable missing"
                return f"shape={tuple(event_data.shape)}", "behEvents object array"
        if nwb_location.startswith("NWBFile/acquisition/") and "/ophys" not in nwb_location:
            acq_dtype = acquisition_datatype_from_location(nwb_location) or datatype_id
            if acq_dtype.endswith("_behEvents") and nwb_fieldname == "timestamps":
                event_data = read_beh_events_object_array(nwbfile, acq_dtype)
                if event_data is None:
                    return None, "EventsTable missing"
                return f"shape={tuple(event_data.shape)}", "behEvents object array"
            data, timestamps = read_acquisition_timeseries_arrays(nwbfile, acq_dtype)
            if data is None:
                return None, "acquisition TimeSeries missing"
            if row_type == "timestamps_array":
                if timestamps is None:
                    return None, "timestamps missing"
                return str(len(timestamps)), f"{len(timestamps)} timestamps"
            return f"shape={tuple(data.shape)}", "acquisition TimeSeries.data"
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

    if nwb_location in {"NWBFile/ophys/PlaneSegmentation", "NWBFile/ophys/ROI"}:
        values = read_nwb_roi_values_for_row(nwbfile, row)
        if not values:
            return "", "ROI column missing"
        preview = "|".join(values[:5])
        if len(values) > 5:
            preview += "|..."
        return preview, f"{len(values)} ROI values"

    if nwb_location == "NWBFile/general/extracellular_ephys/electrodes":
        values = read_nwb_electrode_values_for_row(nwbfile, row)
        if not values:
            return "", "electrode column missing"
        preview = "|".join(values[:5])
        if len(values) > 5:
            preview += "|..."
        return preview, f"{len(values)} electrode values"

    if nwb_location in {
        "NWBFile/ophys/RoiResponseSeries",
        "NWBFile/ophys/ImagingPlane",
        "NWBFile/ophys/OpticalChannel",
    } or nwb_location.startswith("NWBFile/acquisition/") or "lab_meta_data" in nwb_location:
        return read_nwb_value_for_row(nwbfile, row), nwb_location

    if "processing/behavior" in nwb_location:
        if "_events" in nwb_location:
            values = read_nwb_event_values_for_row(nwbfile, row)
            if not values:
                return "", "event column missing"
            preview = "|".join(values[:5])
            if len(values) > 5:
                preview += "|..."
            return preview, f"{len(values)} event values"
        values = read_nwb_feature_values_for_row(nwbfile, row)
        if not values:
            return "", "feature column missing"
        preview = "|".join(values[:5])
        if len(values) > 5:
            preview += "|..."
        return preview, f"{len(values)} feature values"

    if nwb_location == "NWBFile/devices":
        value = _read_device_field(
            nwbfile,
            nwb_fieldname,
            str(row.get("fieldname_surlab", "")),
            notes=str(row.get("notes", "")),
            datatype_id=datatype_id,
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
