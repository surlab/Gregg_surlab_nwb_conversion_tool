"""Unit tests for conversion and validation helper behavior."""

from src.session_record import derive_identifier, discover_session_dirs, field_non_empty, normalize_age_days
from src.validator import (
    STATUS_FOUND,
    STATUS_MISSING_REQUIRED,
    STATUS_NOT_FOUND_RECOMMENDED,
)


def test_identifier_is_deterministic():
    record = {"animal_ID": "MouseA", "session_ID": "S01"}
    assert derive_identifier(record) == "MouseA__S01"


def test_age_days_zero_maps_to_iso_duration():
    assert normalize_age_days("0") == "P0D"


def test_non_empty_check_treats_zero_as_present():
    assert field_non_empty("0")
    assert field_non_empty(0)
    assert not field_non_empty("")


def test_status_constants_are_stable():
    assert STATUS_FOUND == "found"
    assert STATUS_MISSING_REQUIRED == "missing (Required)"
    assert STATUS_NOT_FOUND_RECOMMENDED == "not found (recommended)"


def test_discover_session_dirs_skips_pipeline_output():
    from pathlib import Path

    dataset_dir = Path(__file__).resolve().parents[1] / "demo_data" / "SeqBias_AstroBlock_NPX"
    session_dirs = discover_session_dirs(dataset_dir)
    names = [path.name for path in session_dirs]
    assert "AstroDREADD25_20240702" in names
    assert "roundtrip_surformat" not in names
    assert len(session_dirs) == 1


def test_trialinfo_legacy_aliases_and_leading_number():
    from src.nwb_trial_info import LEGACY_TRIALINFO_FIELD_MAP, _coerce_trial_value, _normalize_trial_row

    row = _normalize_trial_row({"start_time": "1.5", "stop_time": "2.5", "tone_freq": "4kHz"})
    assert row["start_time__s"] == "1.5"
    assert row["tone_frequency__Hz"] == "4kHz"
    assert LEGACY_TRIALINFO_FIELD_MAP["stim_onset"] == "stimulus_onset__s"
    value, ok = _coerce_trial_value("4kHz", "float64", "tone_frequency__Hz")
    assert ok and value == 4.0
    value, ok = _coerce_trial_value("correct", "int", "correct")
    assert ok and value == 1
