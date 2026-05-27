"""Unit tests for Task 4 NWB -> SurLab reverse helper behavior."""

from src.NWB_to_sur import _age_duration_to_days, _all_headers, _ordered_sessioninfo_columns


def test_age_duration_to_days_for_iso_duration():
    assert _age_duration_to_days("P90D") == "90"
    assert _age_duration_to_days("90") == ""


def test_ordered_headers_put_explicit_before_extras():
    explicit_columns = ["animal_ID", "session_ID", "condition"]
    rows = [
        {"animal_ID": "A1", "session_ID": "S1", "condition": "test", "custom_beta": "b"},
        {"animal_ID": "A2", "session_ID": "S2", "condition": "test2", "custom_alpha": "a"},
    ]
    headers = _all_headers(explicit_columns, rows)
    assert headers[:3] == explicit_columns
    assert headers[3:] == ["custom_alpha", "custom_beta"]


def test_sessioninfo_columns_required_then_optional():
    rows = [
        {
            "row_type": "metadata_field",
            "surlab_filename": "sessionInfo_<datasetID>.csv",
            "fieldname_surlab": "animal_ID",
            "requirement_level": "required",
        },
        {
            "row_type": "metadata_field",
            "surlab_filename": "sessionInfo_<datasetID>.csv",
            "fieldname_surlab": "condition",
            "requirement_level": "optional",
        },
    ]
    assert _ordered_sessioninfo_columns(rows) == ["animal_ID", "condition"]
