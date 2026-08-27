"""Read and expand sur_nwb_conversion_table.csv rows for one session.

Rows are expanded dynamically for each ``<datatypeID>`` discovered on disk.
Informational rows (parenthetical field names, documentation-only file patterns)
are skipped automatically when the source does not exist — there is no
hardcoded skip list. ``stage`` in the table is for development tracking only.
"""

from __future__ import annotations

import csv
import copy
from pathlib import Path
from typing import Dict, List, Optional, Set


INFORMATIONAL_FIELD_PREFIX = "("
SKIP_NWB_FIELDNAMES = {
    "N/A",
    "same_as_dataset_dir_mapping",
}
SKIP_FILE_PATTERNS = {
    "(session_file_naming)",
    "(no file)",
}


def read_conversion_table(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def parse_stage(row: Dict[str, str]) -> int:
    try:
        return int(str(row.get("stage", "1")).strip())
    except ValueError:
        return 1


def filter_dev_stage(rows: List[Dict[str, str]], dev_max_stage: Optional[int]) -> List[Dict[str, str]]:
    if dev_max_stage is None:
        return list(rows)
    return [row for row in rows if parse_stage(row) <= dev_max_stage]


def is_informational_row(row: Dict[str, str]) -> bool:
    field_name = str(row.get("fieldname_surlab", "")).strip()
    nwb_field = str(row.get("nwb_fieldname", "")).strip()
    file_pattern = str(row.get("surlab_filename", "")).strip()
    if field_name in {"N/A", "NA", ""} and nwb_field in SKIP_NWB_FIELDNAMES.union({"N/A"}):
        return True
    if field_name.startswith(INFORMATIONAL_FIELD_PREFIX):
        return True
    if file_pattern in SKIP_FILE_PATTERNS:
        return True
    return False


def row_needs_datatype_expansion(row: Dict[str, str]) -> bool:
    joined = " ".join(
        str(row.get(key, ""))
        for key in ("surlab_filename", "requirement_condition", "notes", "fieldname_surlab")
    )
    return "<datatypeID>" in joined


def expand_rows_for_datatypes(rows: List[Dict[str, str]], discovered_datatypes: Set[str]) -> List[Dict[str, str]]:
    """Instantiate <datatypeID> template rows for each discovered stream datatype."""
    expanded: List[Dict[str, str]] = []
    for row in rows:
        if not row_needs_datatype_expansion(row):
            expanded.append(dict(row))
            continue
        for datatype_id in sorted(discovered_datatypes):
            if datatype_id in {"trialInfo", "spikeTimes", "lfp", "spikeWaves"}:
                continue
            if not _datatype_matches_template_row(row, datatype_id):
                continue
            expanded.append(_bind_datatype_row(row, datatype_id))
    return expanded


def _datatype_matches_template_row(row: Dict[str, str], datatype_id: str) -> bool:
    condition = str(row.get("requirement_condition", "")).strip()
    if condition == "if_datatype_present:<datatypeID>":
        return True
    stage = parse_stage(row)
    if datatype_id.endswith("_traces") and stage == 3:
        return True
    if datatype_id.endswith("_behTSeries") and stage == 4:
        return True
    if datatype_id.endswith("_behEvents"):
        return False
    return False


def _bind_datatype_row(row: Dict[str, str], datatype_id: str) -> Dict[str, str]:
    bound = copy.deepcopy(row)
    for key, value in bound.items():
        if isinstance(value, str):
            bound[key] = value.replace("<datatypeID>", datatype_id)
    bound["datatype_id"] = datatype_id
    return bound


def condition_datatype_id(condition: str) -> Optional[str]:
    condition = condition.strip()
    if not condition.startswith("if_datatype_present:"):
        return None
    token = condition.split(":", 1)[1].strip()
    if token == "<datatypeID>":
        return None
    return token


def row_applies_to_session(
    row: Dict[str, str],
    discovered_datatypes: Set[str],
    datatype_id: Optional[str] = None,
) -> bool:
    if is_informational_row(row):
        return False

    condition = str(row.get("requirement_condition", "always")).strip() or "always"
    if condition == "always":
        return True

    bound_datatype = datatype_id or str(row.get("datatype_id", "")).strip() or None
    condition_datatype = condition_datatype_id(condition)
    if condition_datatype is None and bound_datatype:
        return bound_datatype in discovered_datatypes
    if condition_datatype is None:
        return False
    return condition_datatype in discovered_datatypes


def known_sessioninfo_fieldnames(rows: List[Dict[str, str]]) -> List[str]:
    known: Set[str] = set()
    for row in rows:
        if is_informational_row(row):
            continue
        filename = str(row.get("surlab_filename", "")).lower()
        if "sessioninfo" not in filename and filename != "experimentdesc.pdf":
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        if not field_name or field_name == "dataset_specific":
            continue
        known.add(field_name)
    return sorted(known)
