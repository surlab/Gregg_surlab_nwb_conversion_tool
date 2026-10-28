"""Write SurLab spikeWaves into the NWB Units table waveforms column.

Placement (conversion table stage 7):
- ``spikeWaves_data`` → ``Units.waveforms`` (one snippet per unit, 1-D length n_samples)
- ``sample_frequency__Hz`` → ``Units.waveform_rate``
- optional ``spikeWaves_timestamps`` → ``SurLabSchema_spikeWaves.snippet_timestamps``
- metadata ``unit_ID`` aligns with existing ``Units.id`` when spikeTimes is present
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from src.data_io import load_json, load_numeric_array, normalize_schema_keys
from src.nwb_surlab_schema import SurLabSchemaMeta
from src.session_record import field_non_empty, read_csv_rows
from src.surlab_paths import resolve_session_file
from src.table_placement import PlacementContext, record_table_gap, record_warning

logger = logging.getLogger(__name__)

SPIKE_WAVES_ID = "spikeWaves"
LABMETA_CONTAINER = "SurLabSchema_spikeWaves"

CORE_SCALAR_FIELDS = {
    "data_unit_measurement",
    "sample_frequency__Hz",
    "probe",
}

LABMETA_SCALAR_FIELDS = {
    "clustering_algorithm",
}

LAYOUT_FIELDS = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}

WAVEFORM_METADATA_MAP = {
    "primary_channel": "primary_channel",
}


def apply_spike_waves(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
) -> None:
    """Add waveform snippets to Units when spikeWaves files are present."""
    try:
        _add_spike_waves(nwbfile, context, dataset_dir, session_dir)
    except Exception as exc:
        record_table_gap(context, f"spikeWaves handler failed: {exc}")
        logger.exception("Failed converting spikeWaves")


def _add_spike_waves(
    nwbfile,
    context: PlacementContext,
    dataset_dir: Path,
    session_dir: Path,
) -> None:
    data_file = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeWaves_data.{mat|npz}",
        context.session_record,
        datatype_id=SPIKE_WAVES_ID,
    )
    if data_file is None:
        return

    data = np.asarray(load_numeric_array(data_file.path), dtype=float)
    metadata_rows = _load_metadata_rows(session_dir, dataset_dir, context.session_record)
    schema = _load_schema(session_dir, dataset_dir, context.session_record)
    snippet_timestamps = _load_snippet_timestamps(session_dir, dataset_dir, context.session_record)
    scalars = _resolve_scalars(context, schema)

    data = _ensure_samples_by_unit(data, metadata_rows, context, schema)
    if metadata_rows and data.shape[1] != len(metadata_rows):
        raise ValueError(
            f"spikeWaves: metadata rows {len(metadata_rows)} != unit axis {data.shape[1]}"
        )

    _ensure_probe_device(nwbfile, scalars, context)
    unit_ids_in_table = _ensure_units_for_waveforms(nwbfile, metadata_rows, data.shape[1], context)
    waveforms_by_id = _waveforms_by_unit_id(data, metadata_rows)
    waveform_list = [_waveform_for_unit(unit_id, waveforms_by_id) for unit_id in unit_ids_in_table]

    if "waveforms" in nwbfile.units.colnames:
        record_warning(context, "spikeWaves: overwriting existing Units.waveforms column")
    nwbfile.units.add_column(
        name="waveforms",
        description="Spike waveform snippet per unit (SurLab spikeWaves)",
        data=waveform_list,
    )

    rate = scalars.get("sample_frequency__Hz")
    if field_non_empty(rate):
        try:
            nwbfile.units.waveform_rate = float(rate)
        except (TypeError, ValueError):
            record_warning(
                context,
                f"spikeWaves: ignoring non-numeric sample_frequency__Hz={rate!r}",
            )

    unit_token = str(scalars.get("data_unit_measurement") or "")
    if unit_token:
        record_warning(
            context,
            "spikeWaves: Units.waveform_unit is fixed by PyNWB; stored data_unit_measurement in SurLabSchema",
        )

    _add_waveform_metadata_columns(nwbfile, metadata_rows, unit_ids_in_table, context)
    _add_surlab_schema_labmetadata(nwbfile, scalars, schema, snippet_timestamps, unit_token)

    logger.info(
        "Added spikeWaves for %d units: waveform length %d samples",
        len(unit_ids_in_table),
        data.shape[0],
    )


def _ensure_samples_by_unit(
    data: np.ndarray,
    metadata_rows: List[Dict[str, str]],
    context: PlacementContext,
    schema: Dict[str, object],
) -> np.ndarray:
    if data.ndim != 2:
        raise ValueError(f"spikeWaves: expected 2-D array, got shape {data.shape}")

    x_dim = str(schema.get("X_dim", "")).strip().lower()
    y_dim = str(schema.get("Y_dim", "")).strip().lower()
    y_size = schema.get("Y_size")
    n_meta = len(metadata_rows)

    if x_dim in {"waveform_sample", "waveform_samples", "waveform_sample_index"} and y_dim in {
        "unit",
        "units",
    }:
        return data
    if y_dim in {"waveform_sample", "waveform_samples"} and x_dim in {"unit", "units"}:
        record_warning(context, "spikeWaves: transposing from units x samples to samples x units")
        return data.T

    if n_meta and data.shape[1] == n_meta:
        return data
    if n_meta and data.shape[0] == n_meta:
        record_warning(context, "spikeWaves: transposing so unit axis matches metadata row count")
        return data.T
    if _is_number(y_size):
        y_size_int = int(y_size)
        if data.shape[1] == y_size_int:
            return data
        if data.shape[0] == y_size_int:
            record_warning(context, f"spikeWaves: transposing to match Y_size={y_size_int}")
            return data.T

    return data


def _waveforms_by_unit_id(
    data: np.ndarray,
    metadata_rows: List[Dict[str, str]],
) -> Dict[object, np.ndarray]:
    mapping: Dict[object, np.ndarray] = {}
    for index in range(data.shape[1]):
        unit_id = _coerce_id(metadata_rows[index].get("unit_ID", index)) if index < len(metadata_rows) else index
        mapping[unit_id] = np.asarray(data[:, index], dtype=float).ravel()
    return mapping


def _waveform_for_unit(unit_id: object, waveforms_by_id: Dict[object, np.ndarray]) -> np.ndarray:
    if unit_id in waveforms_by_id:
        return waveforms_by_id[unit_id]
    if str(unit_id) in {str(key) for key in waveforms_by_id}:
        for key, value in waveforms_by_id.items():
            if str(key) == str(unit_id):
                return value
    raise KeyError(f"spikeWaves: no waveform column for unit id {unit_id!r}")


def _ensure_units_for_waveforms(
    nwbfile,
    metadata_rows: List[Dict[str, str]],
    n_units: int,
    context: PlacementContext,
) -> List[object]:
    if nwbfile.units is not None and len(nwbfile.units) > 0:
        return [_coerce_id(value) for value in nwbfile.units["id"][:]]

    if not metadata_rows:
        record_warning(context, "spikeWaves: creating units without metadata rows")
        for index in range(n_units):
            nwbfile.add_unit(id=index, spike_times=np.array([], dtype=float))
        return list(range(n_units))

    for row in metadata_rows:
        unit_id = _coerce_id(row.get("unit_ID", ""))
        nwbfile.add_unit(id=unit_id, spike_times=np.array([], dtype=float))
    return [_coerce_id(row.get("unit_ID", index)) for index, row in enumerate(metadata_rows)]


def _add_waveform_metadata_columns(
    nwbfile,
    metadata_rows: List[Dict[str, str]],
    unit_ids_in_table: List[object],
    context: PlacementContext,
) -> None:
    if not metadata_rows:
        return

    row_by_id = {_coerce_id(row.get("unit_ID", index)): row for index, row in enumerate(metadata_rows)}
    existing_cols = set(nwbfile.units.colnames)

    for source_name, target_name in WAVEFORM_METADATA_MAP.items():
        if not any(field_non_empty(row.get(source_name, "")) for row in metadata_rows):
            continue

        if target_name in existing_cols:
            continue

        values = []
        for unit_id in unit_ids_in_table:
            row = row_by_id.get(unit_id) or row_by_id.get(str(unit_id))
            raw = row.get(source_name, "") if row else ""
            if source_name == "primary_channel" and field_non_empty(raw):
                values.append(_coerce_id(raw))
            elif field_non_empty(raw):
                values.append(str(raw).strip())
            else:
                values.append(np.nan if source_name == "primary_channel" else "")

        nwbfile.add_unit_column(
            name=target_name,
            description=f"SurLab spikeWaves {source_name}",
            data=values,
        )
        existing_cols.add(target_name)


def _ensure_probe_device(nwbfile, scalars: Dict[str, object], context: PlacementContext) -> None:
    """Reuse probe Device from spikeTimes when present; do not duplicate."""
    probe_name = str(scalars.get("probe") or "").strip()
    if not probe_name:
        return
    if probe_name in nwbfile.devices:
        return
    record_warning(
        context,
        f"spikeWaves: probe Device {probe_name!r} not found; creating minimal Device "
        "(spikeTimes should register the shared probe first when both modalities present)",
    )
    nwbfile.create_device(name=probe_name, description=f"Probe for {SPIKE_WAVES_ID}")


def _load_snippet_timestamps(
    session_dir: Path,
    dataset_dir: Path,
    session_record: Dict[str, str],
) -> Optional[np.ndarray]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeWaves_timestamps.{mat|npz}",
        session_record,
        datatype_id=SPIKE_WAVES_ID,
    )
    if resolved is None:
        return None
    return np.asarray(load_numeric_array(resolved.path), dtype=float).ravel()


def _load_metadata_rows(
    session_dir: Path,
    dataset_dir: Path,
    session_record: Dict[str, str],
) -> List[Dict[str, str]]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeWaves_metadata.csv",
        session_record,
        datatype_id=SPIKE_WAVES_ID,
    )
    if resolved is None:
        return []
    return [dict(row) for row in read_csv_rows(resolved.path)]


def _load_schema(session_dir: Path, dataset_dir: Path, session_record: Dict[str, str]) -> Dict[str, object]:
    resolved = resolve_session_file(
        session_dir,
        dataset_dir,
        "spikeWaves_schema.json",
        session_record,
        datatype_id=SPIKE_WAVES_ID,
    )
    if resolved is None:
        return {}
    return normalize_schema_keys(load_json(resolved.path))


def _resolve_scalars(context: PlacementContext, schema: Dict[str, object]) -> Dict[str, object]:
    resolved: Dict[str, object] = {}
    for field_name in sorted(CORE_SCALAR_FIELDS.union(LABMETA_SCALAR_FIELDS)):
        session_key = f"{SPIKE_WAVES_ID}_{field_name}"
        session_value = context.session_record.get(session_key, "")
        schema_value = schema.get(field_name, "")

        session_present = field_non_empty(session_value)
        schema_present = field_non_empty(schema_value)

        if session_present and schema_present:
            left = str(session_value).strip()
            right = str(schema_value).strip()
            if left != right and not _numeric_equal(left, right):
                raise ValueError(
                    f"spikeWaves: sessionInfo {session_key}={left!r} disagrees with "
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
    snippet_timestamps: Optional[np.ndarray],
    unit_token: str,
) -> None:
    payload: Dict[str, object] = {}

    if field_non_empty(unit_token):
        payload["data_unit_measurement"] = unit_token

    for field_name in LABMETA_SCALAR_FIELDS:
        if field_name in scalars and field_non_empty(scalars[field_name]):
            payload[field_name] = scalars[field_name]

    if snippet_timestamps is not None and snippet_timestamps.size:
        payload["snippet_timestamps"] = snippet_timestamps.tolist()

    reserved = CORE_SCALAR_FIELDS.union(LABMETA_SCALAR_FIELDS).union(LAYOUT_FIELDS)
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
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return ""
    text = str(value).strip()
    if text in {"", "[]", "{}"}:
        return ""
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
