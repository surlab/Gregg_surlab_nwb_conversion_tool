"""Write SurLab ``lfp`` stream into stock NWB ecephys containers.

Placement (conversion table stage 6):
- ``acquisition/lfp`` ElectricalSeries (data, timestamps, unit) with linked
  ``electrodes`` DynamicTableRegion
- ``general/extracellular_ephys/electrodes`` from ``lfp_metadata.csv`` (LFP-only)
- ``Device`` + ``ElectrodeGroup`` from ``lfp_probe``
- Layout validate_only; filters and descriptive rate (when timestamps present)
  → ``SurLabSchema_lfp`` LabMetaData
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from src.data_io import load_json, load_numeric_array, normalize_schema_keys, parse_coordinate_value
from src.nwb_surlab_schema import SurLabSchemaMeta
from src.session_record import field_non_empty, read_csv_rows
from src.surlab_paths import resolve_session_file
from src.table_placement import PlacementContext, record_table_gap, record_warning

logger = logging.getLogger(__name__)

LFP_DATATYPE_ID = "lfp"
LFP_SERIES_NAME = "lfp"
LABMETA_CONTAINER = "SurLabSchema_lfp"

MISSING_MARKER = "MISSING_REQUIRED_FOR_NWB"

CORE_SCALAR_FIELDS = {
    "data_unit_measurement",
    "sample_frequency__Hz",
    "probe",
}

LABMETA_SCALAR_FIELDS = {
    "filter_type",
    "filter_cutoff_low__Hz",
    "filter_cutoff_high__Hz",
}

LAYOUT_FIELDS = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}

ELECTRODE_COLUMN_MAP = {
    "channel_label": "channel_label",
    "depth__um": "depth__um",
    "grid_location": "grid_location",
}

OPTIONAL_COORD_FIELDS = ("channel_x_coordinate", "channel_y_coordinate")


def apply_lfp(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    discovered_datatypes: set[str],
) -> None:
    """Add LFP ElectricalSeries and linked electrodes when ``lfp`` is present."""
    if LFP_DATATYPE_ID not in discovered_datatypes:
        return
    try:
        _add_lfp_stream(nwbfile, context, dataset_dir, session_dir, discovered_datatypes)
    except Exception as exc:
        record_table_gap(context, f"lfp handler failed: {exc}")
        logger.exception("Failed converting lfp stream")


def _add_lfp_stream(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    discovered_datatypes: set[str],
) -> None:
    from pynwb.ecephys import ElectricalSeries

    if LFP_SERIES_NAME in nwbfile.acquisition:
        record_warning(context, f"LFP acquisition '{LFP_SERIES_NAME}' already exists; skipping rewrite")
        return

    data_file = resolve_session_file(
        session_dir,
        dataset_dir,
        "lfp_data.{mat|npz}",
        context.session_record,
        datatype_id=LFP_DATATYPE_ID,
    )
    timestamps_file = resolve_session_file(
        session_dir,
        dataset_dir,
        "lfp_timestamps.{mat|npz}",
        context.session_record,
        datatype_id=LFP_DATATYPE_ID,
    )
    if data_file is None or timestamps_file is None:
        record_warning(context, "Skipping lfp: missing data and/or timestamps file.")
        return

    data = np.asarray(load_numeric_array(data_file.path), dtype=float)
    timestamps = np.asarray(load_numeric_array(timestamps_file.path), dtype=float).ravel()
    schema = _load_schema(session_dir, dataset_dir, context.session_record)
    metadata_rows = _load_metadata_rows(session_dir, dataset_dir, context.session_record)
    scalars = _resolve_lfp_scalars(context, schema)

    data = _ensure_time_by_channel(data, metadata_rows, context, schema)
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    if data.shape[0] != timestamps.shape[0]:
        raise ValueError(
            f"lfp: timestamps length {timestamps.shape[0]} != data time axis {data.shape[0]}"
        )
    if metadata_rows and data.shape[1] != len(metadata_rows):
        raise ValueError(
            f"lfp: metadata rows {len(metadata_rows)} != data channel axis {data.shape[1]}"
        )

    n_channels = data.shape[1]
    if nwbfile.electrodes is not None and len(nwbfile.electrodes) > 0:
        raise ValueError(
            "lfp: electrodes table already populated; LFP-only electrode build expected empty table"
        )

    device = _ensure_probe_device(nwbfile, scalars, context, discovered_datatypes)
    electrode_group = _ensure_lfp_electrode_group(nwbfile, device, context)
    _add_lfp_electrodes(
        nwbfile,
        metadata_rows,
        n_channels,
        electrode_group,
        context,
    )
    electrode_region = nwbfile.create_electrode_table_region(
        region=list(range(n_channels)),
        description="LFP channels linked to acquisition/lfp ElectricalSeries",
    )

    unit = str(scalars.get("data_unit_measurement") or MISSING_MARKER)
    description = f"SurLab lfp stream; data_unit_measurement={unit}"
    electrical_series = ElectricalSeries(
        name=LFP_SERIES_NAME,
        data=data,
        electrodes=electrode_region,
        timestamps=timestamps,
        description=description,
    )
    nwbfile.add_acquisition(electrical_series)
    _add_surlab_schema_labmetadata(nwbfile, scalars, schema, unit_token=unit)

    logger.info(
        "Added lfp stream: data%s timestamps=%d channels=%d",
        data.shape,
        timestamps.shape[0],
        n_channels,
    )


def _ensure_time_by_channel(
    data: np.ndarray,
    metadata_rows: List[Dict[str, str]],
    context: PlacementContext,
    schema: Dict[str, object],
) -> np.ndarray:
    if data.ndim == 1:
        return data
    if data.ndim != 2:
        raise ValueError(f"lfp: expected 1-D or 2-D array, got shape {data.shape}")

    n_meta = len(metadata_rows)
    x_dim = str(schema.get("X_dim", "")).strip().lower()
    y_dim = str(schema.get("Y_dim", "")).strip().lower()
    y_size = schema.get("Y_size")

    if x_dim == "time" and y_dim in {"channel", "channels"}:
        return data
    if y_dim == "time" and x_dim in {"channel", "channels"}:
        record_warning(context, "lfp: transposing from channels x time to time x channels")
        return data.T

    if n_meta and data.shape[1] == n_meta:
        return data
    if n_meta and data.shape[0] == n_meta:
        record_warning(context, "lfp: transposing so channel axis matches metadata row count")
        return data.T
    if _is_number(y_size):
        y_size_int = int(y_size)
        if data.shape[1] == y_size_int:
            return data
        if data.shape[0] == y_size_int:
            record_warning(context, f"lfp: transposing to match Y_size={y_size_int}")
            return data.T

    return data


def _ensure_probe_device(
    nwbfile,
    scalars: Dict[str, object],
    context: PlacementContext,
    discovered_datatypes: set[str],
):
    probe_name = str(scalars.get("probe") or "").strip()
    if not probe_name and "spikeTimes" in discovered_datatypes:
        spike_probe = str(context.session_record.get("spikeTimes_probe", "")).strip()
        if spike_probe:
            probe_name = spike_probe
            record_warning(
                context,
                "lfp: missing lfp_probe; reusing spikeTimes_probe (single probe session)",
            )
        elif nwbfile.devices:
            probe_name = next(iter(nwbfile.devices.keys()))
            record_warning(
                context,
                f"lfp: missing lfp_probe; reusing existing Device '{probe_name}' from spikeTimes",
            )

    if not probe_name:
        probe_name = MISSING_MARKER
        record_warning(context, "lfp: missing lfp_probe; using MISSING_REQUIRED_FOR_NWB device name")

    if probe_name in nwbfile.devices:
        return nwbfile.devices[probe_name]

    return nwbfile.create_device(name=probe_name, description=f"LFP probe for {LFP_DATATYPE_ID}")


def _ensure_lfp_electrode_group(nwbfile, device, context: PlacementContext):
    group_name = f"{LFP_DATATYPE_ID}_electrodes"
    if group_name in nwbfile.electrode_groups:
        return nwbfile.electrode_groups[group_name]

    location = str(context.session_record.get("area", "")).strip() or MISSING_MARKER
    return nwbfile.create_electrode_group(
        name=group_name,
        description=f"Electrode group for SurLab {LFP_DATATYPE_ID}",
        location=location,
        device=device,
    )


def _add_lfp_electrodes(
    nwbfile,
    metadata_rows: List[Dict[str, str]],
    n_channels: int,
    electrode_group,
    context: PlacementContext,
) -> None:
    known = {"channel_ID", *ELECTRODE_COLUMN_MAP.keys(), *OPTIONAL_COORD_FIELDS}
    extra_cols: List[str] = []
    if metadata_rows:
        for key in metadata_rows[0].keys():
            if key not in known and key not in extra_cols:
                extra_cols.append(key)

    existing_cols = set(nwbfile.electrodes.colnames) if nwbfile.electrodes is not None else set()
    for source_name, target_name in ELECTRODE_COLUMN_MAP.items():
        if metadata_rows and any(field_non_empty(metadata_row.get(source_name, "")) for metadata_row in metadata_rows):
            if target_name not in existing_cols:
                nwbfile.add_electrode_column(name=target_name, description=f"SurLab {source_name}")
                existing_cols.add(target_name)
    for extra_name in extra_cols:
        if extra_name not in existing_cols:
            nwbfile.add_electrode_column(name=extra_name, description=f"SurLab dataset_specific {extra_name}")
            existing_cols.add(extra_name)

    for index in range(n_channels):
        row = metadata_rows[index] if index < len(metadata_rows) else {}
        electrode_id = _coerce_id(row.get("channel_ID", index))
        location = str(row.get("area", "")).strip() or MISSING_MARKER
        x_val = parse_coordinate_value(row.get("channel_x_coordinate", ""))
        y_val = parse_coordinate_value(row.get("channel_y_coordinate", ""))
        z_val = parse_coordinate_value(row.get("depth__um", ""))

        kwargs = {
            "id": electrode_id,
            "x": x_val if isinstance(x_val, float) and not np.isnan(x_val) else float("nan"),
            "y": y_val if isinstance(y_val, float) and not np.isnan(y_val) else float("nan"),
            "z": z_val if isinstance(z_val, float) and not np.isnan(z_val) else float("nan"),
            "imp": -1.0,
            "location": location,
            "filtering": MISSING_MARKER,
            "group": electrode_group,
        }
        for source_name, target_name in ELECTRODE_COLUMN_MAP.items():
            if target_name not in existing_cols:
                continue
            raw = row.get(source_name, "")
            if source_name == "depth__um" and field_non_empty(raw):
                kwargs[target_name] = float(raw)
            elif field_non_empty(raw):
                kwargs[target_name] = str(raw).strip()
        for extra_name in extra_cols:
            kwargs[extra_name] = str(row.get(extra_name, "")).strip()

        nwbfile.add_electrode(**kwargs)


def _load_schema(session_dir: Path, dataset_dir: Path, session_record: Dict[str, str]) -> Dict[str, object]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "lfp_schema.json",
        session_record,
        datatype_id=LFP_DATATYPE_ID,
    )
    if resolved is None:
        return {}
    return normalize_schema_keys(load_json(resolved.path))


def _load_metadata_rows(
    session_dir: Path,
    dataset_dir: Path,
    session_record: Dict[str, str],
) -> List[Dict[str, str]]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "lfp_metadata.csv",
        session_record,
        datatype_id=LFP_DATATYPE_ID,
    )
    if resolved is None:
        return []
    return [dict(row) for row in read_csv_rows(resolved.path)]


def _resolve_lfp_scalars(context: PlacementContext, schema: Dict[str, object]) -> Dict[str, object]:
    """sessionInfo-first for lfp_* and schema mirror; fail if both disagree."""
    resolved: Dict[str, object] = {}
    interested = CORE_SCALAR_FIELDS.union(LABMETA_SCALAR_FIELDS)
    for field_name in sorted(interested):
        session_key = f"{LFP_DATATYPE_ID}_{field_name}"
        if field_name == "probe":
            session_key = "lfp_probe"
        session_value = context.session_record.get(session_key, "")
        schema_value = schema.get(field_name, "")

        session_present = field_non_empty(session_value)
        schema_present = field_non_empty(schema_value)

        if session_present and schema_present:
            left = str(session_value).strip()
            right = str(schema_value).strip()
            if left != right and not _numeric_equal(left, right):
                raise ValueError(
                    f"lfp: sessionInfo {session_key}={left!r} disagrees with "
                    f"schema {field_name}={right!r}"
                )
            resolved[field_name] = _maybe_number(session_value)
        elif session_present:
            resolved[field_name] = _maybe_number(session_value)
        elif schema_present:
            resolved[field_name] = _maybe_number(schema_value)
    return resolved


def _add_surlab_schema_labmetadata(
    nwbfile,
    scalars: Dict[str, object],
    schema: Dict[str, object],
    unit_token: str = "",
) -> None:
    payload: Dict[str, object] = {}

    if field_non_empty(unit_token):
        payload["data_unit_measurement"] = unit_token

    for field_name in LABMETA_SCALAR_FIELDS:
        if field_name in scalars and field_non_empty(scalars[field_name]):
            payload[field_name] = scalars[field_name]

    rate_value = scalars.get("sample_frequency__Hz")
    if field_non_empty(rate_value):
        payload["sample_frequency__Hz"] = rate_value

    reserved = CORE_SCALAR_FIELDS.union(LABMETA_SCALAR_FIELDS).union(LAYOUT_FIELDS)
    for key, value in schema.items():
        if key in reserved:
            continue
        if key in payload:
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


def _coerce_id(value: object):
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        return text


def _optional_float(value: object) -> Optional[float]:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "na", "n/a"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _is_number(value: object) -> bool:
    if value is None:
        return False
    try:
        float(value)
        return str(value).strip() != ""
    except (TypeError, ValueError):
        return False


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
