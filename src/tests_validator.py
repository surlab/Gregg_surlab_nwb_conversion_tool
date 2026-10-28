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


def test_assess_correct_rejects_early_press():
    status, detail, _ = assess_value_type(
        "early_press",
        "str",
        "correct",
        "operant correctness when scored; missing when unscored",
    )
    assert status == STATUS_FAIL
    assert "early_press" in detail


def test_assess_correct_accepts_verbose_strings():
    assert assess_value_type("correct", "str", "correct", "")[0] == STATUS_PASS
    assert assess_value_type("incorrect", "str", "correct", "")[0] == STATUS_PASS
    assert assess_value_type("error", "str", "correct", "")[0] == STATUS_PASS


def test_assess_correct_legacy_zero_one():
    assert assess_value_type("1", "str", "correct", "")[0] == STATUS_PASS
    assert assess_value_type("0", "str", "correct", "")[0] == STATUS_PASS


def test_assess_trial_type_aborted_and_rejects_early_press():
    assert assess_value_type("aborted", "str", "trial_type", "")[0] == STATUS_PASS
    status, detail, _ = assess_value_type("early_press", "str", "trial_type", "")
    assert status == STATUS_FAIL
    assert "aborted" in detail


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


def test_numeric_array_is_float64_compatible_rejects_object():
    from src.validator import _numeric_array_is_float64_compatible
    import numpy as np

    ok, detail = _numeric_array_is_float64_compatible(np.array(["a"], dtype=object))
    assert not ok
    assert "object dtype" in detail


def test_array_validation_lfp_shape_and_timestamps(tmp_path):
    import numpy as np

    from src.validator import ValidationConfig, validate_session_format

    session_dir = tmp_path / "mouse1_session1"
    session_dir.mkdir()
    dataset_dir = tmp_path
    (dataset_dir / "sessionInfo_demo.csv").write_text(
        "animal_ID,session_ID,lfp\nmouse1,session1,1\n",
        encoding="utf-8",
    )
    (session_dir / "sessionInfo_single_session.csv").write_text(
        "animal_ID,session_ID,lfp\nmouse1,session1,1\n",
        encoding="utf-8",
    )
    (session_dir / "lfp_schema.json").write_text(
        '{"X_size": 4, "Y_size": 2, "data_unit_measurement": "amplitude__V"}',
        encoding="utf-8",
    )
    np.savez(session_dir / "lfp_data.npz", data=np.zeros((4, 2)))
    np.savez(session_dir / "lfp_timestamps.npz", timestamps=np.arange(4, dtype=float))

    table_path = tmp_path / "table.csv"
    table_path.write_text(
        "row_type,surlab_file_location,surlab_filename,fieldname_surlab,units,"
        "requirement_level,requirement_condition,nwb_location,nwb_fieldname,nwb_type,stage,notes\n"
        "data_array,session_dir,lfp_data.{mat|npz},NA,na,required,if_datatype_present:lfp,"
        "NWBFile/acquisition/lfp,data,array_of_float64,6,\n"
        "timestamps_array,session_dir,lfp_timestamps.{mat|npz},NA,na,required,if_datatype_present:lfp,"
        "NWBFile/acquisition/lfp,timestamps,array_of_float64,6,\n",
        encoding="utf-8",
    )

    result = validate_session_format(
        ValidationConfig(
            dataset_dir=dataset_dir,
            session_dir=session_dir,
            conversion_table_path=table_path,
        )
    )
    assert result.fail_count == 0
    assert any(issue.check.startswith("array|load|lfp|data") for issue in result.issues)


def test_array_validation_timestamps_length_mismatch_fails(tmp_path):
    import numpy as np

    from src.validator import ValidationConfig, validate_session_format

    session_dir = tmp_path / "mouse1_session1"
    session_dir.mkdir()
    dataset_dir = tmp_path
    (dataset_dir / "sessionInfo_demo.csv").write_text(
        "animal_ID,session_ID,lfp\nmouse1,session1,1\n",
        encoding="utf-8",
    )
    (session_dir / "sessionInfo_single_session.csv").write_text(
        "animal_ID,session_ID,lfp\nmouse1,session1,1\n",
        encoding="utf-8",
    )
    (session_dir / "lfp_schema.json").write_text(
        '{"X_size": 4, "Y_size": 2}',
        encoding="utf-8",
    )
    np.savez(session_dir / "lfp_data.npz", data=np.zeros((4, 2)))
    np.savez(session_dir / "lfp_timestamps.npz", timestamps=np.arange(3, dtype=float))

    table_path = tmp_path / "table.csv"
    table_path.write_text(
        "row_type,surlab_file_location,surlab_filename,fieldname_surlab,units,"
        "requirement_level,requirement_condition,nwb_location,nwb_fieldname,nwb_type,stage,notes\n"
        "data_array,session_dir,lfp_data.{mat|npz},NA,na,required,if_datatype_present:lfp,"
        "NWBFile/acquisition/lfp,data,array_of_float64,6,\n"
        "timestamps_array,session_dir,lfp_timestamps.{mat|npz},NA,na,required,if_datatype_present:lfp,"
        "NWBFile/acquisition/lfp,timestamps,array_of_float64,6,\n",
        encoding="utf-8",
    )

    result = validate_session_format(
        ValidationConfig(
            dataset_dir=dataset_dir,
            session_dir=session_dir,
            conversion_table_path=table_path,
        )
    )
    assert result.fail_count >= 1
    assert any("timestamps_vs_data" in issue.check for issue in result.issues)


def test_traces_microscope_cross_stream_mismatch_warns():
    from src.validator import _issues_traces_microscope_consistency

    issues = _issues_traces_microscope_consistency(
        {
            "GCaMP8m_traces_microscope": "Bruker_Ultima",
            "Neuropil_traces_microscope": "Thorlabs_Bergamo_II",
        },
        {"GCaMP8m_traces", "Neuropil_traces"},
    )
    assert len(issues) == 1
    assert issues[0].status == STATUS_WARN
    assert "disagree" in issues[0].detail


def test_traces_microscope_cross_stream_match_no_warn():
    from src.validator import _issues_traces_microscope_consistency

    issues = _issues_traces_microscope_consistency(
        {
            "GCaMP8m_traces_microscope": "Bruker_Ultima",
            "Neuropil_traces_microscope": "Bruker_Ultima",
        },
        {"GCaMP8m_traces", "Neuropil_traces"},
    )
    assert issues == []


def test_spikewaves_area_column_warns_not_recommended(tmp_path):
    from src.validator import _issues_not_recommended_columns_present

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "spikeWaves_metadata.csv").write_text(
        "unit_ID,primary_channel,area\n1,1,PFC\n",
        encoding="utf-8",
    )
    table_path = tmp_path / "table.csv"
    table_path.write_text(
        "row_type,surlab_file_location,surlab_filename,fieldname_surlab,units,"
        "requirement_level,requirement_condition,nwb_location,nwb_fieldname,nwb_type,stage,notes\n"
        "metadata_field,session_dir,spikeWaves_metadata.csv,area,plain text,not-recommended,"
        "if_datatype_present:spikeWaves,NWBFile,validate_only,str,7,mal-pattern\n",
        encoding="utf-8",
    )
    from src.conversion_table import expand_rows_for_datatypes, read_conversion_table

    rows = expand_rows_for_datatypes(read_conversion_table(table_path), {"spikeWaves"})
    issues = _issues_not_recommended_columns_present(
        rows,
        tmp_path,
        session_dir,
        {},
        {"spikeWaves"},
    )
    assert len(issues) == 1
    assert issues[0].status == STATUS_WARN


def test_spikewaves_area_must_match_spiketimes(tmp_path):
    from src.validator import STATUS_FAIL, _issues_spikewaves_area_vs_spiketimes

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "spikeTimes_metadata.csv").write_text(
        "unit_ID,area\n1,VISp\n",
        encoding="utf-8",
    )
    (session_dir / "spikeWaves_metadata.csv").write_text(
        "unit_ID,primary_channel,area\n1,1,PFC\n",
        encoding="utf-8",
    )
    issues = _issues_spikewaves_area_vs_spiketimes(session_dir, {"spikeWaves", "spikeTimes"})
    assert len(issues) == 1
    assert issues[0].status == STATUS_FAIL
    assert "unit_ID 1" in issues[0].detail


def test_spikewaves_area_column_warns_not_recommended(tmp_path):
    from src.validator import _issues_not_recommended_columns_present

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "spikeWaves_metadata.csv").write_text(
        "unit_ID,primary_channel,area\n1,1,PFC\n",
        encoding="utf-8",
    )
    table_path = tmp_path / "table.csv"
    table_path.write_text(
        "row_type,surlab_file_location,surlab_filename,fieldname_surlab,units,"
        "requirement_level,requirement_condition,nwb_location,nwb_fieldname,nwb_type,stage,notes\n"
        "metadata_field,session_dir,spikeWaves_metadata.csv,area,plain text,not-recommended,"
        "if_datatype_present:spikeWaves,NWBFile,validate_only,str,7,mal-pattern\n",
        encoding="utf-8",
    )
    from src.conversion_table import expand_rows_for_datatypes, read_conversion_table

    rows = expand_rows_for_datatypes(read_conversion_table(table_path), {"spikeWaves"})
    issues = _issues_not_recommended_columns_present(
        rows,
        tmp_path,
        session_dir,
        {},
        {"spikeWaves"},
    )
    assert len(issues) == 1
    assert issues[0].status == STATUS_WARN


def test_spikewaves_area_must_match_spiketimes(tmp_path):
    from src.validator import _issues_spikewaves_area_vs_spiketimes, STATUS_FAIL

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "spikeTimes_metadata.csv").write_text(
        "unit_ID,area\n1,VISp\n",
        encoding="utf-8",
    )
    (session_dir / "spikeWaves_metadata.csv").write_text(
        "unit_ID,primary_channel,area\n1,1,PFC\n",
        encoding="utf-8",
    )
    issues = _issues_spikewaves_area_vs_spiketimes(session_dir, {"spikeWaves", "spikeTimes"})
    assert len(issues) == 1
    assert issues[0].status == STATUS_FAIL
    assert "unit_ID 1" in issues[0].detail
