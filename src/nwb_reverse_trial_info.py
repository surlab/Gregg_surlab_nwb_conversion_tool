"""Export NWB Trials (TimeIntervals) to SurLab trialInfo.csv.

Column mapping is driven by conversion-table rows with
``nwb_location`` under ``NWBFile/intervals/trials``. Extra Trials columns
not listed in the table are written as dataset_specific fields.
"""

from __future__ import annotations

import csv
import logging
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.conversion_table import is_informational_row, parse_stage
from src.session_record import field_non_empty
from src.surlab_paths import resolve_filename_tokens

logger = logging.getLogger(__name__)

# Built-in NWB Trials columns that are not SurLab trialInfo fields.
_SKIP_NWB_COLUMNS = {"id"}


def export_trial_info_from_nwb(
    nwbfile,
    output_dir: Path,
    dataset_id: str,
    session_record: Dict[str, str],
    table_rows: List[Dict[str, str]],
    dev_max_stage: int,
) -> List[Path]:
    """Write trialInfo CSV under output_dir. Returns written paths."""
    if nwbfile.trials is None or len(nwbfile.trials) == 0:
        logger.info("Skipping trialInfo export: no trials in NWB file.")
        return []

    stage_rows = [row for row in table_rows if parse_stage(row) <= dev_max_stage]
    field_map = _trial_field_map_from_table(stage_rows)
    if not field_map:
        logger.warning("Skipping trialInfo export: no intervals/trials rows in conversion table.")
        return []

    pattern = _trialinfo_filename_pattern(stage_rows)
    if pattern is None:
        logger.warning("Skipping trialInfo export: no trialInfo.csv pattern in conversion table.")
        return []

    nwb_to_surlab = {spec["nwb_column"]: field_name for field_name, spec in field_map.items()}
    known_nwb = set(nwb_to_surlab.keys())
    trials = nwbfile.trials
    trial_colnames = list(trials.colnames)

    ordered_surlab = [name for name in _table_field_order(stage_rows) if name in field_map]
    extras = [
        name
        for name in trial_colnames
        if name not in known_nwb and name not in _SKIP_NWB_COLUMNS
    ]

    headers = ordered_surlab + extras
    csv_rows: List[Dict[str, str]] = []
    for trial_index in range(len(trials)):
        row: Dict[str, str] = {}
        for field_name in ordered_surlab:
            nwb_column = field_map[field_name]["nwb_column"]
            nwb_type = field_map[field_name]["nwb_type"]
            if nwb_column not in trial_colnames:
                row[field_name] = ""
                continue
            raw = trials[nwb_column][trial_index]
            row[field_name] = _format_trial_cell(raw, nwb_type)
        for extra_name in extras:
            raw = trials[extra_name][trial_index]
            row[extra_name] = _format_trial_cell(raw, "str")
        csv_rows.append(row)

    # Drop columns that are entirely empty (optional fields never written forward).
    headers = [name for name in headers if any(field_non_empty(row.get(name, "")) for row in csv_rows)]
    if not headers:
        logger.warning("Skipping trialInfo export: all trial columns empty after formatting.")
        return []

    output_name = _verbose_trialinfo_name(pattern, dataset_id, session_record)
    output_path = output_dir / output_name
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in csv_rows:
            writer.writerow({header: row.get(header, "") for header in headers})

    logger.info("Wrote trialInfo (%d trials): %s", len(csv_rows), output_path)
    return [output_path]


def _trial_field_map_from_table(table_rows: Sequence[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    """Map SurLab fieldname -> {nwb_column, nwb_type}."""
    field_map: Dict[str, Dict[str, str]] = {}
    for row in table_rows:
        location = str(row.get("nwb_location", "")).strip()
        if "intervals/trials" not in location:
            continue
        if is_informational_row(row):
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if not field_name or field_name == "dataset_specific" or field_name.startswith("("):
            continue
        nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
        if not nwb_fieldname or nwb_fieldname == "custom_columns":
            continue
        nwb_column = nwb_fieldname
        if nwb_column.startswith("custom_column_"):
            nwb_column = nwb_column[len("custom_column_") :]
        field_map[field_name] = {
            "nwb_column": nwb_column,
            "nwb_type": str(row.get("nwb_type", "str")).strip() or "str",
        }
    return field_map


def _table_field_order(table_rows: Sequence[Dict[str, str]]) -> List[str]:
    ordered: List[str] = []
    seen = set()
    for row in table_rows:
        location = str(row.get("nwb_location", "")).strip()
        if "intervals/trials" not in location:
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if not field_name or field_name == "dataset_specific" or field_name.startswith("("):
            continue
        if field_name in seen:
            continue
        seen.add(field_name)
        ordered.append(field_name)
    return ordered


def _trialinfo_filename_pattern(table_rows: Sequence[Dict[str, str]]) -> Optional[str]:
    for row in table_rows:
        if is_informational_row(row):
            continue
        pattern = str(row.get("surlab_filename", "")).strip()
        if pattern == "trialInfo.csv" or pattern.startswith("trialInfo"):
            return pattern
    return None


def _verbose_trialinfo_name(
    pattern: str,
    dataset_id: str,
    session_record: Dict[str, str],
) -> str:
    animal_id = session_record.get("animal_ID", "")
    session_id = session_record.get("session_ID", "")
    if animal_id and session_id:
        return f"trialInfo_{dataset_id}_{animal_id}_{session_id}.csv"
    resolved = resolve_filename_tokens(pattern, dataset_id, session_record)
    if not resolved.endswith(".csv"):
        return resolved + ".csv"
    return resolved


def _format_trial_cell(value: object, nwb_type: str) -> str:
    if value is None:
        return ""

    type_key = nwb_type.lower().replace("64", "").replace("32", "")

    if isinstance(value, (float, int)) or hasattr(value, "item"):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None:
            if math.isnan(numeric):
                return "NaN"
            if type_key in {"int", "integer"} or (
                type_key in {"float", "float64"} and numeric.is_integer()
            ):
                return str(int(numeric))
            if type_key == "bool":
                return "1" if numeric else "0"
            text = format(numeric, ".12g")
            return text

    if isinstance(value, bool):
        return "1" if value else "0"

    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return "NaN" if text.lower() == "nan" else ""
    return text
