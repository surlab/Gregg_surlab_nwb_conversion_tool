"""Export NWB Units.waveforms to SurLab spikeWaves files."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional

from src.conversion_table import expand_rows_for_datatypes, is_informational_row, parse_stage
from src.data_io import save_json_file, save_numeric_array_npz
from src.nwb_table_reader import (
    SPIKE_WAVES_DATATYPE_ID,
    read_lab_meta_schema_fields,
    read_nwb_unit_values_for_row,
    read_nwb_value_for_row,
    read_spike_waves_arrays,
    units_has_waveforms,
)
from src.session_record import field_non_empty
from src.surlab_paths import resolve_filename_tokens

logger = logging.getLogger(__name__)


def export_spike_waves_from_nwb(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    table_rows: List[Dict[str, str]],
    dev_max_stage: int,
) -> List[Path]:
    """Write spikeWaves data, optional timestamps, metadata, and schema."""
    if not units_has_waveforms(nwbfile):
        logger.info("Skipping spikeWaves export: no units.waveforms column in NWB file.")
        return []

    data, snippet_timestamps = read_spike_waves_arrays(nwbfile)
    if data is None:
        logger.info("Skipping spikeWaves export: waveforms array empty.")
        return []

    stage_rows = [row for row in table_rows if parse_stage(row) <= dev_max_stage]
    spike_rows = _rows_for_datatype(stage_rows, SPIKE_WAVES_DATATYPE_ID)
    written: List[Path] = []

    data_path = _write_array_file(
        output_dir,
        dataset_id,
        session_record,
        role="data",
        array=data,
        array_key="data",
        pattern_token="spikeWaves_data.",
        stage_rows=spike_rows,
    )
    if data_path is not None:
        written.append(data_path)

    if snippet_timestamps is not None:
        ts_path = _write_array_file(
            output_dir,
            dataset_id,
            session_record,
            role="timestamps",
            array=snippet_timestamps,
            array_key="timestamps",
            pattern_token="spikeWaves_timestamps.",
            stage_rows=spike_rows,
        )
        if ts_path is not None:
            written.append(ts_path)

    metadata_path = _write_metadata_csv(nwbfile, output_dir, dataset_id, session_record, spike_rows)
    if metadata_path is not None:
        written.append(metadata_path)

    schema_path = _write_schema_json(
        nwbfile,
        output_dir,
        dataset_id,
        session_record,
        spike_rows,
        data=data,
        snippet_timestamps=snippet_timestamps,
    )
    if schema_path is not None:
        written.append(schema_path)

    return written


def _rows_for_datatype(stage_rows: List[Dict[str, str]], datatype_id: str) -> List[Dict[str, str]]:
    bound = expand_rows_for_datatypes(stage_rows, {datatype_id})
    rows = [row for row in bound if str(row.get("datatype_id", "")).strip() == datatype_id]
    if rows:
        return [row for row in rows if not is_informational_row(row)]
    prefix = f"{datatype_id}_"
    return [
        row
        for row in stage_rows
        if str(row.get("surlab_filename", "")).startswith(prefix) and not is_informational_row(row)
    ]


def _pattern_from_rows(stage_rows: List[Dict[str, str]], token: str) -> Optional[str]:
    for row in stage_rows:
        pattern = str(row.get("surlab_filename", "")).strip()
        if token in pattern:
            return pattern.replace("{mat|npz}", "npz")
    return None


def _verbose_basename(
    dataset_id: str,
    session_record: Dict[str, str],
    role: str,
    extension: str,
    pattern: Optional[str] = None,
) -> str:
    animal_id = session_record.get("animal_ID", "")
    session_id = session_record.get("session_ID", "")
    if animal_id and session_id:
        return f"spikeWaves_{role}_{dataset_id}_{animal_id}_{session_id}{extension}"
    if pattern:
        resolved = resolve_filename_tokens(pattern, dataset_id, session_record)
        for suffix in (".npz", ".mat", ".json", ".csv"):
            if resolved.endswith(suffix):
                return resolved[: -len(suffix)] + extension
        return resolved + extension
    return f"spikeWaves_{role}{extension}"


def _write_array_file(
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    role: str,
    array,
    array_key: str,
    pattern_token: str,
    stage_rows: List[Dict[str, str]],
) -> Optional[Path]:
    pattern = _pattern_from_rows(stage_rows, pattern_token)
    output_name = _verbose_basename(dataset_id, session_record, role, ".npz", pattern=pattern)
    output_path = output_dir / output_name
    save_numeric_array_npz(output_path, array, array_key=array_key)
    logger.info("Wrote spikeWaves %s: %s", role, output_path)
    return output_path


def _write_metadata_csv(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    stage_rows: List[Dict[str, str]],
) -> Optional[Path]:
    metadata_rows = [
        row for row in stage_rows if "spikeWaves_metadata.csv" in str(row.get("surlab_filename", ""))
    ]
    if not metadata_rows or nwbfile.units is None:
        return None

    unit_count = len(nwbfile.units)
    column_values: Dict[str, List[str]] = {}
    for row in metadata_rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if not field or field == "dataset_specific" or field.startswith("("):
            continue
        if field == "area":
            continue
        values = read_nwb_unit_values_for_row(nwbfile, row)
        if len(values) != unit_count:
            values = []
        if any(field_non_empty(value) for value in values):
            column_values[field] = values

    colnames = list(getattr(nwbfile.units, "colnames", []) or [])
    known = set(column_values.keys()) | {"unit_ID", "primary_channel", "id"}
    for column_name in colnames:
        if column_name in known or column_name in {"spike_times", "waveforms", "device", "brain_area", "area"}:
            continue
        values = [str(value).strip() for value in nwbfile.units[column_name][:]]
        if any(field_non_empty(value) for value in values):
            column_values[column_name] = values

    if not column_values:
        return None

    ordered = list(column_values.keys())
    csv_rows = []
    for unit_index in range(unit_count):
        csv_rows.append(
            {column: column_values[column][unit_index] for column in ordered}
        )

    pattern = _pattern_from_rows(stage_rows, "spikeWaves_metadata.csv")
    output_name = _verbose_basename(dataset_id, session_record, "metadata", ".csv", pattern=pattern)
    output_path = output_dir / output_name
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(csv_rows)
    logger.info("Wrote spikeWaves metadata: %s", output_path)
    return output_path


def _write_schema_json(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    stage_rows: List[Dict[str, str]],
    data,
    snippet_timestamps,
) -> Optional[Path]:
    schema_rows = [
        row for row in stage_rows if "spikeWaves_schema.json" in str(row.get("surlab_filename", ""))
    ]
    schema: Dict[str, object] = {}

    for row in schema_rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if not field or field == "dataset_specific" or field.startswith("("):
            continue
        nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
        if nwb_fieldname == "validate_only":
            continue
        value = read_nwb_value_for_row(nwbfile, row)
        if field_non_empty(value):
            schema[field] = _coerce_schema_value(value, str(row.get("nwb_type", "str")))

    lab_fields = read_lab_meta_schema_fields(nwbfile, SPIKE_WAVES_DATATYPE_ID)
    mapped_lab_keys = {
        str(row.get("nwb_fieldname", "")).strip()
        for row in schema_rows
        if "SurLabSchema" in str(row.get("nwb_location", ""))
    }
    for key, value in lab_fields.items():
        if key in mapped_lab_keys and key in schema:
            continue
        if key not in schema and field_non_empty(value):
            schema[key] = _coerce_schema_value(value, "str")

    if data is not None:
        schema.setdefault("X_dim", "waveform_sample")
        schema.setdefault("Y_dim", "unit")
        schema.setdefault("X_size", int(data.shape[0]))
        schema.setdefault("Y_size", int(data.shape[1]) if data.ndim > 1 else 1)
    if snippet_timestamps is not None:
        schema.setdefault(
            "X_idx",
            [float(value) for value in snippet_timestamps.ravel().tolist()],
        )

    if not schema:
        return None

    pattern = _pattern_from_rows(stage_rows, "spikeWaves_schema.json")
    output_name = _verbose_basename(dataset_id, session_record, "schema", ".json", pattern=pattern)
    output_path = output_dir / output_name
    save_json_file(output_path, schema)
    logger.info("Wrote spikeWaves schema: %s", output_path)
    return output_path


def _coerce_schema_value(value: str, nwb_type: str) -> object:
    nwb_type = nwb_type.strip().lower()
    if nwb_type in {"int", "integer"}:
        try:
            return int(float(value))
        except ValueError:
            return value
    if nwb_type == "float":
        try:
            return float(value)
        except ValueError:
            return value
    return value
