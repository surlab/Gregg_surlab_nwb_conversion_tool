"""Export NWB acquisition TimeSeries (behTSeries) to SurLab stream files."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from src.conversion_table import (
    expand_rows_for_datatypes,
    is_informational_row,
    parse_stage,
)
from src.data_io import save_json_file, save_numeric_array_npz
from src.nwb_table_reader import (
    discover_beh_tseries_datatypes,
    find_behavior_features_table,
    read_acquisition_timeseries_arrays,
    read_lab_meta_schema_fields,
    read_nwb_feature_values_for_row,
    read_nwb_value_for_row,
)
from src.session_record import field_non_empty
from src.surlab_paths import resolve_filename_tokens

logger = logging.getLogger(__name__)

FEATURE_TABLE_COLUMNS = ("feature_ID", "feature_label")


def export_beh_tseries_from_nwb(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    table_rows: List[Dict[str, str]],
    dev_max_stage: int,
    present_datatypes: Optional[Set[str]] = None,
) -> List[Path]:
    """Write data/timestamps/metadata/schema for each ``*_behTSeries`` stream."""
    stage_rows = [row for row in table_rows if parse_stage(row) <= dev_max_stage]
    stream_ids = _beh_tseries_stream_ids(nwbfile, present_datatypes)
    if not stream_ids:
        logger.info("Skipping behTSeries export: no *_behTSeries streams discovered.")
        return []

    written: List[Path] = []
    for datatype_id in stream_ids:
        written.extend(
            _export_one_beh_tseries_stream(
                nwbfile,
                output_dir,
                dataset_id,
                session_record,
                stage_rows,
                datatype_id,
            )
        )
    return written


def _beh_tseries_stream_ids(nwbfile, present_datatypes: Optional[Set[str]]) -> List[str]:
    discovered = discover_beh_tseries_datatypes(nwbfile)
    if present_datatypes:
        for datatype_id in sorted(present_datatypes):
            if datatype_id.endswith("_behTSeries") and datatype_id not in discovered:
                discovered.append(datatype_id)
    return sorted(set(discovered))


def _export_one_beh_tseries_stream(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    stage_rows: List[Dict[str, str]],
    datatype_id: str,
) -> List[Path]:
    bound_rows = expand_rows_for_datatypes(stage_rows, {datatype_id})
    stream_rows = [row for row in bound_rows if str(row.get("datatype_id", "")).strip() == datatype_id]
    if not stream_rows:
        stream_rows = bound_rows

    data, timestamps = read_acquisition_timeseries_arrays(nwbfile, datatype_id)
    if data is None:
        logger.warning("No acquisition TimeSeries named %s; skipping behTSeries stream.", datatype_id)
        return []

    written: List[Path] = []
    data_path = _write_array_file(
        output_dir,
        dataset_id,
        session_record,
        datatype_id,
        role="data",
        array=data,
        array_key="data",
        pattern_token="_data.",
        stream_rows=stream_rows,
    )
    if data_path is not None:
        written.append(data_path)

    if timestamps is not None:
        ts_path = _write_array_file(
            output_dir,
            dataset_id,
            session_record,
            datatype_id,
            role="timestamps",
            array=timestamps,
            array_key="timestamps",
            pattern_token="_timestamps.",
            stream_rows=stream_rows,
        )
        if ts_path is not None:
            written.append(ts_path)

    metadata_path = _write_metadata_csv(
        nwbfile,
        output_dir,
        dataset_id,
        session_record,
        datatype_id,
        stream_rows,
    )
    if metadata_path is not None:
        written.append(metadata_path)

    schema_path = _write_schema_json(
        nwbfile,
        output_dir,
        dataset_id,
        session_record,
        datatype_id,
        stream_rows,
        data=data,
        timestamps=timestamps,
        metadata_path=metadata_path,
    )
    if schema_path is not None:
        written.append(schema_path)

    return written


def _rows_for_filename(stream_rows: Sequence[Dict[str, str]], token: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in stream_rows:
        if is_informational_row(row):
            continue
        if token in str(row.get("surlab_filename", "")):
            rows.append(row)
    return rows


def _pattern_from_rows(stream_rows: Sequence[Dict[str, str]], token: str) -> Optional[str]:
    for row in stream_rows:
        pattern = str(row.get("surlab_filename", "")).strip()
        if token in pattern:
            return pattern.replace("{mat|npz}", "npz")
    return None


def _verbose_stream_name(
    dataset_id: str,
    session_record: Dict[str, str],
    datatype_id: str,
    role: str,
    extension: str,
    pattern: Optional[str] = None,
) -> str:
    animal_id = session_record.get("animal_ID", "")
    session_id = session_record.get("session_ID", "")
    if animal_id and session_id:
        return f"{datatype_id}_{role}_{dataset_id}_{animal_id}_{session_id}{extension}"
    if pattern:
        resolved = resolve_filename_tokens(pattern, dataset_id, session_record)
        resolved = resolved.replace("<datatypeID>", datatype_id)
        if not resolved.endswith(extension):
            for suffix in (".npz", ".mat", ".json", ".csv"):
                if resolved.endswith(suffix):
                    resolved = resolved[: -len(suffix)]
                    break
            resolved = resolved + extension
        return resolved
    return f"{datatype_id}_{role}{extension}"


def _write_array_file(
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    datatype_id: str,
    role: str,
    array,
    array_key: str,
    pattern_token: str,
    stream_rows: Sequence[Dict[str, str]],
) -> Optional[Path]:
    pattern = _pattern_from_rows(stream_rows, pattern_token)
    output_name = _verbose_stream_name(
        dataset_id,
        session_record,
        datatype_id,
        role,
        ".npz",
        pattern=pattern,
    )
    output_path = output_dir / output_name
    save_numeric_array_npz(output_path, array, array_key=array_key)
    logger.info("Wrote behTSeries %s: %s", role, output_path)
    return output_path


def _write_metadata_csv(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    datatype_id: str,
    stream_rows: Sequence[Dict[str, str]],
) -> Optional[Path]:
    metadata_rows = _rows_for_filename(stream_rows, "_metadata.csv")
    features_table = find_behavior_features_table(nwbfile, datatype_id)
    if features_table is None:
        return None

    column_values: Dict[str, List[str]] = {}
    for row in metadata_rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if not field or field == "dataset_specific" or field.startswith("("):
            continue
        values = read_nwb_feature_values_for_row(nwbfile, row)
        if any(field_non_empty(value) for value in values):
            column_values[field] = values

    known_columns = set(column_values.keys())
    colnames = list(getattr(features_table, "colnames", []) or [])
    try:
        row_count = len(features_table)
    except TypeError:
        row_count = 0
    for column_name in colnames:
        if column_name in known_columns:
            continue
        if column_name in FEATURE_TABLE_COLUMNS:
            continue
        values = [str(value).strip() for value in features_table[column_name][:]]
        if any(field_non_empty(value) for value in values):
            column_values[column_name] = values

    if not column_values and row_count:
        for column_name in FEATURE_TABLE_COLUMNS:
            if column_name in colnames:
                column_values[column_name] = [
                    str(value).strip() for value in features_table[column_name][:]
                ]

    if not column_values:
        return None

    ordered: List[str] = []
    for row in metadata_rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if field in column_values and field not in ordered:
            ordered.append(field)
    for field in column_values:
        if field not in ordered:
            ordered.append(field)

    row_count = max(len(values) for values in column_values.values())
    csv_rows = []
    for index in range(row_count):
        csv_rows.append(
            {
                column: (column_values[column][index] if index < len(column_values[column]) else "")
                for column in ordered
            }
        )

    pattern = _pattern_from_rows(stream_rows, "_metadata.csv")
    output_name = _verbose_stream_name(
        dataset_id, session_record, datatype_id, "metadata", ".csv", pattern=pattern
    )
    output_path = output_dir / output_name
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(csv_rows)
    logger.info("Wrote behTSeries metadata: %s", output_path)
    return output_path


def _write_schema_json(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    datatype_id: str,
    stream_rows: Sequence[Dict[str, str]],
    data,
    timestamps,
    metadata_path: Optional[Path],
) -> Optional[Path]:
    schema_rows = _rows_for_filename(stream_rows, "_schema.json")
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

    lab_fields = read_lab_meta_schema_fields(nwbfile, datatype_id)
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
        schema.setdefault("X_dim", "time")
        schema.setdefault("Y_dim", "features")
        schema.setdefault("X_size", int(data.shape[0]))
        schema.setdefault("Y_size", int(data.shape[1]) if data.ndim > 1 else 1)
    if timestamps is not None:
        schema.setdefault("X_idx", [float(value) for value in timestamps.ravel().tolist()])
    if metadata_path is not None and metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8", newline="") as handle:
            meta_rows = list(csv.DictReader(handle))
        if meta_rows and "feature_ID" in meta_rows[0]:
            schema.setdefault("Y_idx", [row.get("feature_ID", "") for row in meta_rows])

    if not schema:
        return None

    pattern = _pattern_from_rows(stream_rows, "_schema.json")
    output_name = _verbose_stream_name(
        dataset_id, session_record, datatype_id, "schema", ".json", pattern=pattern
    )
    output_path = output_dir / output_name
    save_json_file(output_path, schema)
    logger.info("Wrote behTSeries schema: %s", output_path)
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
