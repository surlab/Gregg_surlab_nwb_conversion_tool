"""Write SurLab ``*_behTSeries`` streams into stock NWB containers.

Placement (conversion table stage 4):
- ``acquisition/<datatypeID>`` TimeSeries (data, timestamps, unit)
- ``processing/behavior/<datatypeID>_features`` DynamicTable
  (feature_ID, feature_label, extras; row i ↔ data column i)
- Layout schema keys are validate_only (not written)
- Rare schema leftovers → SurLabSchema_<datatypeID> LabMetaData

PyNWB forbids TimeSeries.rate together with timestamps; when timestamps are
written (always for SurLab), ``sample_frequency__Hz`` goes to SurLabSchema.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import numpy as np

from src.data_io import load_json, load_numeric_array, normalize_schema_keys
from src.nwb_surlab_schema import SurLabSchemaMeta
from src.session_record import field_non_empty, read_csv_rows
from src.surlab_paths import resolve_session_file
from src.table_placement import PlacementContext, record_table_gap, record_warning

logger = logging.getLogger(__name__)

MISSING_MARKER = "MISSING_REQUIRED_FOR_NWB"

CORE_SCALAR_FIELDS = {
    "data_unit_measurement",
    "sample_frequency__Hz",
}

LAYOUT_FIELDS = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}

FEATURE_COLUMNS = ("feature_ID", "feature_label")


def apply_beh_tseries(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    discovered_datatypes: set[str],
) -> None:
    """Add all discovered ``*_behTSeries`` streams to the NWB file."""
    stream_ids = sorted(dtype for dtype in discovered_datatypes if dtype.endswith("_behTSeries"))
    if not stream_ids:
        return

    for datatype_id in stream_ids:
        try:
            _add_one_beh_tseries_stream(
                nwbfile,
                context,
                dataset_dir,
                session_dir,
                datatype_id,
            )
        except Exception as exc:
            record_table_gap(
                context,
                f"behTSeries handler failed for {datatype_id}: {exc}",
            )
            logger.exception("Failed converting behTSeries stream %s", datatype_id)


def _add_one_beh_tseries_stream(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
    datatype_id: str,
) -> None:
    from pynwb.base import TimeSeries

    data_file = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_data.{{mat|npz}}",
        context.session_record,
        datatype_id=datatype_id,
    )
    timestamps_file = resolve_session_file(
        session_dir,
        dataset_dir,
        f"{datatype_id}_timestamps.{{mat|npz}}",
        context.session_record,
        datatype_id=datatype_id,
    )
    if data_file is None or timestamps_file is None:
        record_warning(
            context,
            f"Skipping {datatype_id}: missing data and/or timestamps file.",
        )
        return

    data = np.asarray(load_numeric_array(data_file.path), dtype=float)
    timestamps = np.asarray(load_numeric_array(timestamps_file.path), dtype=float).ravel()
    schema = _load_schema(session_dir, dataset_dir, context.session_record, datatype_id)
    metadata_rows = _load_metadata_rows(session_dir, dataset_dir, context.session_record, datatype_id)
    scalars = _resolve_stream_scalars(context, datatype_id, schema)

    data = _ensure_time_by_feature(data, metadata_rows, context, datatype_id, schema)
    if data.ndim == 1:
        data = data.reshape(-1, 1)

    if data.shape[0] != timestamps.shape[0]:
        raise ValueError(
            f"{datatype_id}: timestamps length {timestamps.shape[0]} != data time axis {data.shape[0]}"
        )
    if metadata_rows and data.shape[1] != len(metadata_rows):
        raise ValueError(
            f"{datatype_id}: metadata rows {len(metadata_rows)} != data feature axis {data.shape[1]}"
        )

    unit = str(scalars.get("data_unit_measurement") or MISSING_MARKER)
    time_series = TimeSeries(
        name=datatype_id,
        data=data,
        unit=unit,
        timestamps=timestamps,
        description=f"SurLab behTSeries stream {datatype_id}",
    )
    nwbfile.add_acquisition(time_series)

    n_features = data.shape[1]
    features_table = _build_features_table(datatype_id, metadata_rows, n_features, context)
    behavior = _ensure_behavior_module(nwbfile)
    behavior.add(features_table)

    _add_surlab_schema_labmetadata(nwbfile, datatype_id, scalars, schema)
    logger.info(
        "Added behTSeries stream %s: data%s timestamps=%d features=%d",
        datatype_id,
        data.shape,
        timestamps.shape[0],
        n_features,
    )


def _ensure_time_by_feature(
    data: np.ndarray,
    metadata_rows: List[Dict[str, str]],
    context: PlacementContext,
    datatype_id: str,
    schema: Dict[str, object],
) -> np.ndarray:
    """Return array shaped (n_time, n_feature); transpose on clear mismatch."""
    if data.ndim == 1:
        return data.reshape(-1, 1)
    if data.ndim != 2:
        raise ValueError(f"{datatype_id}: expected 1-D or 2-D behTSeries array, got shape {data.shape}")

    n_meta = len(metadata_rows)
    x_dim = str(schema.get("X_dim", "")).strip().lower()
    y_dim = str(schema.get("Y_dim", "")).strip().lower()
    y_size = schema.get("Y_size")

    if x_dim == "time" and y_dim in {"feature", "features"}:
        return data
    if y_dim == "time" and x_dim in {"feature", "features"}:
        record_warning(context, f"{datatype_id}: transposing behTSeries from features x time to time x features")
        return data.T

    if n_meta and data.shape[1] == n_meta:
        return data
    if n_meta and data.shape[0] == n_meta:
        record_warning(
            context,
            f"{datatype_id}: transposing behTSeries so feature axis matches metadata row count",
        )
        return data.T
    if _is_number(y_size):
        y_size_int = int(y_size)
        if y_size_int == 0:
            return data
        if data.shape[1] == y_size_int:
            return data
        if data.shape[0] == y_size_int:
            record_warning(context, f"{datatype_id}: transposing behTSeries to match Y_size={y_size_int}")
            return data.T

    return data


def _build_features_table(
    datatype_id: str,
    metadata_rows: List[Dict[str, str]],
    n_features: int,
    context: PlacementContext,
):
    from hdmf.common import DynamicTable

    table_name = f"{datatype_id}_features"
    table = DynamicTable(
        name=table_name,
        description=(
            f"Feature identity for {datatype_id}; row i aligns with "
            f"acquisition/{datatype_id}.data[:, i] (no DynamicTableRegion link)"
        ),
    )
    table.add_column(name="feature_ID", description="SurLab feature_ID")
    table.add_column(name="feature_label", description="SurLab feature_label")

    extra_cols: List[str] = []
    if metadata_rows:
        for key in metadata_rows[0].keys():
            if key in FEATURE_COLUMNS:
                continue
            if key not in extra_cols:
                extra_cols.append(key)
    for extra_name in extra_cols:
        table.add_column(name=extra_name, description=f"SurLab dataset_specific {extra_name}")

    for index in range(n_features):
        row = metadata_rows[index] if index < len(metadata_rows) else {}
        feature_id = row.get("feature_ID", str(index))
        feature_label = str(row.get("feature_label", "")).strip()
        if not feature_label:
            feature_label = MISSING_MARKER
            record_warning(context, f"{datatype_id}: feature row {index} missing feature_label")
        kwargs = {
            "feature_ID": _coerce_id(feature_id),
            "feature_label": feature_label,
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


def _resolve_stream_scalars(
    context: PlacementContext,
    datatype_id: str,
    schema: Dict[str, object],
) -> Dict[str, object]:
    """sessionInfo-first; optional schema mirror; fail if both disagree."""
    resolved: Dict[str, object] = {}
    for field_name in sorted(CORE_SCALAR_FIELDS):
        session_key = f"{datatype_id}_{field_name}"
        session_value = context.session_record.get(session_key, "")
        schema_value = schema.get(field_name, "")

        session_present = field_non_empty(session_value)
        schema_present = field_non_empty(schema_value)

        if session_present and schema_present:
            left = str(session_value).strip()
            right = str(schema_value).strip()
            if left != right and not _numeric_equal(left, right):
                raise ValueError(
                    f"{datatype_id}: sessionInfo {session_key}={left!r} disagrees with "
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
    datatype_id: str,
    scalars: Dict[str, object],
    schema: Dict[str, object],
) -> None:
    payload: Dict[str, object] = {}

    # Timestamps are always written; PyNWB cannot also set TimeSeries.rate.
    rate_value = scalars.get("sample_frequency__Hz")
    if field_non_empty(rate_value):
        payload["sample_frequency__Hz"] = rate_value

    reserved = CORE_SCALAR_FIELDS.union(LAYOUT_FIELDS)
    for key, value in schema.items():
        if key in reserved:
            continue
        if key in payload:
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
        description="behavioral continuous streams and feature tables",
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
