"""Write SurLab spikeTimes modality into an NWB Units table.

See for_cursor/task2_implementation_decisions_and_answers.txt (section E) for
clock-reference (zero_time) warning policy and file-first discovery conventions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from src.data_io import load_json, load_spike_times_by_unit, normalize_metadata_row, normalize_schema_keys
from src.session_record import read_csv_rows
from src.surlab_paths import ResolvedSurLabFile, resolve_session_file
from src.table_placement import PlacementContext, record_table_gap

logger = logging.getLogger(__name__)

SPIKE_METADATA_COLUMN_MAP = {
    "unit_ID": "id",
    "depth__um": "depth",
    "area": "brain_area",
    "spike_sorting_ID": "sorting_id",
    "quality": "quality",
    "grid_location": "grid_location",
}


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
        datatype_id="spikeTimes",
    )
    if data_file is None:
        return

    spike_series = load_spike_times_by_unit(data_file.path)
    metadata_rows = _load_metadata_rows(session_dir, dataset_dir, context.session_record)
    schema = _load_schema(session_dir, dataset_dir, context.session_record)

    device = _ensure_device(nwbfile, schema)
    _ensure_custom_unit_columns(nwbfile, metadata_rows)

    for unit_index, spike_times in enumerate(spike_series):
        unit_kwargs = {"spike_times": spike_times}
        if unit_index < len(metadata_rows):
            unit_kwargs.update(_metadata_to_unit_kwargs(metadata_rows[unit_index]))
        nwbfile.add_unit(**unit_kwargs)

    if device is not None:
        logger.info("Registered device %s (Units linkage deferred)", device.name)

    logger.info("Added %d units from %s", len(spike_series), data_file.path.name)


def _load_metadata_rows(session_dir: Path, dataset_dir: Path, session_record: Dict[str, str]) -> List[Dict[str, str]]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeTimes_metadata.csv",
        session_record,
        datatype_id="spikeTimes",
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
        datatype_id="spikeTimes",
    )
    if resolved is None:
        return {}
    return normalize_schema_keys(load_json(resolved.path))


def _ensure_device(nwbfile, schema: Dict[str, object]):
    probe_name = str(schema.get("probe", "")).strip()
    if not probe_name:
        return None
    description_parts = []
    for key in ("acquisition_software", "sorting_software"):
        value = str(schema.get(key, "")).strip()
        if value:
            description_parts.append(f"{key}={value}")
    description = "; ".join(description_parts) if description_parts else None
    return nwbfile.create_device(name=probe_name, description=description)


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


def warn_zero_time_reference(
    context: PlacementContext,
    session_dir: Path,
    dataset_dir: Path,
    tolerance: float = 0.001,
) -> None:
    stream_id = str(context.session_record.get("zero_time", "")).strip()
    if not stream_id:
        return

    if stream_id == "spikeTimes":
        data_file = resolve_session_file(
            session_dir,
            dataset_dir,
            "spikeTimes_data.{mat|npz}",
            context.session_record,
            datatype_id="spikeTimes",
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
