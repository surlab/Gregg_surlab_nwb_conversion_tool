"""Export NWB Units table to SurLab spikeTimes files using sur_nwb_conversion_table.csv."""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional

from src.conversion_table import is_informational_row, parse_stage
from src.data_io import save_json_file, save_spike_times_npz
from src.nwb_table_reader import read_nwb_unit_values_for_row, read_nwb_value_for_row
from src.session_record import field_non_empty
from src.surlab_paths import resolve_filename_tokens

logger = logging.getLogger(__name__)


def export_spike_times_from_nwb(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    table_rows: List[Dict[str, str]],
    dev_max_stage: int,
) -> List[Path]:
    """Write spikeTimes data, metadata, and schema under output_dir."""
    if nwbfile.units is None or len(nwbfile.units) == 0:
        logger.info("Skipping spikeTimes export: no units in NWB file.")
        return []

    stage_rows = [row for row in table_rows if parse_stage(row) <= dev_max_stage]
    spike_series = _units_to_spike_series(nwbfile)
    written: List[Path] = []

    data_pattern = _row_filename_pattern(stage_rows, "spikeTimes_data.{mat|npz}")
    if data_pattern:
        data_name = _verbose_basename(data_pattern, dataset_id, session_record) + ".npz"
        data_path = output_dir / data_name
        save_spike_times_npz(data_path, spike_series)
        written.append(data_path)
        logger.info("Wrote spikeTimes data: %s", data_path)

    metadata_path = _write_metadata_csv(
        nwbfile,
        output_dir,
        dataset_id,
        session_record,
        stage_rows,
    )
    if metadata_path is not None:
        written.append(metadata_path)

    schema_path = _write_schema_json(
        nwbfile,
        output_dir,
        dataset_id,
        session_record,
        stage_rows,
    )
    if schema_path is not None:
        written.append(schema_path)

    return written


def _units_to_spike_series(nwbfile) -> List:
    import numpy as np

    series = []
    for unit_index in range(len(nwbfile.units)):
        spike_times = nwbfile.units["spike_times"][unit_index]
        series.append(np.asarray(spike_times, dtype=float).ravel())
    return series


def _rows_for_file(stage_rows: List[Dict[str, str]], filename_token: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in stage_rows:
        if filename_token not in str(row.get("surlab_filename", "")):
            continue
        if is_informational_row(row):
            continue
        rows.append(row)
    return rows


def _row_filename_pattern(rows: List[Dict[str, str]], contains: str) -> Optional[str]:
    for row in rows:
        if is_informational_row(row):
            continue
        pattern = str(row.get("surlab_filename", "")).strip()
        if contains in pattern:
            return pattern.replace("{mat|npz}", "npz")
    return None


def _verbose_basename(
    pattern: str,
    dataset_id: str,
    session_record: Dict[str, str],
    datatype_id: str = "spikeTimes",
    role: str = "data",
) -> str:
    animal_id = session_record.get("animal_ID", "")
    session_id = session_record.get("session_ID", "")
    if animal_id and session_id:
        return f"{datatype_id}_{role}_{dataset_id}_{animal_id}_{session_id}"
    resolved = resolve_filename_tokens(pattern, dataset_id, session_record)
    for suffix in (".npz", ".mat", ".json", ".csv"):
        if resolved.endswith(suffix):
            return resolved[: -len(suffix)]
    return resolved


def _write_metadata_csv(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    stage_rows: List[Dict[str, str]],
) -> Optional[Path]:
    pattern = _row_filename_pattern(stage_rows, "spikeTimes_metadata.csv")
    metadata_rows = _rows_for_file(stage_rows, "spikeTimes_metadata.csv")
    if pattern is None or not metadata_rows:
        return None

    unit_count = len(nwbfile.units)
    column_values: Dict[str, List[str]] = {}
    for row in metadata_rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if not field or field == "dataset_specific" or field.startswith("("):
            continue
        values = read_nwb_unit_values_for_row(nwbfile, row)
        if len(values) != unit_count:
            values = []
        if any(field_non_empty(value) for value in values):
            column_values[field] = values

    if not column_values:
        return None

    metadata_columns = list(column_values.keys())
    csv_rows: List[Dict[str, str]] = []
    for unit_index in range(unit_count):
        csv_rows.append(
            {column: column_values[column][unit_index] for column in metadata_columns}
        )

    output_name = _verbose_basename(pattern, dataset_id, session_record, role="metadata") + ".csv"
    output_path = output_dir / output_name
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=metadata_columns)
        writer.writeheader()
        writer.writerows(csv_rows)
    logger.info("Wrote spikeTimes metadata: %s", output_path)
    return output_path


def _write_schema_json(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    stage_rows: List[Dict[str, str]],
) -> Optional[Path]:
    pattern = _row_filename_pattern(stage_rows, "spikeTimes_schema.json")
    schema_rows = _rows_for_file(stage_rows, "spikeTimes_schema.json")
    if pattern is None or not schema_rows:
        return None

    schema: Dict[str, object] = {}
    for row in schema_rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if not field or field == "dataset_specific" or field.startswith("("):
            continue
        value = read_nwb_value_for_row(nwbfile, row)
        if field_non_empty(value):
            schema[field] = _coerce_schema_value(value, str(row.get("nwb_type", "str")))

    if not schema:
        return None

    output_name = _verbose_basename(pattern, dataset_id, session_record, role="schema") + ".json"
    output_path = output_dir / output_name
    save_json_file(output_path, schema)
    logger.info("Wrote spikeTimes schema: %s", output_path)
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
