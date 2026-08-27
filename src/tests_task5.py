"""Unit tests for Task 5 round-trip comparison helpers."""

from pathlib import Path

import numpy as np

from src.nwb_triangulation import attribute_roundtrip_issue
from src.roundtrip_validation import (
    STATUS_MATCH,
    STATUS_MISMATCH,
    STATUS_SKIPPED_NON_COMPARABLE,
    STATUS_SKIPPED_ROUNDTRIP_MISSING,
    ComparisonConfig,
    OriginalSnapshot,
    _compare_sessioninfo_field,
    _effective_sessioninfo_scalar,
    _normalize_age_value,
    _normalize_date_value,
    _normalize_modality_flag,
    _normalize_scalar,
    _values_match,
)


def test_normalize_scalar_boolean_aliases():
    assert _normalize_scalar(True) == "1"
    assert _normalize_scalar("false") == "0"


def test_normalize_age_iso_duration():
    assert _normalize_age_value("P90D") == "90"
    assert _normalize_age_value("90") == "90"


def test_normalize_date_formats():
    assert _normalize_date_value("07-02-2024") == "2024-07-02"
    assert _normalize_date_value("2024-07-02") == "2024-07-02"


def test_values_match_age_and_date():
    config = ComparisonConfig(Path("."), Path("sur_nwb_conversion_table.csv"))
    matched, _ = _values_match("age__days", "90", "P90D", config)
    assert matched
    matched, _ = _values_match("session_date", "07-02-2024", "2024-07-02", config)
    assert matched


def test_values_match_detects_difference():
    config = ComparisonConfig(Path("."), Path("sur_nwb_conversion_table.csv"))
    matched, detail = _values_match("institution", "MIT", "Harvard", config)
    assert not matched
    assert "Harvard" in detail


def test_status_constants():
    assert STATUS_MATCH == "match"
    assert STATUS_MISMATCH == "mismatch"
    assert STATUS_SKIPPED_ROUNDTRIP_MISSING == "skipped_roundtrip_missing"


def test_attribute_task4_when_nwb_matches_original():
    owner = attribute_roundtrip_issue(
        status="mismatch",
        field_name="unit_ID",
        original_value="1",
        nwb_value="1",
        roundtrip_value="",
        nwb_note="units column missing",
    )
    assert owner == "task4_reverse"


def test_attribute_task2_when_nwb_missing():
    owner = attribute_roundtrip_issue(
        status="mismatch",
        field_name="experimenter",
        original_value="Gabrielle Drummond",
        nwb_value="",
        roundtrip_value="",
        nwb_note="nwbfile",
    )
    assert owner == "task2_forward"


def test_array_allclose_behavior():
    left = np.array([0.0, 1.0, 2.0])
    right = np.array([0.0, 1.0, 2.0000001])
    assert np.allclose(left, right, rtol=1e-6, atol=1e-6)


def test_normalize_modality_flag_treats_empty_as_zero():
    assert _normalize_modality_flag("") == "0"
    assert _normalize_modality_flag("0") == "0"
    assert _normalize_modality_flag("1") == "1"


def test_effective_sessioninfo_scalar_uses_schema_mirror(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    schema_path = session_dir / "spikeTimes_schema_demo.json"
    schema_path.write_text('{"probe": "Neuropixel1.0"}', encoding="utf-8")
    snapshot = OriginalSnapshot(
        session_record={"animal_ID": "A", "session_ID": "1"},
        dataset_sessioninfo_path=None,
        dataset_session_row={},
        session_sessioninfo_path=None,
        session_session_row={"spikeTimes": "1"},
        discovered_datatypes={"spikeTimes"},
        resolved_files={},
    )
    table_row = {
        "notes": "Legacy optional mirror: spikeTimes_schema.json key probe. Fail if both non-empty and disagree.",
    }
    value, source = _effective_sessioninfo_scalar("spikeTimes_probe", snapshot, session_dir, table_row)
    assert value == "Neuropixel1.0"
    assert source == "schema mirror"


def test_compare_sessioninfo_field_matches_schema_mirror_when_column_absent(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "spikeTimes_schema_demo.json").write_text('{"probe": "Neuropixel1.0"}', encoding="utf-8")
    snapshot = OriginalSnapshot(
        session_record={"animal_ID": "A", "session_ID": "1"},
        dataset_sessioninfo_path=None,
        dataset_session_row={},
        session_sessioninfo_path=None,
        session_session_row={"spikeTimes": "1"},
        discovered_datatypes={"spikeTimes"},
        resolved_files={},
    )
    table_row = {
        "notes": "Legacy optional mirror: spikeTimes_schema.json key probe. Fail if both non-empty and disagree.",
    }
    config = ComparisonConfig(tmp_path, Path("sur_nwb_conversion_table.csv"))
    status, _ = _compare_sessioninfo_field(
        "spikeTimes_probe",
        snapshot,
        session_dir,
        table_row,
        {},
        {"spikeTimes_probe": "Neuropixel1.0"},
        config,
    )
    assert status == STATUS_MATCH


def test_compare_sessioninfo_field_skips_lfp_scalars_when_flag_off(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "lfp_schema_demo.json").write_text('{"probe": "Neuropixel1.0"}', encoding="utf-8")
    snapshot = OriginalSnapshot(
        session_record={"animal_ID": "A", "session_ID": "1"},
        dataset_sessioninfo_path=None,
        dataset_session_row={},
        session_sessioninfo_path=None,
        session_session_row={"lfp": "0"},
        discovered_datatypes={"lfp"},
        resolved_files={},
    )
    table_row = {
        "notes": "Legacy optional mirror: lfp_schema.json key probe. Fail if both non-empty and disagree.",
    }
    config = ComparisonConfig(tmp_path, Path("sur_nwb_conversion_table.csv"))
    status, detail = _compare_sessioninfo_field(
        "lfp_probe",
        snapshot,
        session_dir,
        table_row,
        {"lfp": "0"},
        {"lfp_probe": "Neuropixel1.0"},
        config,
    )
    assert status == STATUS_SKIPPED_NON_COMPARABLE
    assert "lfp flag=0" in detail


def test_compare_sessioninfo_lfp_flag_empty_roundtrip_matches_zero(tmp_path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    snapshot = OriginalSnapshot(
        session_record={"animal_ID": "A", "session_ID": "1"},
        dataset_sessioninfo_path=None,
        dataset_session_row={},
        session_sessioninfo_path=None,
        session_session_row={"lfp": "0"},
        discovered_datatypes=set(),
        resolved_files={},
    )
    config = ComparisonConfig(tmp_path, Path("sur_nwb_conversion_table.csv"))
    status, _ = _compare_sessioninfo_field(
        "lfp",
        snapshot,
        session_dir,
        {},
        {"lfp": "0"},
        {},
        config,
    )
    assert status == STATUS_MATCH
