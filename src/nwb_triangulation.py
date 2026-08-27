"""Table-driven NWB reads for Task 5 round-trip triangulation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

from src.data_io import load_spike_times_by_unit
from src.nwb_table_reader import read_nwb_triangulation_value
from src.session_record import nwb_output_basename, normalize_age_days

ZERO_TIME_PREFIX = "SurLab zero_time="

OWNER_TASK2_FORWARD = "task2_forward"
OWNER_TASK4_REVERSE = "task4_reverse"
OWNER_BOTH_OR_TABLE = "both_or_table_gap"
OWNER_DATA_OR_SPEC = "data_or_spec"
OWNER_TASK4_NOT_EXPORTED = "task4_not_exported"
OWNER_NWB_UNREADABLE = "nwb_check_failed"


def find_session_nwb(session_dir: Path, session_record: Dict[str, str]) -> Optional[Path]:
    """Pick the canonical session NWB (exclude legacy stage-suffixed files when possible)."""
    preferred = session_dir / f"{nwb_output_basename(session_record)}.nwb"
    if preferred.exists():
        return preferred
    candidates = sorted(
        path
        for path in session_dir.glob("*.nwb")
        if not re.search(r"_stage\d+$", path.stem)
    )
    if candidates:
        return candidates[-1]
    legacy = sorted(session_dir.glob("*.nwb"))
    return legacy[-1] if legacy else None


def read_nwb_value_for_row(nwbfile, row: Dict[str, str]) -> Tuple[Optional[str], str]:
    """Return (scalar_or_none, note) for one conversion-table row from an open NWB file."""
    return read_nwb_triangulation_value(nwbfile, row)


def load_nwb_file(nwb_path: Path):
    from pynwb import NWBHDF5IO

    io_handle = NWBHDF5IO(str(nwb_path), mode="r", load_namespaces=True)
    return io_handle, io_handle.read()


def _safe_join_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, np.ndarray)):
        parts = [str(part).strip() for part in value if str(part).strip() != ""]
        return ",".join(parts)
    return str(value).strip()


def normalize_for_triangulation(field_name: str, value: object) -> str:
    if value is None:
        return ""
    text = _safe_join_text(value)
    if field_name == "age__days":
        if text.startswith("P") and text.endswith("D"):
            return text[1:-1]
        try:
            iso = normalize_age_days(text)
            if iso:
                return iso[1:-1] if iso.startswith("P") and iso.endswith("D") else iso
        except ValueError:
            return text
    if field_name == "session_date" and "T" in text:
        return text.split("T", 1)[0]
    if text.endswith(".0") and text.replace(".", "", 1).isdigit():
        return text[:-2]
    if text.lower() in {"true", "yes"}:
        return "1"
    if text.lower() in {"false", "no"}:
        return "0"
    return text


def values_equivalent_for_triangulation(field_name: str, left: object, right: object) -> bool:
    return normalize_for_triangulation(field_name, left) == normalize_for_triangulation(field_name, right)


def attribute_roundtrip_issue(
    status: str,
    field_name: str,
    original_value: object,
    nwb_value: object,
    roundtrip_value: object,
    nwb_note: str = "",
) -> str:
    """Assign likely owner using original / NWB / roundtrip witness pattern."""
    if status == "skipped_roundtrip_missing":
        return OWNER_TASK4_NOT_EXPORTED
    if status != "mismatch":
        return ""

    if field_name == "age__days" and normalize_for_triangulation(field_name, original_value) in {"", "U", "UNKNOWN"}:
        return OWNER_DATA_OR_SPEC

    original_norm = normalize_for_triangulation(field_name, original_value)
    nwb_norm = normalize_for_triangulation(field_name, nwb_value)
    roundtrip_norm = normalize_for_triangulation(field_name, roundtrip_value)
    original_empty = original_norm == ""
    nwb_empty = nwb_norm == ""
    roundtrip_empty = roundtrip_norm == ""

    if nwb_note in {"units column missing", "units missing", "device", "processing"} and nwb_empty:
        if not original_empty and roundtrip_empty:
            return OWNER_TASK2_FORWARD
        if not original_empty and not roundtrip_empty:
            return OWNER_TASK4_REVERSE

    if not original_empty and not nwb_empty and not roundtrip_empty:
        if values_equivalent_for_triangulation(field_name, original_value, nwb_value) and not values_equivalent_for_triangulation(
            field_name, nwb_value, roundtrip_value
        ):
            return OWNER_TASK4_REVERSE
        if not values_equivalent_for_triangulation(field_name, original_value, nwb_value) and values_equivalent_for_triangulation(
            field_name, nwb_value, roundtrip_value
        ):
            return OWNER_TASK2_FORWARD
        return OWNER_BOTH_OR_TABLE

    if not original_empty and nwb_empty and roundtrip_empty:
        return OWNER_TASK2_FORWARD
    if not original_empty and not nwb_empty and roundtrip_empty:
        return OWNER_TASK4_REVERSE
    if original_empty and not roundtrip_empty:
        return OWNER_TASK4_REVERSE
    if original_empty and not nwb_empty:
        return OWNER_TASK2_FORWARD
    if not original_empty and nwb_empty and not roundtrip_empty:
        return OWNER_BOTH_OR_TABLE
    return OWNER_BOTH_OR_TABLE


def spike_times_match_in_nwb(nwbfile, original_path: Path, rtol: float, atol: float) -> Tuple[bool, str]:
    if nwbfile.units is None:
        return False, "units missing"
    nwb_series = [np.asarray(values, dtype=float).ravel() for values in nwbfile.units["spike_times"]]
    original_series = load_spike_times_by_unit(original_path)
    if len(nwb_series) != len(original_series):
        return False, f"unit_count {len(original_series)} vs {len(nwb_series)}"
    for index, (left, right) in enumerate(zip(original_series, nwb_series)):
        if not np.allclose(left, right, rtol=rtol, atol=atol, equal_nan=True):
            return False, f"unit {index} spike_times differ"
    return True, f"{len(original_series)} units match"
