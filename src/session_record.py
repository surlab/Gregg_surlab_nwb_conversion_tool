"""Load and normalize SurLab sessionInfo records.

Legacy headers (animalID, sessID, sess_date, age, infoTrials) are normalized to
canonical names in memory when reading. The validator and table logic use only
canonical names; legacy matching is not a validation feature. On-disk CSVs are
not rewritten (round-trip canonicalization is Task 4 / Task 5 scope).
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


LEGACY_TO_CANONICAL_FIELD_MAP = {
    # Input-only aliases for older exports; see task2 doc section E.
    "animalID": "animal_ID",
    "sessID": "session_ID",
    "sess_date": "session_date",
    "age": "age__days",
    "infoTrials": "trialInfo",
}


def read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def normalize_session_record_keys(raw_record: Dict[str, str]) -> Dict[str, str]:
    """Map legacy sessionInfo headers to canonical names in memory only."""
    normalized = dict(raw_record)
    for legacy_name, canonical_name in LEGACY_TO_CANONICAL_FIELD_MAP.items():
        if canonical_name not in normalized and legacy_name in normalized:
            normalized[canonical_name] = normalized[legacy_name]
    return normalized


def field_non_empty(value: object) -> bool:
    if value is None:
        return False
    as_text = str(value).strip()
    return as_text != ""


def truthy_flag(value: object) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def find_session_info_csv(base_dir: Path, expected_name: str) -> Optional[Path]:
    expected_path = base_dir / expected_name
    if expected_path.exists():
        return expected_path
    for pattern in ("sessionInfo*.csv", "sessionsInfo*.csv", "*session*Info*.csv"):
        matches = sorted(base_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


# Tool/pipeline output dirs under dataset root — not SurLab session folders.
NON_SESSION_SUBDIR_NAMES = frozenset(
    {
        "roundtrip_surformat",
    }
)


def has_per_session_sessioninfo(session_dir: Path) -> bool:
    """True when session_dir holds a single-row sessionInfo CSV (per-session metadata)."""
    single_session = session_dir / "sessionInfo_single_session.csv"
    if single_session.exists():
        return len(read_csv_rows(single_session)) == 1

    for pattern in ("sessionsInfo*.csv", "sessionInfo*.csv"):
        for csv_path in sorted(session_dir.glob(pattern)):
            if len(read_csv_rows(csv_path)) == 1:
                return True
    return False


def discover_session_dirs(dataset_dir: Path) -> List[Path]:
    """List session subfolders under a dataset directory.

    Skips known pipeline output directories (e.g. roundtrip_surformat/) and any
    folder without a single-row per-session sessionInfo CSV on disk.
    """
    session_dirs: List[Path] = []
    for path in sorted(dataset_dir.iterdir()):
        if not path.is_dir():
            continue
        if path.name in NON_SESSION_SUBDIR_NAMES:
            continue
        if has_per_session_sessioninfo(path):
            session_dirs.append(path)
    return session_dirs


def load_session_record(dataset_dir: Path, session_dir: Path, dataset_id: str) -> Dict[str, str]:
    """Select one session row and return canonical field names."""
    session_local_info = find_session_info_csv(session_dir, "sessionInfo_single_session.csv")
    if session_local_info is not None:
        local_rows = read_csv_rows(session_local_info)
        if len(local_rows) == 1:
            return normalize_session_record_keys(local_rows[0])

    expected_dataset_file = f"sessionInfo_{dataset_id}.csv"
    dataset_info_path = find_session_info_csv(dataset_dir, expected_dataset_file)
    if dataset_info_path is None:
        raise FileNotFoundError("Could not find dataset sessionInfo CSV in dataset directory.")
    dataset_rows = read_csv_rows(dataset_info_path)
    if len(dataset_rows) == 1:
        return normalize_session_record_keys(dataset_rows[0])
    raise ValueError(
        "Could not select one session row. Provide sessionInfo_single_session.csv "
        "or reduce dataset-level sessionInfo to one row for this session."
    )


def derive_identifier(session_record: Dict[str, str]) -> str:
    animal_id = session_record.get("animal_ID", "").strip()
    session_id = session_record.get("session_ID", "").strip()
    if not animal_id or not session_id:
        raise ValueError("Cannot derive NWB identifier without non-empty animal_ID and session_ID.")
    return f"{animal_id}__{session_id}"


def parse_session_start_time(session_record: Dict[str, str], timezone_name: str = "UTC") -> datetime:
    raw_value = session_record.get("session_date", "").strip()
    if not raw_value:
        raise ValueError("session_date is required and must be non-empty.")
    parsed = None
    for date_format in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(raw_value, date_format)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ValueError(f"session_date '{raw_value}' is not parseable.")
    if timezone_name.upper() != "UTC":
        raise ValueError(f"Only UTC timezone policy is implemented; got {timezone_name!r}.")
    return parsed.replace(tzinfo=timezone.utc)


def normalize_age_days(age_days: str) -> Optional[str]:
    cleaned = age_days.strip()
    if cleaned.lower() in {"u", "unknown", "na", "n/a", "//"}:
        return None
    day_count = float(cleaned)
    if day_count < 0:
        raise ValueError("age__days cannot be negative.")
    if day_count.is_integer():
        return f"P{int(day_count)}D"
    return f"P{day_count}D"


def session_key(session_record: Dict[str, str]) -> str:
    animal_id = session_record.get("animal_ID", "unknown").strip() or "unknown"
    session_id = session_record.get("session_ID", "unknown").strip() or "unknown"
    return f"{animal_id}__{session_id}"


def nwb_output_basename(session_record: Dict[str, str]) -> str:
    """Return the default NWB filename stem: animal_ID_session_ID (no stage suffix)."""
    animal_id = session_record.get("animal_ID", "").strip()
    session_id = session_record.get("session_ID", "").strip()
    if not animal_id or not session_id:
        raise ValueError("Cannot derive NWB filename without non-empty animal_ID and session_ID.")
    return f"{animal_id}_{session_id}"
