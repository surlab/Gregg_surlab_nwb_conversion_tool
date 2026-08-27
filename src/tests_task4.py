"""Unit tests for Task 4 NWB -> SurLab reverse helper behavior."""

from src.NWB_to_sur import _age_duration_to_days, _all_headers, _ordered_sessioninfo_columns
from src.nwb_keyword_map import (
    apply_keywords_to_session_row,
    build_keyword_list,
    load_keyword_rules,
)
from src.nwb_table_reader import parse_experiment_description, parse_zero_time_from_notes, read_nwb_value_for_row


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


def test_parse_zero_time_from_notes():
    notes = "Other text\nSurLab zero_time=GCaMP7f_traces\nmore"
    assert parse_zero_time_from_notes(notes) == "GCaMP7f_traces"


def test_parse_experiment_description_key_value_pairs():
    parsed = parse_experiment_description("laser_power=42; PMT_gain=1.2")
    assert parsed == {"laser_power": "42", "PMT_gain": "1.2"}


def test_keyword_rules_empty_without_nwb_keyword_column():
    rows = [{"nwb_fieldname": "institution", "fieldname_surlab": "institution"}]
    rules = load_keyword_rules(rows)
    assert rules.fixed == {}
    assert rules.identity_suffixes == ()


def test_keyword_rules_from_conversion_table_column():
    rows = [
        {
            "nwb_fieldname": "keywords",
            "fieldname_surlab": "spikeTimes",
            "nwb_keyword": "spike_times",
        },
        {
            "nwb_fieldname": "keywords",
            "fieldname_surlab": "(per_stream_traces)",
            "nwb_keyword": "identity",
        },
    ]
    rules = load_keyword_rules(rows)
    assert rules.fixed == {"spikeTimes": "spike_times"}
    assert rules.identity_suffixes == ("_traces",)


def test_build_keyword_list_from_table_rules():
    rows = [
        {"nwb_fieldname": "keywords", "fieldname_surlab": "trialInfo", "nwb_keyword": "trials"},
        {"nwb_fieldname": "keywords", "fieldname_surlab": "(per_stream_traces)", "nwb_keyword": "identity"},
    ]
    session = {"trialInfo": "1", "GCaMP7f_traces": "1", "spikeTimes": "0"}
    assert build_keyword_list(session, rows) == ["GCaMP7f_traces", "trials"]


def test_keyword_rules_load_from_repo_conversion_table():
    from pathlib import Path

    from src.conversion_table import read_conversion_table

    table_path = Path(__file__).resolve().parents[1] / "sur_nwb_conversion_table.csv"
    rows = read_conversion_table(table_path)
    rules = load_keyword_rules(rows)
    assert rules.fixed["spikeTimes"] == "spike_times"
    assert rules.fixed["trialInfo"] == "trials"
    assert "_traces" in rules.identity_suffixes


def test_apply_keywords_to_session_row_fixed_and_per_stream():
    rules = load_keyword_rules(
        [
            {"nwb_fieldname": "keywords", "fieldname_surlab": "spikeTimes", "nwb_keyword": "spike_times"},
            {"nwb_fieldname": "keywords", "fieldname_surlab": "(per_stream_traces)", "nwb_keyword": "identity"},
        ]
    )
    row = {"animal_ID": "A1", "spikeTimes": "", "behEvents": ""}
    known = {"animal_ID", "spikeTimes", "GCaMP7f_traces", "behEvents"}
    warnings = apply_keywords_to_session_row(
        row,
        ["spike_times", "GCaMP7f_traces", "unknown_token"],
        rules,
        known,
    )
    assert row["spikeTimes"] == "1"
    assert row["GCaMP7f_traces"] == "1"
    assert row["behEvents"] == ""
    assert any("unknown_token" in message for message in warnings)


def test_read_nwb_table_reader_device_and_keywords():
    from types import SimpleNamespace

    device = SimpleNamespace(
        name="Neuropixel1.0",
        description="acquisition_software=spikeGLX; sorting_software=Kilosort",
    )
    nwbfile = SimpleNamespace(
        devices={"Neuropixel1.0": device},
        processing={},
        units=None,
        notes="SurLab zero_time=spikeTimes",
        keywords=["trials", "spike_times"],
        subject=None,
    )
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "probe",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.name",
            "nwb_type": "str",
        },
    ) == "Neuropixel1.0"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "acquisition_software",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.description",
            "nwb_type": "str",
        },
    ) == "spikeGLX"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "sorting_software",
            "nwb_location": "NWBFile/processing",
            "nwb_fieldname": "processing_module_description",
            "nwb_type": "str",
        },
    ) == "Kilosort"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "trialInfo",
            "nwb_location": "NWBFile",
            "nwb_fieldname": "keywords",
            "nwb_keyword": "trials",
            "nwb_type": "array_of_str",
        },
    ) == "1"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "lfp",
            "nwb_location": "NWBFile",
            "nwb_fieldname": "keywords",
            "nwb_keyword": "lfp",
            "nwb_type": "array_of_str",
        },
    ) == "0"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "zero_time",
            "nwb_location": "NWBFile",
            "nwb_fieldname": "notes",
            "nwb_type": "str",
        },
    ) == "spikeTimes"


def test_parse_combined_device_description_for_prefixed_stream_scalars():
    from types import SimpleNamespace

    from src.nwb_table_reader import schema_key_candidates

    device = SimpleNamespace(
        name="Neuropixel1.0",
        description="acquisition_software=spikeGLX; sorting_software=Kilosort",
    )
    nwbfile = SimpleNamespace(devices={"Neuropixel1.0": device}, processing={}, units=None)
    acq_notes = (
        "Legacy optional mirror: spikeTimes_schema.json key acquisition_software. "
        "Fail if both non-empty and disagree."
    )
    sort_notes = (
        "Legacy optional mirror: spikeTimes_schema.json key sorting_software. "
        "Fail if both non-empty and disagree."
    )
    assert schema_key_candidates("spikeTimes_acquisition_software", acq_notes)[0] == "acquisition_software"
    assert (
        read_nwb_value_for_row(
            nwbfile,
            {
                "fieldname_surlab": "spikeTimes_acquisition_software",
                "nwb_location": "NWBFile/devices",
                "nwb_fieldname": "Device.description",
                "nwb_type": "str",
                "notes": acq_notes,
            },
        )
        == "spikeGLX"
    )
    assert (
        read_nwb_value_for_row(
            nwbfile,
            {
                "fieldname_surlab": "spikeTimes_sorting_software",
                "nwb_location": "NWBFile/processing",
                "nwb_fieldname": "processing_module_description",
                "nwb_type": "str",
                "notes": sort_notes,
            },
        )
        == "Kilosort"
    )


def test_build_session_row_dual_write_software_and_no_spurious_lfp():
    from types import SimpleNamespace

    from src.NWB_to_sur import build_session_row_from_nwb
    from src.conversion_table import read_conversion_table
    from pathlib import Path

    device = SimpleNamespace(
        name="Neuropixel1.0",
        description="acquisition_software=spikeGLX; sorting_software=Kilosort",
    )

    class FakeUnits:
        colnames = ["spike_times"]

        def __len__(self):
            return 2

    nwbfile = SimpleNamespace(
        devices={"Neuropixel1.0": device},
        processing={},
        units=FakeUnits(),
        notes="SurLab zero_time=spikeTimes",
        keywords=["spike_times", "spike_waveforms", "trials"],
        subject=None,
        institution="MIT",
        lab="SurLab",
        experimenter="Gabrielle Drummond",
        session_id="20240702",
        session_start_time=None,
        session_description="DPCPX",
        related_publications=[],
        experiment_description="",
        lab_meta_data={},
    )
    rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    session_row, warnings, present = build_session_row_from_nwb(nwbfile, rows)
    assert "spikeTimes" in present
    assert "lfp" not in present
    assert session_row.get("spikeTimes") == "1"
    assert session_row.get("lfp") == "0"
    assert session_row.get("trialInfo") == "1"
    assert session_row.get("behEvents") == "0"
    assert session_row.get("spikeTimes_acquisition_software") == "spikeGLX"
    assert session_row.get("spikeTimes_sorting_software") == "Kilosort"
    assert session_row.get("spikeTimes_probe") == "Neuropixel1.0"
    assert "lfp_probe" not in session_row or session_row.get("lfp_probe", "") == ""
    assert "<datatypeID>_probe" not in session_row
    assert warnings == []


def test_export_trial_info_from_nwb_table_driven():
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.conversion_table import read_conversion_table
    from src.nwb_reverse_trial_info import export_trial_info_from_nwb

    class FakeTrials:
        colnames = (
            "start_time",
            "stop_time",
            "stimulus_onset__s",
            "output",
            "correct",
            "tone_idx",
        )

        def __init__(self):
            self._data = {
                "start_time": np.asarray([1.5, 2.5], dtype=float),
                "stop_time": np.asarray([2.0, 3.0], dtype=float),
                "stimulus_onset__s": np.asarray([1.6, 2.6], dtype=float),
                "output": np.asarray(["lick", "no_press"], dtype=object),
                "correct": np.asarray([1, 0], dtype=int),
                "tone_idx": np.asarray(["4", "12"], dtype=object),
            }

        def __len__(self):
            return 2

        def __getitem__(self, key):
            return self._data[key]

    nwbfile = SimpleNamespace(trials=FakeTrials())
    table_rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    output_dir = Path("demo_data") / "_tmp_task4_trialinfo_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        written = export_trial_info_from_nwb(
            nwbfile,
            output_dir,
            "DemoDS",
            {"animal_ID": "A1", "session_ID": "S1"},
            table_rows,
            dev_max_stage=5,
        )
        assert len(written) == 1
        assert written[0].name == "trialInfo_DemoDS_A1_S1.csv"
        import csv

        with written[0].open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert list(rows[0].keys())[:4] == [
            "start_time__s",
            "stop_time__s",
            "stimulus_onset__s",
            "output",
        ]
        assert rows[0]["start_time__s"] == "1.5"
        assert rows[0]["correct"] == "1"
        assert rows[1]["correct"] == "0"
        assert rows[0]["tone_idx"] == "4"
        assert "tone_idx" in rows[0]
    finally:
        for path in output_dir.glob("trialInfo_*.csv"):
            path.unlink()
        if output_dir.exists():
            output_dir.rmdir()


def test_discover_present_includes_trialinfo_from_trials():
    from types import SimpleNamespace

    from src.NWB_to_sur import _discover_present_datatypes

    class FakeTrials:
        def __len__(self):
            return 3

    nwbfile = SimpleNamespace(units=None, trials=FakeTrials(), keywords=["trials"])
    present = _discover_present_datatypes(
        nwbfile,
        [
            {
                "nwb_fieldname": "keywords",
                "fieldname_surlab": "trialInfo",
                "nwb_keyword": "trials",
            }
        ],
    )
    assert "trialInfo" in present

