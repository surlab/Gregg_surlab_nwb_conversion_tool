"""Load sessionInfo <-> NWB keyword rules from sur_nwb_conversion_table.csv ``nwb_keyword`` column."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


@dataclass
class KeywordRules:
    """Forward: sessionInfo column -> NWB keyword token."""

    fixed: Dict[str, str] = field(default_factory=dict)
    identity_suffixes: tuple[str, ...] = ()

    @property
    def keyword_to_column(self) -> Dict[str, str]:
        return {keyword: column for column, keyword in self.fixed.items()}

    def fixed_modality_columns(self) -> List[str]:
        return list(self.fixed.keys())


def is_keyword_sessioninfo_column(field_name: str, rules: KeywordRules) -> bool:
    if field_name in rules.fixed:
        return True
    return any(field_name.endswith(suffix) for suffix in rules.identity_suffixes)


def build_keyword_list(session_record: Dict[str, str], table_rows: List[Dict[str, str]]) -> List[str]:
    """Build NWBFile.keywords from sessionInfo boolean flags using table ``nwb_keyword`` rows."""
    from src.session_record import truthy_flag

    rules = load_keyword_rules(table_rows)
    keywords: List[str] = []

    for column_name, keyword_token in rules.fixed.items():
        if truthy_flag(session_record.get(column_name, "")):
            keywords.append(keyword_token)

    for column_name, value in session_record.items():
        if any(column_name.endswith(suffix) for suffix in rules.identity_suffixes):
            if truthy_flag(value):
                keywords.append(column_name)

    return sorted(set(keywords))


def load_keyword_rules(table_rows: List[Dict[str, str]]) -> KeywordRules:
    """Read keyword mapping from rows where ``nwb_fieldname`` is ``keywords``."""
    if not table_rows:
        logger.warning("No conversion table rows; keyword rules are empty.")
        return KeywordRules()

    if "nwb_keyword" not in table_rows[0]:
        logger.warning(
            "sur_nwb_conversion_table.csv has no nwb_keyword column; keyword rules are empty."
        )
        return KeywordRules()

    fixed: Dict[str, str] = {}
    identity_suffixes: List[str] = []
    for row in table_rows:
        if str(row.get("nwb_fieldname", "")).strip() != "keywords":
            continue
        field_name = str(row.get("fieldname_surlab", "")).strip()
        keyword_token = str(row.get("nwb_keyword", "")).strip()
        if keyword_token == "identity":
            lowered = field_name.lower()
            if "traces" in lowered:
                identity_suffixes.append("_traces")
            if "behtseries" in lowered:
                identity_suffixes.append("_behTSeries")
            continue
        if field_name.startswith("(") or not keyword_token:
            continue
        fixed[field_name] = keyword_token

    if not fixed and not identity_suffixes:
        logger.warning("No nwb_keyword rows found for NWBFile.keywords; keyword rules are empty.")

    return KeywordRules(fixed=fixed, identity_suffixes=tuple(dict.fromkeys(identity_suffixes)))


def keywords_from_nwb(nwbfile) -> List[str]:
    raw = getattr(nwbfile, "keywords", None)
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    if hasattr(raw, "__len__") and not isinstance(raw, (str, bytes)):
        try:
            return [str(item).strip() for item in raw if str(item).strip()]
        except TypeError:
            pass
    text = str(raw).strip()
    if text.startswith("<") and "Dataset" in text:
        return []
    return [text] if text else []


def apply_keywords_to_session_row(
    session_row: Dict[str, str],
    keywords: List[str],
    rules: KeywordRules,
    known_columns: Set[str],
) -> List[str]:
    """Set modality boolean columns from NWB keywords; return warning messages."""
    warnings: List[str] = []
    keyword_to_column = rules.keyword_to_column

    for keyword in keywords:
        if keyword in keyword_to_column:
            column = keyword_to_column[keyword]
            if column in known_columns:
                session_row[column] = "1"
            continue
        if any(keyword.endswith(suffix) for suffix in rules.identity_suffixes):
            session_row[keyword] = "1"
            continue
        warnings.append(f"Unknown NWB keyword not mapped to sessionInfo: {keyword}")

    return warnings


def discover_datatypes_from_keywords(keywords: List[str], rules: KeywordRules) -> Set[str]:
    """Infer SurLab datatype IDs present from NWB keywords."""
    found: Set[str] = set()
    keyword_to_column = rules.keyword_to_column
    for keyword in keywords:
        if keyword in keyword_to_column:
            found.add(keyword_to_column[keyword])
            continue
        if any(keyword.endswith(suffix) for suffix in rules.identity_suffixes):
            found.add(keyword)
    return found
