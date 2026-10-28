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
    assert session_row.get("spikeWaves") == "1"
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
            "action",
            "correct",
            "tone_idx",
        )

        def __init__(self):
            self._data = {
                "start_time": np.asarray([1.5, 2.5], dtype=float),
                "stop_time": np.asarray([2.0, 3.0], dtype=float),
                "stimulus_onset__s": np.asarray([1.6, 2.6], dtype=float),
                "action": np.asarray(["lick", "no_press"], dtype=object),
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
        headers = list(rows[0].keys())
        assert headers[:3] == [
            "start_time__s",
            "stop_time__s",
            "stimulus_onset__s",
        ]
        assert "action" in headers
        assert "correct" in headers
        assert rows[0]["start_time__s"] == "1.5000"
        assert rows[0]["action"] == "lick"
        assert rows[0]["correct"] == "correct"
        assert rows[1]["correct"] == "incorrect"
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


def test_imaging_plane_rate_reads_imaging_rate_alias():
    from types import SimpleNamespace

    import numpy as np

    from src.nwb_table_reader import read_nwb_value_for_row

    plane = SimpleNamespace(imaging_rate=15.0, rate=None)
    series = SimpleNamespace(
        name="GCaMP8m_traces",
        data=np.zeros((2, 1)),
        timestamps=np.arange(2, dtype=float),
        rois=SimpleNamespace(table=SimpleNamespace(imaging_plane=plane, colnames=(), id=np.asarray([0]))),
        imaging_plane=None,
    )
    fluorescence = SimpleNamespace(roi_response_series={"GCaMP8m_traces": series})
    nwbfile = SimpleNamespace(
        processing={"ophys": SimpleNamespace(data_interfaces={"Fluorescence": fluorescence})},
        acquisition={},
        lab_meta_data={},
        keywords=["GCaMP8m_traces"],
    )
    value = read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "GCaMP8m_traces_sample_frequency__Hz",
            "datatype_id": "GCaMP8m_traces",
            "nwb_location": "NWBFile/ophys/ImagingPlane",
            "nwb_fieldname": "imaging_rate",
            "nwb_type": "float",
        },
    )
    assert value in {"15", "15.0"}


def test_export_traces_from_fake_ophys_nwb(tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.conversion_table import read_conversion_table
    from src.nwb_reverse_traces import export_traces_from_nwb
    from src.nwb_table_reader import read_nwb_value_for_row

    class FakePlaneSeg:
        colnames = ("roi_x", "area")

        def __init__(self):
            self.id = np.asarray([0, 1])
            self._data = {
                "roi_x": np.asarray([10.0, 20.0]),
                "area": np.asarray(["VISp", "VISp"], dtype=object),
            }
            self.imaging_plane = SimpleNamespace(
                rate=15.0,
                optical_channel=SimpleNamespace(name="GCaMP8m", emission_lambda=920.0),
            )

        def __len__(self):
            return 2

        def __getitem__(self, key):
            return self._data[key]

    plane = FakePlaneSeg()
    series = SimpleNamespace(
        name="GCaMP8m_traces",
        data=np.arange(12, dtype=float).reshape(6, 2),
        timestamps=np.arange(6, dtype=float),
        unit="fluorescence__a.u.",
        rois=SimpleNamespace(table=plane),
        imaging_plane=plane.imaging_plane,
    )
    fluorescence = SimpleNamespace(roi_response_series={"GCaMP8m_traces": series})
    module = SimpleNamespace(data_interfaces={"Fluorescence": fluorescence})
    schema_meta = SimpleNamespace(
        name="SurLabSchema_GCaMP8m_traces",
        detection_software="Suite2p",
        laser_name="Insight",
        description="",
        schema_json="",
        extras_json="",
        fields_json="",
        fields={},
    )
    nwbfile = SimpleNamespace(
        keywords=["GCaMP8m_traces"],
        processing={"ophys": module},
        acquisition={},
        lab_meta_data={"SurLabSchema_GCaMP8m_traces": schema_meta},
        units=None,
        trials=None,
    )

    table_rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    written = export_traces_from_nwb(
        nwbfile,
        tmp_path,
        "DemoDS",
        {"animal_ID": "A1", "session_ID": "S1"},
        table_rows,
        dev_max_stage=3,
        present_datatypes={"GCaMP8m_traces"},
    )
    names = sorted(path.name for path in written)
    assert any(name.startswith("GCaMP8m_traces_data_") and name.endswith(".npz") for name in names)
    assert any(name.startswith("GCaMP8m_traces_timestamps_") for name in names)
    assert any(name.startswith("GCaMP8m_traces_metadata_") for name in names)
    assert any(name.startswith("GCaMP8m_traces_schema_") for name in names)

    data_file = next(path for path in written if "_data_" in path.name)
    loaded = np.load(data_file)
    assert loaded["data"].shape == (6, 2)

    assert (
        read_nwb_value_for_row(
            nwbfile,
            {
                "fieldname_surlab": "GCaMP8m_traces_indicator",
                "datatype_id": "GCaMP8m_traces",
                "nwb_location": "NWBFile/ophys/OpticalChannel",
                "nwb_fieldname": "name",
                "nwb_type": "str",
            },
        )
        == "GCaMP8m"
    )
    assert (
        read_nwb_value_for_row(
            nwbfile,
            {
                "fieldname_surlab": "detection_software",
                "datatype_id": "GCaMP8m_traces",
                "nwb_location": "NWBFile/lab_meta_data/SurLabSchema_GCaMP8m_traces",
                "nwb_fieldname": "detection_software",
                "nwb_type": "str",
            },
        )
        == "Suite2p"
    )


def test_build_session_row_expands_traces_stream_scalars():
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.NWB_to_sur import build_session_row_from_nwb
    from src.conversion_table import read_conversion_table

    class FakePlaneSeg:
        colnames = ()

        def __init__(self):
            self.id = np.asarray([0])
            self.imaging_plane = SimpleNamespace(
                rate=15.0,
                optical_channel=SimpleNamespace(name="GCaMP8m", emission_lambda=920.0),
            )

        def __len__(self):
            return 1

        def __getitem__(self, key):
            raise KeyError(key)

    plane = FakePlaneSeg()
    series = SimpleNamespace(
        name="GCaMP8m_traces",
        data=np.zeros((3, 1)),
        timestamps=np.arange(3, dtype=float),
        unit="a.u.",
        rois=SimpleNamespace(table=plane),
        imaging_plane=plane.imaging_plane,
    )
    fluorescence = SimpleNamespace(roi_response_series={"GCaMP8m_traces": series})
    nwbfile = SimpleNamespace(
        keywords=["GCaMP8m_traces"],
        processing={"ophys": SimpleNamespace(data_interfaces={"Fluorescence": fluorescence})},
        acquisition={},
        lab_meta_data={
            "SurLabSchema_GCaMP8m_traces": SimpleNamespace(
                name="SurLabSchema_GCaMP8m_traces",
                detection_software="Suite2p",
                description="",
                schema_json="",
                extras_json="",
                fields_json="",
                fields={},
            )
        },
        units=None,
        trials=None,
        subject=None,
        institution="MIT",
        lab="SurLab",
        experimenter="Tester",
        session_id="S1",
        session_start_time=None,
        session_description="",
        related_publications=[],
        experiment_description="",
        notes="",
        devices={},
    )
    rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    session_row, _warnings, present = build_session_row_from_nwb(nwbfile, rows)
    assert "GCaMP8m_traces" in present
    assert session_row.get("GCaMP8m_traces") == "1"
    assert session_row.get("GCaMP8m_traces_indicator") == "GCaMP8m"
    assert session_row.get("GCaMP8m_traces_sample_frequency__Hz") in {"15", "15.0"}
    assert session_row.get("GCaMP8m_traces_detection_software") == "Suite2p"


def test_export_beh_tseries_from_fake_nwb(tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.conversion_table import read_conversion_table
    from src.nwb_reverse_beh_tseries import export_beh_tseries_from_nwb
    from src.nwb_table_reader import read_nwb_value_for_row

    class FakeFeatures:
        colnames = ("feature_ID", "feature_label")

        def __init__(self):
            self._data = {
                "feature_ID": np.asarray([0, 1], dtype=int),
                "feature_label": np.asarray(["pupil", "area"], dtype=object),
            }

        def __len__(self):
            return 2

        def __getitem__(self, key):
            return self._data[key]

    features = FakeFeatures()
    series = SimpleNamespace(
        name="pupil_behTSeries",
        data=np.arange(6, dtype=float).reshape(3, 2),
        timestamps=np.arange(3, dtype=float),
        unit="mixed__see_metadata",
        rate=None,
    )
    behavior = SimpleNamespace(data_interfaces={"pupil_behTSeries_features": features})
    schema_meta = SimpleNamespace(
        name="SurLabSchema_pupil_behTSeries",
        schema_json='{"sample_frequency__Hz": 30.0}',
        description="",
        extras_json="",
        fields_json="",
        fields={},
    )
    nwbfile = SimpleNamespace(
        keywords=["pupil_behTSeries"],
        acquisition={"pupil_behTSeries": series},
        processing={"behavior": behavior},
        lab_meta_data={"SurLabSchema_pupil_behTSeries": schema_meta},
    )

    table_rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    written = export_beh_tseries_from_nwb(
        nwbfile,
        tmp_path,
        "DemoDS",
        {"animal_ID": "A1", "session_ID": "S1"},
        table_rows,
        dev_max_stage=4,
        present_datatypes={"pupil_behTSeries"},
    )
    names = sorted(path.name for path in written)
    assert any(name.startswith("pupil_behTSeries_data_") for name in names)
    assert any(name.startswith("pupil_behTSeries_metadata_") for name in names)
    assert any(name.startswith("pupil_behTSeries_schema_") for name in names)

    assert (
        read_nwb_value_for_row(
            nwbfile,
            {
                "fieldname_surlab": "pupil_behTSeries_data_unit_measurement",
                "datatype_id": "pupil_behTSeries",
                "nwb_location": "NWBFile/acquisition/pupil_behTSeries",
                "nwb_fieldname": "unit",
                "nwb_type": "str",
            },
        )
        == "mixed__see_metadata"
    )
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "pupil_behTSeries_sample_frequency__Hz",
            "datatype_id": "pupil_behTSeries",
            "nwb_location": "NWBFile/acquisition/pupil_behTSeries",
            "nwb_fieldname": "rate",
            "nwb_type": "float",
        },
    ) in {"30", "30.0"}


def test_build_session_row_expands_behtseries_stream_scalars():
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.NWB_to_sur import build_session_row_from_nwb
    from src.conversion_table import read_conversion_table

    class FakeFeatures:
        colnames = ("feature_ID", "feature_label")

        def __init__(self):
            self._data = {
                "feature_ID": np.asarray([0], dtype=int),
                "feature_label": np.asarray(["wheel_speed_native"], dtype=object),
            }

        def __len__(self):
            return 1

        def __getitem__(self, key):
            return self._data[key]

    series = SimpleNamespace(
        name="wheel_behTSeries",
        data=np.zeros((2, 1)),
        timestamps=np.arange(2, dtype=float),
        unit="mixed__see_metadata",
        rate=None,
    )
    behavior = SimpleNamespace(data_interfaces={"wheel_behTSeries_features": FakeFeatures()})
    nwbfile = SimpleNamespace(
        keywords=["wheel_behTSeries"],
        acquisition={"wheel_behTSeries": series},
        processing={"behavior": behavior},
        lab_meta_data={
            "SurLabSchema_wheel_behTSeries": SimpleNamespace(
                name="SurLabSchema_wheel_behTSeries",
                schema_json='{"sample_frequency__Hz": 0.0}',
                description="",
                extras_json="",
                fields_json="",
                fields={},
            )
        },
        units=None,
        trials=None,
        subject=None,
        institution="MIT",
        lab="SurLab",
        experimenter="Tester",
        session_id="S1",
        session_start_time=None,
        session_description="",
        related_publications=[],
        experiment_description="",
        notes="",
        devices={},
    )
    rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    session_row, _warnings, present = build_session_row_from_nwb(nwbfile, rows)
    assert "wheel_behTSeries" in present
    assert session_row.get("wheel_behTSeries") == "1"
    assert session_row.get("wheel_behTSeries_data_unit_measurement") == "mixed__see_metadata"
    assert session_row.get("wheel_behTSeries_sample_frequency__Hz") in {"0", "0.0"}


def test_export_lfp_from_fake_nwb(tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.conversion_table import read_conversion_table
    from src.nwb_reverse_lfp import export_lfp_from_nwb
    from src.nwb_table_reader import read_nwb_value_for_row

    class FakeElectrodes:
        colnames = ("location", "channel_label", "depth__um", "grid_location", "x", "y", "z", "group")

        def __init__(self):
            self.id = np.asarray([1, 2], dtype=int)
            self._data = {
                "location": np.asarray(["PFC", "PFC"], dtype=object),
                "channel_label": np.asarray(["ch1", "ch2"], dtype=object),
                "depth__um": np.asarray([20.0, 30.0]),
                "grid_location": np.asarray(["0,0", "0,1"], dtype=object),
                "x": np.asarray([np.nan, np.nan]),
                "y": np.asarray([np.nan, np.nan]),
                "z": np.asarray([20.0, 30.0]),
                "group": np.asarray([None, None], dtype=object),
            }

        def __len__(self):
            return 2

        def __getitem__(self, key):
            return self._data[key]

    device = SimpleNamespace(name="Neuropixel1.0")
    group = SimpleNamespace(name="lfp_electrodes", device=device)
    electrodes = FakeElectrodes()
    electrodes._data["group"] = np.asarray([group, group], dtype=object)
    region = SimpleNamespace(data=np.asarray([0, 1], dtype=int))
    series = SimpleNamespace(
        name="lfp",
        data=np.arange(6, dtype=float).reshape(3, 2),
        timestamps=np.arange(3, dtype=float),
        unit="volts",
        description="SurLab lfp stream; data_unit_measurement=amplitude__V",
        electrodes=region,
    )
    schema_meta = SimpleNamespace(
        name="SurLabSchema_lfp",
        schema_json='{"sample_frequency__Hz": 2500.0, "filter_type": "bandpass"}',
        description="",
        extras_json="",
        fields_json="",
        fields={},
    )
    nwbfile = SimpleNamespace(
        keywords=["lfp"],
        acquisition={"lfp": series},
        electrodes=electrodes,
        lab_meta_data={"SurLabSchema_lfp": schema_meta},
        devices={"Neuropixel1.0": device},
    )

    table_rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    written = export_lfp_from_nwb(
        nwbfile,
        tmp_path,
        "DemoDS",
        {"animal_ID": "A1", "session_ID": "S1"},
        table_rows,
        dev_max_stage=6,
    )
    names = sorted(path.name for path in written)
    assert any(name.startswith("lfp_data_") for name in names)
    assert any(name.startswith("lfp_metadata_") for name in names)
    assert any(name.startswith("lfp_schema_") for name in names)

    assert (
        read_nwb_value_for_row(
            nwbfile,
            {
                "fieldname_surlab": "lfp_data_unit_measurement",
                "datatype_id": "lfp",
                "nwb_location": "NWBFile/acquisition/lfp",
                "nwb_fieldname": "unit",
                "nwb_type": "str",
            },
        )
        == "amplitude__V"
    )


def test_export_spike_waves_from_fake_nwb(tmp_path):
    import json
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.conversion_table import read_conversion_table
    from src.nwb_reverse_spike_waves import export_spike_waves_from_nwb

    class FakeUnits:
        colnames = (
            "id",
            "waveforms",
            "primary_channel",
            "brain_area",
            "sampling_rate__Hz",
        )

        def __init__(self):
            self.id = np.asarray([1, 2], dtype=int)
            self._data = {
                "waveforms": [
                    np.arange(4, dtype=float),
                    np.arange(4, 8, dtype=float),
                ],
                "primary_channel": np.asarray([1, 2], dtype=int),
                "brain_area": np.asarray(["PFC", "PFC"], dtype=object),
                "sampling_rate__Hz": np.asarray([30000.0, 30000.0]),
            }

        def __len__(self):
            return 2

        def __getitem__(self, key):
            return self._data[key]

    schema_meta = SimpleNamespace(
        name="SurLabSchema_spikeWaves",
        schema_json='{"snippet_timestamps": [0.0, 0.001, 0.002, 0.003], "clustering_algorithm": "Kilosort4", "data_unit_measurement": "amplitude__au"}',
        description="",
        extras_json="",
        fields_json="",
        fields={},
    )
    nwbfile = SimpleNamespace(
        keywords=["spike_waveforms"],
        units=FakeUnits(),
        lab_meta_data={"SurLabSchema_spikeWaves": schema_meta},
        devices={"Neuropixel1.0": SimpleNamespace(name="Neuropixel1.0")},
    )

    table_rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    written = export_spike_waves_from_nwb(
        nwbfile,
        tmp_path,
        "DemoDS",
        {"animal_ID": "A1", "session_ID": "S1"},
        table_rows,
        dev_max_stage=7,
    )
    names = sorted(path.name for path in written)
    assert any(name.startswith("spikeWaves_data_") for name in names)
    assert any(name.startswith("spikeWaves_timestamps_") for name in names)
    assert any(name.startswith("spikeWaves_metadata_") for name in names)
    schema_paths = [path for path in written if "schema" in path.name]
    assert schema_paths
    schema = json.loads(schema_paths[0].read_text(encoding="utf-8"))
    assert schema.get("data_unit_measurement") == "amplitude__au"


def test_spike_waves_data_unit_from_surlab_schema():
    from pathlib import Path
    from types import SimpleNamespace

    from src.NWB_to_sur import build_session_row_from_nwb
    from src.conversion_table import read_conversion_table
    from src.nwb_table_reader import read_nwb_value_for_row

    schema_meta = SimpleNamespace(
        name="SurLabSchema_spikeWaves",
        schema_json='{"data_unit_measurement": "amplitude__au"}',
        description="",
        extras_json="",
        fields_json="",
        fields={},
    )

    class FakeUnits:
        colnames = ("id", "waveforms")
        waveform_rate = 30000.0

        def __init__(self):
            self.id = [1]

        def __len__(self):
            return 1

        def __getitem__(self, key):
            raise KeyError(key)

    nwbfile = SimpleNamespace(
        keywords=["spike_waveforms"],
        units=FakeUnits(),
        lab_meta_data={"SurLabSchema_spikeWaves": schema_meta},
        devices={},
        acquisition={},
        electrodes=None,
        trials=None,
        subject=None,
        institution="MIT",
        lab="SurLab",
        experimenter="Tester",
        session_id="S1",
        session_start_time=None,
        session_description="",
        related_publications=[],
        experiment_description="",
        notes="",
        processing={},
    )
    row = {
        "fieldname_surlab": "spikeWaves_data_unit_measurement",
        "requirement_condition": "if_datatype_present:spikeWaves",
        "nwb_location": "NWBFile/units",
        "nwb_fieldname": "custom_column_data_unit_measurement",
        "nwb_type": "str",
    }
    assert read_nwb_value_for_row(nwbfile, row) == "amplitude__au"
    rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    session_row, _warnings, present = build_session_row_from_nwb(nwbfile, rows)
    assert "spikeWaves" in present
    assert session_row.get("spikeWaves_data_unit_measurement") == "amplitude__au"


def test_export_beh_events_from_fake_nwb(tmp_path):
    import json
    from pathlib import Path
    from types import SimpleNamespace

    import numpy as np

    from src.conversion_table import read_conversion_table
    from src.nwb_reverse_beh_events import export_beh_events_from_nwb

    class FakeEvents:
        colnames = ("event_ID", "event_label")

        def __init__(self):
            self._data = {
                "event_ID": np.asarray([1], dtype=int),
                "event_label": np.asarray(["lick"], dtype=object),
            }

        def __len__(self):
            return 1

        def __getitem__(self, key):
            return self._data[key]

    series = SimpleNamespace(
        name="lick_behEvents",
        timestamps=np.asarray([0.1, 0.2, 0.3], dtype=float),
        description="SurLab behEvents; data_unit_measurement=time__s",
    )
    behavior = SimpleNamespace(data_interfaces={"lick_behEvents_events": FakeEvents()})
    nwbfile = SimpleNamespace(
        keywords=["lick_behEvents"],
        acquisition={"lick_behEvents": series},
        processing={"behavior": behavior},
        lab_meta_data={},
    )

    table_rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    written = export_beh_events_from_nwb(
        nwbfile,
        tmp_path,
        "DemoDS",
        {"animal_ID": "A1", "session_ID": "S1"},
        table_rows,
        dev_max_stage=8,
        present_datatypes={"lick_behEvents"},
    )
    names = sorted(path.name for path in written)
    assert any(name.startswith("lick_behEvents_data_") for name in names)
    assert any(name.startswith("lick_behEvents_metadata_") for name in names)
    assert any(name.startswith("lick_behEvents_schema_") for name in names)

    data_file = next(path for path in written if "_data_" in path.name)
    loaded = np.load(data_file, allow_pickle=True)
    assert loaded["data"].shape == (1, 1)
    assert len(loaded["data"][0, 0]) == 3

    schema_file = next(path for path in written if "_schema_" in path.name)
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    assert schema.get("X_dim") == "event_type"
    assert schema.get("Y_dim") == "events"
    assert schema.get("X_size") == 1
    assert schema.get("Y_size") == 1
    assert schema.get("X_size") != 3  # not nested lick count


def test_beh_events_unit_parsed_from_description_unit_key():
    from types import SimpleNamespace

    from src.nwb_table_reader import read_nwb_value_for_row

    series = SimpleNamespace(
        name="lick_behEvents",
        timestamps=[0.1, 0.2],
        description="SurLab behEvents stream lick_behEvents; unit=time__s",
    )
    nwbfile = SimpleNamespace(
        acquisition={"lick_behEvents": series},
        events={},
        processing={},
        lab_meta_data={},
    )
    value = read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "data_unit_measurement",
            "datatype_id": "lick_behEvents",
            "surlab_filename": "lick_behEvents_schema.json",
            "nwb_location": "NWBFile/acquisition/lick_behEvents",
            "nwb_fieldname": "description",
            "nwb_type": "str",
        },
    )
    assert value == "time__s"


def test_lfp_schema_probe_uses_condition_datatype():
    from types import SimpleNamespace

    from src.nwb_table_reader import datatype_id_from_row, read_nwb_value_for_row

    probe = SimpleNamespace(
        name="Neuropixel1.0",
        description="acquisition_software=SpikeGLX; sorting_software=Kilosort4",
    )
    placeholder = SimpleNamespace(
        name="GCaMP8m_traces_device",
        description="MISSING_REQUIRED_FOR_NWB",
    )
    nwbfile = SimpleNamespace(
        devices={"GCaMP8m_traces_device": placeholder, "Neuropixel1.0": probe},
        acquisition={},
        electrodes=None,
        units=None,
    )
    row = {
        "fieldname_surlab": "probe",
        "surlab_filename": "lfp_schema.json",
        "requirement_condition": "if_datatype_present:lfp",
        "nwb_location": "NWBFile/devices",
        "nwb_fieldname": "Device.name",
        "nwb_type": "str",
    }
    assert datatype_id_from_row(row) == "lfp"
    assert read_nwb_value_for_row(nwbfile, row) == "Neuropixel1.0"


def test_kitchen_sink_style_ecephys_probe_and_software():
    from pathlib import Path
    from types import SimpleNamespace

    from src.NWB_to_sur import build_session_row_from_nwb
    from src.conversion_table import read_conversion_table
    from src.nwb_table_reader import read_nwb_value_for_row

    ophys = SimpleNamespace(name="GCaMP8m_traces_device", description="MISSING_REQUIRED_FOR_NWB")
    probe = SimpleNamespace(
        name="Neuropixel1.0",
        description="acquisition_software=SpikeGLX; sorting_software=Kilosort4",
    )

    class FakeUnits:
        colnames = ("id", "waveforms", "waveform_rate")
        waveform_rate = 30000.0

        def __init__(self):
            self.id = [1, 2]

        def __len__(self):
            return 2

        def __getitem__(self, key):
            if key == "id":
                return self.id
            raise KeyError(key)

    behavior = SimpleNamespace(
        description="behavioral continuous streams and feature tables",
    )
    nwbfile = SimpleNamespace(
        keywords=["spike_times", "spike_waveforms", "lfp"],
        devices={"GCaMP8m_traces_device": ophys, "Neuropixel1.0": probe},
        units=FakeUnits(),
        processing={"behavior": behavior},
        acquisition={},
        electrodes=None,
        trials=None,
        subject=None,
        institution="MIT",
        lab="SurLab",
        experimenter="Tester",
        session_id="S1",
        session_start_time=None,
        session_description="",
        related_publications=[],
        experiment_description="",
        notes="",
        lab_meta_data={},
    )

    rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))
    session_row, _warnings, _present = build_session_row_from_nwb(nwbfile, rows)
    assert session_row.get("spikeTimes_probe") == "Neuropixel1.0"
    assert session_row.get("spikeTimes_acquisition_software") == "SpikeGLX"
    assert session_row.get("spikeTimes_sorting_software") == "Kilosort4"
    assert session_row.get("spikeWaves_probe") == "Neuropixel1.0"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "sample_frequency__Hz",
            "surlab_filename": "spikeWaves_schema.json",
            "requirement_condition": "if_datatype_present:spikeWaves",
            "nwb_location": "NWBFile/units",
            "nwb_fieldname": "waveform_rate",
            "nwb_type": "float",
        },
    ) in {"30000", "30000.0"}


def test_trialinfo_time_fields_use_fixed_decimals():
    from src.nwb_reverse_trial_info import _format_trial_cell

    assert _format_trial_cell(10.0, "float64", field_name="start_time__s") == "10.0000"
    assert _format_trial_cell(10.6, "float64", field_name="stimulus_onset__s") == "10.6000"
    assert _format_trial_cell(0.15, "float64", field_name="reaction_time__s") == "0.1500"
    assert _format_trial_cell(float("nan"), "float64", field_name="reaction_time__s") == "NaN"
    assert _format_trial_cell(float("nan"), "float64", field_name="stimulus_offset__s") == "NaN"


def _fake_traces_nwbfile(*, microscope_name: str, microscope_description: str = ""):
    from types import SimpleNamespace

    import numpy as np

    microscope = SimpleNamespace(
        name=microscope_name,
        description=microscope_description,
    )
    plane = SimpleNamespace(
        rate=15.0,
        device=microscope,
        optical_channel=SimpleNamespace(name="GCaMP8m", emission_lambda=920.0),
    )

    class FakePlaneSeg:
        colnames = ()

        def __init__(self):
            self.id = np.asarray([0])
            self.imaging_plane = plane

        def __len__(self):
            return 1

        def __getitem__(self, key):
            raise KeyError(key)

    plane_seg = FakePlaneSeg()
    series = SimpleNamespace(
        name="GCaMP8m_traces",
        data=np.zeros((3, 1)),
        timestamps=np.arange(3, dtype=float),
        unit="a.u.",
        rois=SimpleNamespace(table=plane_seg),
        imaging_plane=plane,
    )
    fluorescence = SimpleNamespace(roi_response_series={"GCaMP8m_traces": series})
    devices = {microscope_name: microscope}
    return SimpleNamespace(
        keywords=["GCaMP8m_traces"],
        processing={"ophys": SimpleNamespace(data_interfaces={"Fluorescence": fluorescence})},
        acquisition={},
        lab_meta_data={
            "SurLabSchema_GCaMP8m_traces": SimpleNamespace(
                name="SurLabSchema_GCaMP8m_traces",
                detection_software="Suite2p",
                description="",
                schema_json="",
                extras_json="",
                fields_json="",
                fields={},
            )
        },
        units=None,
        trials=None,
        subject=None,
        institution="MIT",
        lab="SurLab",
        experimenter="Tester",
        session_id="S1",
        session_start_time=None,
        session_description="",
        related_publications=[],
        experiment_description="",
        notes="",
        devices=devices,
    )


def test_reverse_microscope_reads_imaging_plane_device():
    from pathlib import Path

    from src.NWB_to_sur import build_session_row_from_nwb
    from src.conversion_table import read_conversion_table
    from src.nwb_table_reader import read_nwb_value_for_row

    nwbfile = _fake_traces_nwbfile(
        microscope_name="Bruker_Ultima",
        microscope_description="Two-photon; Prairie View",
    )
    rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))

    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "GCaMP8m_traces_microscope",
            "requirement_condition": "if_datatype_present:GCaMP8m_traces",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.name",
            "nwb_type": "str",
        },
    ) == "Bruker_Ultima"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "GCaMP8m_traces_microscope_description",
            "requirement_condition": "if_datatype_present:GCaMP8m_traces",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.description",
            "nwb_type": "str",
        },
    ) == "Two-photon; Prairie View"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "microscope",
            "surlab_filename": "GCaMP8m_traces_schema.json",
            "requirement_condition": "if_datatype_present:GCaMP8m_traces",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.name",
            "nwb_type": "str",
        },
    ) == "Bruker_Ultima"

    session_row, _warnings, present = build_session_row_from_nwb(nwbfile, rows)
    assert "GCaMP8m_traces" in present
    assert session_row.get("GCaMP8m_traces_microscope") == "Bruker_Ultima"
    assert session_row.get("GCaMP8m_traces_microscope_description") == "Two-photon; Prairie View"


def test_reverse_microscope_skips_placeholder_device():
    from pathlib import Path

    from src.NWB_to_sur import build_session_row_from_nwb
    from src.conversion_table import read_conversion_table
    from src.nwb_table_reader import read_nwb_value_for_row

    nwbfile = _fake_traces_nwbfile(
        microscope_name="GCaMP8m_traces_device",
        microscope_description="MISSING_REQUIRED_FOR_NWB",
    )
    rows = read_conversion_table(Path("sur_nwb_conversion_table.csv"))

    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "GCaMP8m_traces_microscope",
            "requirement_condition": "if_datatype_present:GCaMP8m_traces",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.name",
            "nwb_type": "str",
        },
    ) == ""
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "GCaMP8m_traces_microscope_description",
            "requirement_condition": "if_datatype_present:GCaMP8m_traces",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.description",
            "nwb_type": "str",
        },
    ) == ""

    session_row, _warnings, _present = build_session_row_from_nwb(nwbfile, rows)
    assert session_row.get("GCaMP8m_traces_microscope", "") == ""
    assert session_row.get("GCaMP8m_traces_microscope_description", "") == ""


def test_export_traces_schema_includes_microscope_from_device(tmp_path):
    import json
    from pathlib import Path

    from src.conversion_table import filter_dev_stage, read_conversion_table
    from src.nwb_reverse_traces import export_traces_from_nwb

    nwbfile = _fake_traces_nwbfile(
        microscope_name="Bruker_Ultima",
        microscope_description="Two-photon; Prairie View",
    )
    rows = filter_dev_stage(read_conversion_table(Path("sur_nwb_conversion_table.csv")), 3)
    session_record = {"animal_ID": "MouseA", "session_ID": "S01", "GCaMP8m_traces": "1"}
    written = export_traces_from_nwb(
        nwbfile,
        tmp_path,
        "demo",
        session_record,
        rows,
        dev_max_stage=3,
    )
    schema_paths = [path for path in written if path.name.endswith("schema.json") or "_schema_" in path.name]
    assert schema_paths
    schema = json.loads(schema_paths[0].read_text(encoding="utf-8"))
    assert schema.get("microscope") == "Bruker_Ultima"
    assert schema.get("microscope_description") == "Two-photon; Prairie View"
    assert "GCaMP8m_traces_device" not in json.dumps(schema)

