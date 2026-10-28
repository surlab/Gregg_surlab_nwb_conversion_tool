"""Write SurLab ``*_behEvents`` streams into stock NWB containers.

Placement (conversion table stage 8):
- ``events/<datatypeID>`` EventsTable (timestamp + annotation per event)
- ``processing/behavior/<datatypeID>_events`` DynamicTable (event_ID, event_label, extras)
- Metadata row i ↔ object-array slot i; EventsTable rows carry annotation = event_label
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import numpy as np

from src.data_io import load_json, load_numeric_array, normalize_schema_keys, squeeze_object_array
from src.nwb_surlab_schema import SurLabSchemaMeta
from src.session_record import field_non_empty, read_csv_rows
from src.surlab_paths import resolve_session_file
from src.table_placement import PlacementContext, record_table_gap, record_warning

logger = logging.getLogger(__name__)

MISSING_MARKER = "MISSING_REQUIRED_FOR_NWB"

LAYOUT_FIELDS = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}

EVENT_COLUMNS = ("event_ID", "event_label")


def apply_beh_events(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    discovered_datatypes: set[str],
) -> None:
    """Add all discovered ``*_behEvents`` streams to the NWB file."""
    stream_ids = sorted(dtype for dtype in discovered_datatypes if dtype.endswith("_behEvents"))
    if not stream_ids:
        return

    for datatype_id in stream_ids:
        try:
            _add_one_beh_events_stream(
                nwbfile,
                context,
                dataset_dir,
                session_dir,
                datatype_id,
            )
        except Exception as exc:
            record_table_gap(
                context,
                f"behEvents handler failed for {datatype_id}: {exc}",
            )
            logger.exception("Failed converting behEvents stream %s", datatype_id)


def _add_one_beh_events_stream(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    datatype_id: str,
) -> None:
    data_file = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_data.{{mat|npz}}",
        context.session_record,
        datatype_id=datatype_id,
    )
    if data_file is None:
        record_warning(context, f"Skipping {datatype_id}: missing data file.")
        return

    raw = load_numeric_array(data_file.path)
    metadata_rows = _load_metadata_rows(session_dir, dataset_dir, context.session_record, datatype_id)
    schema = _load_schema(session_dir, dataset_dir, context.session_record, datatype_id)
    event_series = _load_event_time_series(raw, metadata_rows, context, datatype_id, schema)

    if metadata_rows and len(event_series) != len(metadata_rows):
        raise ValueError(
            f"{datatype_id}: metadata rows {len(metadata_rows)} != "
            f"event-type count {len(event_series)}"
        )

    events = getattr(nwbfile, "events", None) or {}
    if datatype_id in events:
        record_warning(context, f"{datatype_id}: events table exists; skipping rewrite")
    else:
        _add_events_table(nwbfile, datatype_id, event_series, metadata_rows, schema, context)

    events_table = _build_events_metadata_table(datatype_id, metadata_rows, len(event_series), context)
    behavior = _ensure_behavior_module(nwbfile)
    behavior.add(events_table)

    _add_surlab_schema_labmetadata(nwbfile, datatype_id, schema, context)
    logger.info(
        "Added behEvents stream %s: %d event type(s), lengths=%s",
        datatype_id,
        len(event_series),
        [len(np.asarray(ts).ravel()) for ts in event_series],
    )


def _add_events_table(
    nwbfile,
    datatype_id: str,
    event_series: List[np.ndarray],
    metadata_rows: List[Dict[str, str]],
    schema: Dict[str, object],
    context: PlacementContext,
) -> None:
    unit_hint = _resolve_data_unit_measurement(context, schema, datatype_id)
    events_table = nwbfile.create_events_table(
        name=datatype_id,
        description=f"SurLab behEvents stream {datatype_id}; data_unit_measurement={unit_hint}",
    )
    events_table.add_column(name="annotation", description="SurLab event_label")

    for index, timestamps in enumerate(event_series):
        row = metadata_rows[index] if index < len(metadata_rows) else {}
        label = str(row.get("event_label", "")).strip()
        if not label:
            label = f"event{index}"
            record_warning(context, f"{datatype_id}: event row {index} missing event_label")
        for timestamp in np.asarray(timestamps, dtype=float).ravel():
            events_table.add_event(timestamp=float(timestamp), annotation=label)


def _load_event_time_series(
    raw: np.ndarray,
    metadata_rows: List[Dict[str, str]],
    context: PlacementContext,
    datatype_id: str,
    schema: Dict[str, object],
) -> List[np.ndarray]:
    if raw.dtype == object or raw.ndim >= 1 and raw.size and isinstance(raw.ravel()[0], (list, np.ndarray)):
        series = squeeze_object_array(raw)
        return [np.asarray(item, dtype=float).ravel() for item in series]

    if raw.ndim == 1:
        return [np.asarray(raw, dtype=float).ravel()]

    if raw.ndim == 2:
        n_meta = len(metadata_rows)
        y_size = schema.get("Y_size")
        if n_meta and raw.shape[1] == n_meta:
            return [raw[:, index].ravel() for index in range(raw.shape[1])]
        if n_meta and raw.shape[0] == n_meta:
            record_warning(context, f"{datatype_id}: treating behEvents rows as event types")
            return [raw[index, :].ravel() for index in range(raw.shape[0])]
        if _is_number(y_size):
            y_size_int = int(y_size)
            if raw.shape[1] == y_size_int:
                return [raw[:, index].ravel() for index in range(raw.shape[1])]
            if raw.shape[0] == y_size_int:
                return [raw[index, :].ravel() for index in range(raw.shape[0])]
        if raw.shape[0] == 1:
            return [raw.reshape(-1)]
        if raw.shape[1] == 1:
            return [raw.reshape(-1)]

    raise ValueError(f"{datatype_id}: unsupported behEvents data shape {raw.shape}")


def _build_events_metadata_table(
    datatype_id: str,
    metadata_rows: List[Dict[str, str]],
    n_event_types: int,
    context: PlacementContext,
):
    from hdmf.common import DynamicTable

    table_name = f"{datatype_id}_events"
    table = DynamicTable(
        name=table_name,
        description=(
            f"Event identity for {datatype_id}; row i aligns with object-array slot i "
            f"and EventsTable annotation labels"
        ),
    )
    table.add_column(name="event_ID", description="SurLab event_ID")
    table.add_column(name="event_label", description="SurLab event_label")

    extra_cols: List[str] = []
    if metadata_rows:
        for key in metadata_rows[0].keys():
            if key in EVENT_COLUMNS or key in extra_cols:
                continue
            extra_cols.append(key)
    for extra_name in extra_cols:
        table.add_column(name=extra_name, description=f"SurLab dataset_specific {extra_name}")

    for index in range(n_event_types):
        row = metadata_rows[index] if index < len(metadata_rows) else {}
        event_id = row.get("event_ID", str(index))
        event_label = str(row.get("event_label", "")).strip()
        if not event_label:
            event_label = MISSING_MARKER
            record_warning(context, f"{datatype_id}: event row {index} missing event_label")
        kwargs = {
            "event_ID": _coerce_id(event_id),
            "event_label": event_label,
        }
        for extra_name in extra_cols:
            kwargs[extra_name] = str(row.get(extra_name, "")).strip()
        table.add_row(**kwargs)

    return table


def _load_schema(
    session_dir: Path,
    dataset_dir: Path,
    session_record: Dict[str, str],
    datatype_id: str,
) -> Dict[str, object]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_schema.json",
        session_record,
        datatype_id=datatype_id,
    )
    if resolved is None:
        return {}
    return normalize_schema_keys(load_json(resolved.path))


def _load_metadata_rows(
    session_dir: Path,
    dataset_dir: Path,
    session_record: Dict[str, str],
    datatype_id: str,
) -> List[Dict[str, str]]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_metadata.csv",
        session_record,
        datatype_id=datatype_id,
    )
    if resolved is None:
        return []
    return [dict(row) for row in read_csv_rows(resolved.path)]


def _resolve_data_unit_measurement(
    context: PlacementContext,
    schema: Dict[str, object],
    datatype_id: str,
) -> str:
    session_key = f"{datatype_id}_data_unit_measurement"
    session_value = context.session_record.get(session_key, "")
    schema_value = schema.get("data_unit_measurement", "")

    session_present = field_non_empty(session_value)
    schema_present = field_non_empty(schema_value)

    if session_present and schema_present:
        left = str(session_value).strip()
        right = str(schema_value).strip()
        if left != right:
            raise ValueError(
                f"{datatype_id}: sessionInfo {session_key}={left!r} disagrees with "
                f"schema data_unit_measurement={right!r}"
            )
        return left
    if session_present:
        return str(session_value).strip()
    if schema_present:
        return str(schema_value).strip()
    return "time__s"


def _add_surlab_schema_labmetadata(
    nwbfile,
    datatype_id: str,
    schema: Dict[str, object],
    context: PlacementContext,
) -> None:
    payload: Dict[str, object] = {}
    unit_token = _resolve_data_unit_measurement(context, schema, datatype_id)
    if field_non_empty(unit_token):
        payload["data_unit_measurement"] = unit_token

    for key, value in schema.items():
        if key in LAYOUT_FIELDS or key in payload:
            continue
        if field_non_empty(value):
            payload[key] = value

    if not payload:
        return

    container_name = f"SurLabSchema_{datatype_id}"
    schema_json = json.dumps(payload, sort_keys=True, default=str)
    if container_name in getattr(nwbfile, "lab_meta_data", {}):
        nwbfile.lab_meta_data[container_name].schema_json = schema_json
        return

    nwbfile.add_lab_meta_data(SurLabSchemaMeta(name=container_name, schema_json=schema_json))


def _ensure_behavior_module(nwbfile):
    if "behavior" in nwbfile.processing:
        return nwbfile.processing["behavior"]
    return nwbfile.create_processing_module(
        name="behavior",
        description="behavioral continuous streams, features, and events",
    )


def _coerce_id(value: object):
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        return text


def _is_number(value: object) -> bool:
    if value is None:
        return False
    try:
        float(value)
        return str(value).strip() != ""
    except (TypeError, ValueError):
        return False
