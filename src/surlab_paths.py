"""Resolve SurLab filenames and discover session datatypes from files on disk.

File presence in the session directory is the authoritative signal for which
datatypes exist (e.g. ``spikeTimes_data*.mat`` -> ``spikeTimes``). Filename
resolution tries the minimal canonical name first, then verbose aliases via
``<stem>*.<ext>`` glob. Shared by forward conversion and discovery validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


DATA_FILE_ROLE_SUFFIX = "_data"
TIMESTAMPS_FILE_ROLE_SUFFIX = "_timestamps"
SCHEMA_FILE_ROLE_SUFFIX = "_schema"
METADATA_FILE_ROLE_SUFFIX = "_metadata"

TRIAL_INFO_STEM = "trialInfo"


@dataclass(frozen=True)
class ResolvedSurLabFile:
    """One concrete file matched from a table filename pattern."""

    path: Path
    pattern: str
    datatype_id: Optional[str] = None


def dataset_id_from_dir(dataset_dir: Path) -> str:
    return dataset_dir.name


def resolve_filename_tokens(pattern: str, dataset_id: str, session_record: Dict[str, str]) -> str:
    resolved = pattern.replace("<datasetID>", dataset_id)
    for token_key in ("animal_ID", "session_ID"):
        resolved = resolved.replace(f"<{token_key}>", session_record.get(token_key, ""))
    return resolved


def _brace_alternatives(pattern: str) -> List[str]:
    match = re.search(r"\{([^}]+)\}", pattern)
    if not match:
        return [pattern]
    options = match.group(1).split("|")
    return [pattern.replace(match.group(0), option) for option in options]


def _datatype_from_data_stem(stem: str) -> Optional[str]:
    if stem.endswith(DATA_FILE_ROLE_SUFFIX):
        return stem[: -len(DATA_FILE_ROLE_SUFFIX)]
    return None


def _datatype_from_role_stem(stem: str, role_suffix: str) -> Optional[str]:
    if stem.endswith(role_suffix):
        return stem[: -len(role_suffix)]
    return None


def _strip_verbose_session_suffix(stem: str, dataset_id: str, session_record: Dict[str, str]) -> str:
    animal_id = session_record.get("animal_ID", "")
    session_id = session_record.get("session_ID", "")
    verbose_suffix = f"_{dataset_id}_{animal_id}_{session_id}"
    if stem.endswith(verbose_suffix):
        return stem[: -len(verbose_suffix)]
    return stem


def discover_datatypes_from_files(session_dir: Path, dataset_id: str, session_record: Dict[str, str]) -> Set[str]:
    """Infer present datatypes from filenames; file presence is authoritative."""
    found: Set[str] = set()
    if not session_dir.is_dir():
        return found

    for path in session_dir.iterdir():
        if not path.is_file():
            continue
        stem = path.stem

        if stem == TRIAL_INFO_STEM or stem.startswith(f"{TRIAL_INFO_STEM}_"):
            found.add(TRIAL_INFO_STEM)
            continue

        for role_suffix in (
            DATA_FILE_ROLE_SUFFIX,
            TIMESTAMPS_FILE_ROLE_SUFFIX,
            SCHEMA_FILE_ROLE_SUFFIX,
            METADATA_FILE_ROLE_SUFFIX,
        ):
            if role_suffix in stem:
                datatype_id = stem.split(role_suffix, 1)[0]
                if datatype_id:
                    found.add(datatype_id)
                break

    return found


def resolve_session_file(
    session_dir: Path,
    dataset_dir: Path,
    filename_pattern: str,
    session_record: Dict[str, str],
    datatype_id: Optional[str] = None,
) -> Optional[ResolvedSurLabFile]:
    """Resolve one session file: minimal name first, then verbose alias glob."""
    dataset_id = dataset_id_from_dir(dataset_dir)
    pattern = resolve_filename_tokens(filename_pattern, dataset_id, session_record)
    if datatype_id:
        pattern = pattern.replace("<datatypeID>", datatype_id)

    for candidate_pattern in _brace_alternatives(pattern):
        if candidate_pattern.startswith("("):
            return None

        candidate_path = session_dir / candidate_pattern
        if candidate_path.exists():
            return ResolvedSurLabFile(path=candidate_path, pattern=filename_pattern, datatype_id=datatype_id)

        path_obj = Path(candidate_pattern)
        if path_obj.suffix:
            verbose_glob = f"{path_obj.stem}*{path_obj.suffix}"
            matches = sorted(session_dir.glob(verbose_glob))
            if matches:
                return ResolvedSurLabFile(path=matches[0], pattern=filename_pattern, datatype_id=datatype_id)

        matches = sorted(session_dir.glob(candidate_pattern))
        if matches:
            return ResolvedSurLabFile(path=matches[0], pattern=filename_pattern, datatype_id=datatype_id)

    return None


def resolve_dataset_file(
    dataset_dir: Path,
    filename_pattern: str,
    session_record: Dict[str, str],
) -> Optional[ResolvedSurLabFile]:
    dataset_id = dataset_id_from_dir(dataset_dir)
    pattern = resolve_filename_tokens(filename_pattern, dataset_id, session_record)
    if pattern.startswith("("):
        return None

    candidate_path = dataset_dir / pattern
    if candidate_path.exists():
        return ResolvedSurLabFile(path=candidate_path, pattern=filename_pattern)

    if "sessionInfo" in pattern:
        for glob_pattern in ("sessionInfo*.csv", "sessionsInfo*.csv", "*session*Info*.csv"):
            matches = sorted(dataset_dir.glob(glob_pattern))
            if matches:
                return ResolvedSurLabFile(path=matches[0], pattern=filename_pattern)

    matches = sorted(dataset_dir.glob(pattern))
    if matches:
        return ResolvedSurLabFile(path=matches[0], pattern=filename_pattern)
    return None


def resolve_row_source_file(
    row: Dict[str, str],
    dataset_dir: Path,
    session_dir: Path,
    session_record: Dict[str, str],
    datatype_id: Optional[str] = None,
) -> Optional[ResolvedSurLabFile]:
    location = str(row.get("surlab_file_location", "")).strip()
    file_pattern = str(row.get("surlab_filename", "")).strip()
    if location == "dataset_dir":
        return resolve_dataset_file(dataset_dir, file_pattern, session_record)
    return resolve_session_file(session_dir, dataset_dir, file_pattern, session_record, datatype_id=datatype_id)


def datatype_ids_referenced_in_table(rows: Iterable[Dict[str, str]]) -> Set[str]:
    referenced: Set[str] = set()
    for row in rows:
        condition = str(row.get("requirement_condition", "")).strip()
        if condition.startswith("if_datatype_present:"):
            token = condition.split(":", 1)[1].strip()
            if token != "<datatypeID>":
                referenced.add(token)
        for token in ("surlab_filename", "fieldname_surlab", "notes"):
            text = str(row.get(token, ""))
            if "<datatypeID>" in text:
                referenced.add("<datatypeID>")
                break
    return referenced
