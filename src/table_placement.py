"""Map conversion table targets onto PyNWB objects.

Placement reads ``nwb_location`` and ``nwb_fieldname`` literally from the
table. ``zero_time`` (SurLab session clock) is stored as
``NWBFile.notes = 'SurLab zero_time=<datatypeID>'`` — NWB has no global zero_time
field; timestamps in each stream are already relative to that origin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.conversion_table import is_informational_row, known_sessioninfo_fieldnames
from src.nwb_keyword_map import build_keyword_list, is_keyword_sessioninfo_column, load_keyword_rules
from src.session_record import (
    derive_identifier,
    field_non_empty,
    normalize_age_days,
    parse_session_start_time,
    truthy_flag,
)

logger = logging.getLogger(__name__)

ZERO_TIME_NOTES_PREFIX = "SurLab zero_time="
# Round-trip encoding for session clock reference stream (see task2 doc section E).


@dataclass
class PlacementContext:
    """Runtime state while applying table rows to one NWB file."""

    session_record: Dict[str, str]
    table_rows: List[Dict[str, str]]
    table_gaps: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def record_table_gap(context: PlacementContext, message: str) -> None:
    context.table_gaps.append(message)
    logger.warning("Table gap: %s", message)


def record_warning(context: PlacementContext, message: str) -> None:
    context.warnings.append(message)
    logger.warning(message)


def parse_nwb_target(nwb_location: str, nwb_fieldname: str) -> Tuple[str, str]:
    location = nwb_location.strip()
    attribute = nwb_fieldname.strip()
    if location == "NWBFile":
        return "file", attribute
    if location.startswith("NWBFile/general/subject"):
        return "subject", attribute
    if location.startswith("NWBFile/"):
        container = location.split("/", 1)[1]
        return container.lower(), attribute
    return location, attribute


def coerce_scalar(value: str, nwb_type: str):
    cleaned = value.strip()
    type_key = nwb_type.strip().lower().replace("64", "").replace("32", "")
    if type_key == "datetime":
        return parse_session_start_time({"session_date": cleaned})
    if type_key in {"int", "integer"}:
        return int(float(cleaned))
    if type_key in {"float", "float64"}:
        return float(cleaned)
    if type_key == "bool":
        return truthy_flag(cleaned)
    return cleaned


def collect_dataset_specific_session_fields(
    session_record: Dict[str, str],
    table_rows: List[Dict[str, str]],
) -> Dict[str, str]:
    known_fields = set(known_sessioninfo_fieldnames(table_rows))
    extras: Dict[str, str] = {}
    for key, value in session_record.items():
        if key in known_fields:
            continue
        if key.endswith("_traces") or key.endswith("_behTSeries"):
            continue
        if field_non_empty(value):
            extras[key] = str(value).strip()
    return extras


def format_experiment_description(extras: Dict[str, str]) -> str:
    if not extras:
        return ""
    return "; ".join(f"{key}={value}" for key, value in sorted(extras.items()))


def format_zero_time_notes(stream_id: str) -> str:
    return f"{ZERO_TIME_NOTES_PREFIX}{stream_id}"


def create_nwbfile_from_table(context: PlacementContext, timezone_name: str = "UTC"):
    from pynwb import NWBFile
    from pynwb.file import Subject

    session_record = context.session_record
    keyword_rules = load_keyword_rules(context.table_rows)
    required_description = session_record.get("condition", "").strip() or "No session description provided."
    identifier = derive_identifier(session_record)
    session_start_time = parse_session_start_time(session_record, timezone_name=timezone_name)

    nwbfile = NWBFile(
        session_description=required_description,
        identifier=identifier,
        session_start_time=session_start_time,
    )
    subject_fields: Dict[str, object] = {}
    experiment_description_parts: List[str] = []
    constructor_fields = {"session_description", "identifier", "session_start_time"}

    for row in context.table_rows:
        if is_informational_row(row):
            continue
        filename = str(row.get("surlab_filename", "")).lower()
        if "sessioninfo" not in filename:
            continue

        field_name = str(row.get("fieldname_surlab", "")).strip()
        nwb_location = str(row.get("nwb_location", "")).strip()
        nwb_fieldname = str(row.get("nwb_fieldname", "")).strip()
        nwb_type = str(row.get("nwb_type", "str")).strip()

        if field_name == "dataset_specific":
            extras = collect_dataset_specific_session_fields(session_record, context.table_rows)
            text = format_experiment_description(extras)
            if text:
                experiment_description_parts.append(text)
            continue

        if field_name == "(derived_file_identifier)":
            continue

        if field_name == "zero_time":
            stream_id = str(session_record.get("zero_time", "")).strip()
            if stream_id:
                _set_target(
                    nwbfile,
                    subject_fields,
                    nwb_location,
                    nwb_fieldname,
                    format_zero_time_notes(stream_id),
                    nwb_type,
                )
            continue

        if field_name in {"condition"}:
            continue

        if nwb_fieldname in constructor_fields:
            continue

        raw_value = session_record.get(field_name, "")
        if not field_non_empty(raw_value):
            continue

        if field_name == "age__days":
            converted = normalize_age_days(str(raw_value))
            if converted is None:
                continue
            _set_target(nwbfile, subject_fields, nwb_location, nwb_fieldname, converted, nwb_type)
            continue

        if is_keyword_sessioninfo_column(field_name, keyword_rules):
            continue

        converted = coerce_scalar(str(raw_value), nwb_type)
        _set_target(nwbfile, subject_fields, nwb_location, nwb_fieldname, converted, nwb_type)

    keywords = build_keyword_list(session_record, context.table_rows)
    if keywords:
        nwbfile.keywords = keywords

    if experiment_description_parts:
        existing = str(getattr(nwbfile, "experiment_description", "") or "").strip()
        merged = "; ".join(experiment_description_parts)
        nwbfile.experiment_description = f"{existing}; {merged}".strip("; ").strip() if existing else merged

    if subject_fields:
        nwbfile.subject = Subject(**subject_fields)

    return nwbfile


def _set_target(
    nwbfile,
    subject_fields: Dict[str, object],
    nwb_location: str,
    nwb_fieldname: str,
    value: object,
    nwb_type: str,
) -> None:
    container, attribute = parse_nwb_target(nwb_location, nwb_fieldname)
    if container == "file":
        if attribute == "related_publications" and not isinstance(value, (list, tuple)):
            setattr(nwbfile, attribute, [str(value)])
        elif attribute == "experimenter" and not isinstance(value, (list, tuple)):
            setattr(nwbfile, attribute, str(value))
        else:
            setattr(nwbfile, attribute, value)
        return
    if container == "subject":
        if attribute == "age" and nwb_type == "str":
            subject_fields[attribute] = str(value)
        else:
            subject_fields[attribute] = value
        return
    raise ValueError(f"No placement handler for target {nwb_location}/{nwb_fieldname}")
