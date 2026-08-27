"""Unit tests for SurLab format convention helpers."""

from src.validator import assess_value_type, STATUS_FAIL, STATUS_PASS, STATUS_WARN


def test_assess_float_rejects_unit_suffix():
    status, detail, _ = assess_value_type("4kHz", "float64", "tone_frequency__Hz", "auditory tone frequency numeric Hz")
    assert status == STATUS_FAIL
    assert "unit suffix" in detail


def test_assess_float_accepts_plain_number():
    status, detail, _ = assess_value_type("4", "float64", "tone_frequency__Hz", "Hz")
    assert status == STATUS_PASS
    assert detail == ""


def test_assess_correct_binary_only():
    status, detail, gap = assess_value_type("early_press", "int", "correct", "binary trial outcome 0/1")
    assert status == STATUS_FAIL
    assert "binary" in detail
    assert gap == "" or "binary" in gap or "allowed_values" in gap


def test_assess_correct_zero_one():
    status, _, _ = assess_value_type("1", "int", "correct", "binary trial outcome 0/1")
    assert status == STATUS_PASS


def test_assess_date_requires_iso():
    status, detail, _ = assess_value_type("07-02-2024", "datetime", "session_date", "calendar date YYYY-MM-DD")
    assert status == STATUS_FAIL
    assert "YYYY-MM-DD" in detail


def test_assess_sex_domain():
    status, _, _ = assess_value_type("X", "str", "sex", "single letter M F O U")
    assert status == STATUS_FAIL


def test_assess_frequency_sanity_warn():
    status, detail, _ = assess_value_type("0", "float", "sample_frequency__Hz", "float Hz")
    assert status == STATUS_WARN
    assert "frequency" in detail


def test_assess_float_or_str_accepts_both():
    assert assess_value_type("0.95", "float_or_str", "quality")[0] == STATUS_PASS
    assert assess_value_type("good", "float_or_str", "quality")[0] == STATUS_PASS


def test_assess_array_of_float_from_list():
    status, detail, _ = assess_value_type([0.0, 1.5, 2.0], "array_of_float", "X_idx")
    assert status == STATUS_PASS
    assert detail == ""


def test_assess_array_of_int_or_str():
    status, _, _ = assess_value_type([1, 2, "roi_a"], "array_of_int_or_str", "Y_idx")
    assert status == STATUS_PASS
    status, detail, _ = assess_value_type([1, "x"], "array_of_float", "X_idx")
    assert status == STATUS_FAIL
    assert "non-numeric" in detail


def test_conversion_table_has_no_ambiguous_nwb_types():
    from pathlib import Path

    from src.conversion_table import read_conversion_table

    rows = read_conversion_table(Path(__file__).resolve().parents[1] / "sur_nwb_conversion_table.csv")
    ambiguous = {
        str(row.get("fieldname_surlab", "")): str(row.get("nwb_type", "")).strip()
        for row in rows
        if str(row.get("nwb_type", "")).strip().lower() in {"variable", "array"}
    }
    assert ambiguous == {}
