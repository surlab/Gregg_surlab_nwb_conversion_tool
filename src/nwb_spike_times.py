"""Write SurLab spikeTimes modality into an NWB Units table.

See for_cursor/task2_implementation_decisions_and_answers.txt (section E) for
clock-reference (zero_time) warning policy and file-first discovery conventions.
See for_cursor/task2_forward_gaps_decisions_kitchen_sink.txt for SurLabSchema,
probe Device, and quality_metric_description policy.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

from src.data_io import load_json, load_spike_times_by_unit, normalize_metadata_row, normalize_schema_keys
from src.nwb_surlab_schema import SurLabSchemaMeta
from src.session_record import field_non_empty, read_csv_rows
from src.surlab_paths import resolve_session_file
from src.table_placement import PlacementContext

logger = logging.getLogger(__name__)

SPIKE_TIMES_ID = "spikeTimes"
LABMETA_CONTAINER = "SurLabSchema_spikeTimes"

SPIKE_METADATA_COLUMN_MAP = {
    "unit_ID": "id",
    "depth__um": "depth",
    "area": "brain_area",
    "spike_sorting_ID": "sorting_id",
    "quality": "quality",
    "grid_location": "grid_location",
}

DEVICE_SCALAR_FIELDS = {
    "probe",
    "acquisition_software",
    "sorting_software",
}

LABMETA_SCALAR_FIELDS = {
    "filter_type",
    "filter_cutoff_low__Hz",
    "filter_cutoff_high__Hz",
    "sample_frequency__Hz",
    "data_unit_measurement",
}

SESSION_SCALAR_KEYS = {
    "probe": "spikeTimes_probe",
    "acquisition_software": "spikeTimes_acquisition_software",
    "sorting_software": "spikeTimes_sorting_software",
    "filter_type": "spikeTimes_filter_type",
    "filter_cutoff_low__Hz": "spikeTimes_filter_cutoff_low__Hz",
    "filter_cutoff_high__Hz": "spikeTimes_filter_cutoff_high__Hz",
    "sample_frequency__Hz": "spikeTimes_sample_frequency__Hz",
    "data_unit_measurement": "spikeTimes_data_unit_measurement",
    "quality_metric": "spikeTimes_quality_metric",
}

LAYOUT_FIELDS = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}


def apply_spike_times(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
) -> None:
    data_file = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeTimes_data.{mat|npz}",
        context.session_record,
        datatype_id=SPIKE_TIMES_ID,
    )
    if data_file is None:
        return

    spike_series = load_spike_times_by_unit(data_file.path)
    metadata_rows = _load_metadata_rows(session_dir, dataset_dir, context.session_record)
    schema = _load_schema(session_dir, dataset_dir, context.session_record)
    scalars = _resolve_spike_times_scalars(context, schema)

    device = _ensure_device(nwbfile, scalars)
    _ensure_custom_unit_columns(nwbfile, metadata_rows)
    if device is not None:
        _ensure_units_device_column(nwbfile)

    for unit_index, spike_times in enumerate(spike_series):
        unit_kwargs = {"spike_times": spike_times}
        if unit_index < len(metadata_rows):
            unit_kwargs.update(_metadata_to_unit_kwargs(metadata_rows[unit_index]))
        if device is not None:
            unit_kwargs["device"] = device
        nwbfile.add_unit(**unit_kwargs)

    _add_quality_metric_description_column(nwbfile, scalars)
    _add_surlab_schema_labmetadata(nwbfile, scalars, schema)

    if device is not None:
        logger.info("Registered device %s and linked Units.device column", device.name)

    logger.info("Added %d units from %s", len(spike_series), data_file.path.name)


def _load_metadata_rows(session_dir: Path, dataset_dir: Path, session_record: Dict[str, str]) -> List[Dict[str, str]]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeTimes_metadata.csv",
        session_record,
        datatype_id=SPIKE_TIMES_ID,
    )
    if resolved is None:
        return []
    return [normalize_metadata_row(row) for row in read_csv_rows(resolved.path)]


def _load_schema(session_dir: Path, dataset_dir: Path, session_record: Dict[str, str]) -> Dict[str, object]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeTimes_schema.json",
        session_record,
        datatype_id=SPIKE_TIMES_ID,
    )
    if resolved is None:
        return {}
    return normalize_schema_keys(load_json(resolved.path))


def _resolve_spike_times_scalars(context: PlacementContext, schema: Dict[str, object]) -> Dict[str, object]:
    """sessionInfo-first for spikeTimes_* columns; fail if schema mirror disagrees."""
    resolved: Dict[str, object] = {}
    for field_name, session_key in SESSION_SCALAR_KEYS.items():
        session_value = context.session_record.get(session_key, "")
        schema_value = schema.get(field_name, "")

        session_present = field_non_empty(session_value)
        schema_present = field_non_empty(schema_value)

        if session_present and schema_present:
            left = str(session_value).strip()
            right = str(schema_value).strip()
            if left != right and not _numeric_equal(left, right):
                raise ValueError(
                    f"spikeTimes: sessionInfo {session_key}={left!r} disagrees with "
                    f"schema {field_name}={right!r}"
                )
            resolved[field_name] = _maybe_number(session_value)
        elif session_present:
            resolved[field_name] = _maybe_number(session_value)
        elif schema_present:
            resolved[field_name] = _maybe_number(schema_value)
    return resolved


def _build_device_description(scalars: Dict[str, object]) -> Optional[str]:
    parts: List[str] = []
    for key in ("acquisition_software", "sorting_software"):
        value = scalars.get(key)
        if field_non_empty(value):
            parts.append(f"{key}={value}")
    return "; ".join(parts) if parts else None


def _ensure_device(nwbfile, scalars: Dict[str, object]):
    probe_name = str(scalars.get("probe") or "").strip()
    if not probe_name:
        return None

    description = _build_device_description(scalars)
    if probe_name in nwbfile.devices:
        device = nwbfile.devices[probe_name]
        if description:
            existing = str(getattr(device, "description", "") or "").strip()
            if existing and existing != description:
                logger.warning(
                    "Probe Device %s already has description %r; not overwriting with %r",
                    probe_name,
                    existing,
                    description,
                )
        return device

    return nwbfile.create_device(name=probe_name, description=description)


def _ensure_units_device_column(nwbfile) -> None:
    existing = set(nwbfile.units.colnames) if nwbfile.units is not None else set()
    if "device" not in existing:
        nwbfile.add_unit_column(name="device", description="Probe Device for sorted units")


def _add_quality_metric_description_column(nwbfile, scalars: Dict[str, object]) -> None:
    description_text = str(scalars.get("quality_metric") or "").strip()
    if not description_text:
        return
    if nwbfile.units is None or len(nwbfile.units) == 0:
        return
    existing = set(nwbfile.units.colnames)
    if "quality_metric_description" in existing:
        return
    n_units = len(nwbfile.units)
    nwbfile.add_unit_column(
        name="quality_metric_description",
        description="Documents meaning of the quality column",
        data=[description_text] * n_units,
    )


def _add_surlab_schema_labmetadata(
    nwbfile,
    scalars: Dict[str, object],
    schema: Dict[str, object],
) -> None:
    payload: Dict[str, object] = {}

    for field_name in LABMETA_SCALAR_FIELDS:
        if field_name in scalars and field_non_empty(scalars[field_name]):
            payload[field_name] = scalars[field_name]

    reserved = (
        set(DEVICE_SCALAR_FIELDS)
        .union(LABMETA_SCALAR_FIELDS)
        .union(LAYOUT_FIELDS)
        .union({"quality_metric"})
    )
    for key, value in schema.items():
        if key in reserved or key in payload:
            continue
        if field_non_empty(value):
            payload[key] = value

    if not payload:
        return

    schema_json = json.dumps(payload, sort_keys=True, default=str)
    if LABMETA_CONTAINER in getattr(nwbfile, "lab_meta_data", {}):
        nwbfile.lab_meta_data[LABMETA_CONTAINER].schema_json = schema_json
        return

    nwbfile.add_lab_meta_data(SurLabSchemaMeta(name=LABMETA_CONTAINER, schema_json=schema_json))


def _ensure_custom_unit_columns(nwbfile, metadata_rows: List[Dict[str, str]]) -> None:
    """Register only Units columns that appear in metadata (PyNWB requires a value per row)."""
    column_descriptions = {
        "depth": "Unit depth in micrometers",
        "brain_area": "Brain area label",
        "sorting_id": "Spike sorting cluster id",
        "quality": "Unit quality metric",
        "grid_location": "Grid probe location",
    }
    needed_targets: set[str] = set()
    for metadata_row in metadata_rows:
        for source_name, target_name in SPIKE_METADATA_COLUMN_MAP.items():
            if target_name == "id":
                continue
            if str(metadata_row.get(source_name, "")).strip():
                needed_targets.add(target_name)

    existing = set(nwbfile.units.colnames) if nwbfile.units is not None else set()
    for column_name in sorted(needed_targets):
        if column_name not in existing:
            nwbfile.add_unit_column(name=column_name, description=column_descriptions[column_name])


def _metadata_to_unit_kwargs(metadata_row: Dict[str, str]) -> Dict[str, object]:
    kwargs: Dict[str, object] = {}
    for source_name, target_name in SPIKE_METADATA_COLUMN_MAP.items():
        value = metadata_row.get(source_name, "")
        if str(value).strip() == "":
            continue
        if target_name == "id":
            kwargs[target_name] = _coerce_unit_id(value)
        elif target_name == "depth":
            kwargs[target_name] = float(value)
        elif target_name == "quality":
            kwargs[target_name] = float(value)
        else:
            kwargs[target_name] = str(value).strip()
    return kwargs


def _coerce_unit_id(value: object):
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        return text


def _maybe_number(value: object):
    text = str(value).strip()
    try:
        number = float(text)
        if number.is_integer() and "." not in text and "e" not in text.lower():
            return int(number)
        return number
    except ValueError:
        return text


def _numeric_equal(left: str, right: str) -> bool:
    try:
        return float(left) == float(right)
    except ValueError:
        return False


def warn_zero_time_reference(
    context: PlacementContext,
    session_dir: Path,
    dataset_dir: Path,
    tolerance: float = 0.001,
) -> None:
    stream_id = str(context.session_record.get("zero_time", "")).strip()
    if not stream_id:
        return

    if stream_id == SPIKE_TIMES_ID:
        data_file = resolve_session_file(
            session_dir,
            dataset_dir,
            "spikeTimes_data.{mat|npz}",
            context.session_record,
            datatype_id=SPIKE_TIMES_ID,
        )
        if data_file is None:
            return
        series = load_spike_times_by_unit(data_file.path)
        if not series:
            return
        first_times = [float(values[0]) for values in series if len(values) > 0]
        if not first_times:
            return
        reference_time = min(first_times)
    else:
        timestamps_file = resolve_session_file(
            session_dir,
            dataset_dir,
            f"{stream_id}_timestamps.{{mat|npz}}",
            context.session_record,
            datatype_id=stream_id,
        )
        if timestamps_file is None:
            return
        from src.data_io import load_numeric_array

        timestamps = load_numeric_array(timestamps_file.path).ravel()
        if len(timestamps) == 0:
            return
        reference_time = float(timestamps[0])

    if abs(reference_time) > tolerance:
        from src.table_placement import record_warning

        record_warning(
            context,
            f"zero_time reference stream '{stream_id}' first timestamp is {reference_time}; expected ~0.",
        )
