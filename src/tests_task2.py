"""Unit tests for stage-1 conversion and validation helper behavior."""

from pathlib import Path

from src.sur_to_nwb import _derive_identifier, _normalize_age
from src.validator import (
    STATUS_FOUND,
    STATUS_MISSING_REQUIRED,
    STATUS_NOT_FOUND_RECOMMENDED,
    _field_non_empty,
    _get_requirement_level,
)


def test_identifier_is_deterministic():
    record = {"animal_ID": "MouseA", "session_ID": "S01"}
    assert _derive_identifier(record) == "MouseA__S01"


def test_age_days_zero_maps_to_iso_duration():
    assert _normalize_age("0") == "P0D"


def test_requirement_level_supports_new_and_legacy_columns():
    assert _get_requirement_level({"requirement_level": "required"}) == "required"
    assert _get_requirement_level({"required": "true"}) == "required"
    assert _get_requirement_level({"required": "false"}) == "optional"


def test_non_empty_check_treats_zero_as_present():
    assert _field_non_empty("0")
    assert _field_non_empty(0)
    assert not _field_non_empty("")


def test_status_constants_are_stable():
    assert STATUS_FOUND == "found"
    assert STATUS_MISSING_REQUIRED == "missing (Required)"
    assert STATUS_NOT_FOUND_RECOMMENDED == "not found (recommended)"

