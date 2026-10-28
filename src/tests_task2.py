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
    assert not field_non_empty("[]")
    assert not field_non_empty([])
    assert not field_non_empty({})


def test_status_constants_are_stable():
    assert STATUS_FOUND == "found"
    assert STATUS_MISSING_REQUIRED == "missing (Required)"
    assert STATUS_NOT_FOUND_RECOMMENDED == "not found (recommended)"


def test_discover_session_dirs_skips_pipeline_output():
    from pathlib import Path

    dataset_dir = Path(__file__).resolve().parents[1] / "demo_data" / "surlab_format_demo"
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


def test_expand_rows_binds_traces_not_beh_to_ophys_templates():
    from src.conversion_table import expand_rows_for_datatypes

    rows = [
        {
            "stage": "3",
            "requirement_condition": "if_datatype_present:<datatypeID>",
            "surlab_filename": "<datatypeID>_data.{mat|npz}",
            "nwb_location": "NWBFile/ophys/RoiResponseSeries",
            "nwb_fieldname": "data",
            "fieldname_surlab": "NA",
        },
        {
            "stage": "1",
            "requirement_condition": "if_datatype_present:<datatypeID>",
            "surlab_filename": "sessionInfo_<datasetID>.csv",
            "nwb_location": "NWBFile/ophys/OpticalChannel",
            "nwb_fieldname": "name",
            "fieldname_surlab": "<datatypeID>_indicator",
        },
            {
                "stage": "1",
                "requirement_condition": "if_datatype_present:<datatypeID>",
                "surlab_filename": "sessionInfo_<datasetID>.csv",
                "nwb_location": "NWBFile/acquisition/<datatypeID>",
                "nwb_fieldname": "unit",
                "fieldname_surlab": "<datatypeID>_data_unit_measurement",
            },
            {
                "stage": "4",
                "requirement_condition": "if_datatype_present:<datatypeID>",
                "surlab_filename": "<datatypeID>_data.{mat|npz}",
                "nwb_location": "NWBFile/acquisition/<datatypeID>",
                "nwb_fieldname": "data",
                "fieldname_surlab": "NA",
            },
        ]
    expanded = expand_rows_for_datatypes(rows, {"GCaMP8m_traces", "pupil_behTSeries"})
    by_file = [row["surlab_filename"] for row in expanded]
    assert "GCaMP8m_traces_data.{mat|npz}" in by_file
    assert "pupil_behTSeries_data.{mat|npz}" in by_file
    assert sum(1 for name in by_file if name.endswith("_data.{mat|npz}")) == 2
    ophys_indicators = [
        row for row in expanded if row.get("nwb_location") == "NWBFile/ophys/OpticalChannel"
    ]
    assert len(ophys_indicators) == 1
    assert ophys_indicators[0]["fieldname_surlab"] == "GCaMP8m_traces_indicator"
    acq_units = [
        row
        for row in expanded
        if "acquisition" in str(row.get("nwb_location", ""))
        and row.get("nwb_fieldname") == "unit"
        and "data_unit_measurement" in str(row.get("fieldname_surlab", ""))
    ]
    assert len(acq_units) == 1
    assert acq_units[0]["fieldname_surlab"] == "pupil_behTSeries_data_unit_measurement"
    assert acq_units[0]["nwb_location"] == "NWBFile/acquisition/pupil_behTSeries"


def test_traces_axis_transpose_when_roi_on_axis0():
    import numpy as np
    from src.nwb_traces import _ensure_time_by_roi
    from src.table_placement import PlacementContext

    context = PlacementContext(session_record={}, table_rows=[])
    data = np.zeros((3, 10))  # ROI x time
    metadata_rows = [{"roi_ID": "0"}, {"roi_ID": "1"}, {"roi_ID": "2"}]
    out = _ensure_time_by_roi(data, metadata_rows, context, "GCaMP8m_traces", {})
    assert out.shape == (10, 3)
    assert context.warnings


def test_beh_tseries_axis_transpose_when_feature_on_axis0():
    import numpy as np
    from src.nwb_beh_tseries import _ensure_time_by_feature
    from src.table_placement import PlacementContext

    context = PlacementContext(session_record={}, table_rows=[])
    data = np.zeros((2, 5))  # features x time
    metadata_rows = [{"feature_ID": "0"}, {"feature_ID": "1"}]
    out = _ensure_time_by_feature(data, metadata_rows, context, "pupil_behTSeries", {})
    assert out.shape == (5, 2)
    assert context.warnings


def test_expand_rows_binds_behtseries_stage4_to_acquisition():
    from src.conversion_table import expand_rows_for_datatypes

    rows = [
        {
            "stage": "4",
            "requirement_condition": "if_datatype_present:<datatypeID>",
            "surlab_filename": "<datatypeID>_data.{mat|npz}",
            "nwb_location": "NWBFile/acquisition/<datatypeID>",
            "nwb_fieldname": "data",
            "fieldname_surlab": "NA",
        },
        {
            "stage": "4",
            "requirement_condition": "if_datatype_present:<datatypeID>",
            "surlab_filename": "<datatypeID>_metadata.csv",
            "nwb_location": "NWBFile/processing/behavior/<datatypeID>_features",
            "nwb_fieldname": "feature_label",
            "fieldname_surlab": "feature_label",
        },
    ]
    expanded = expand_rows_for_datatypes(rows, {"pupil_behTSeries", "GCaMP8m_traces"})
    assert any(row["surlab_filename"] == "pupil_behTSeries_data.{mat|npz}" for row in expanded)
    assert not any("GCaMP8m_traces_data" in row["surlab_filename"] for row in expanded)
    assert any(
        row.get("nwb_location") == "NWBFile/processing/behavior/pupil_behTSeries_features"
        for row in expanded
    )


def test_lfp_axis_transpose_when_channel_on_axis0():
    import numpy as np
    from src.nwb_lfp import _ensure_time_by_channel
    from src.table_placement import PlacementContext

    context = PlacementContext(session_record={}, table_rows=[])
    data = np.zeros((8, 100))  # channels x time
    metadata_rows = [{"channel_ID": str(i)} for i in range(8)]
    out = _ensure_time_by_channel(data, metadata_rows, context, {})
    assert out.shape == (100, 8)
    assert context.warnings


def test_spike_waves_axis_transpose_when_unit_on_axis0():
    import numpy as np
    from src.nwb_spike_waves import _ensure_samples_by_unit
    from src.table_placement import PlacementContext

    context = PlacementContext(session_record={}, table_rows=[])
    data = np.zeros((5, 82))  # units x samples
    metadata_rows = [{"unit_ID": str(i)} for i in range(1, 6)]
    out = _ensure_samples_by_unit(data, metadata_rows, context, {})
    assert out.shape == (82, 5)
    assert context.warnings


def test_parse_coordinate_list_accepts_space_separated():
    from src.data_io import parse_coordinate_list

    assert parse_coordinate_list("2 3 4 2 3 4") == [2.0, 3.0, 4.0, 2.0, 3.0, 4.0]
    assert parse_coordinate_list("1 1 1 2 2 2 3 3 3") == [1.0, 1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0]
    assert parse_coordinate_list("405.0") == [405.0]


def test_build_roi_pixel_mask_uses_center_or_outline():
    from src.nwb_traces import _build_roi_pixel_mask
    from src.table_placement import PlacementContext

    context = PlacementContext(session_record={}, table_rows=[])
    center_row = {"roi_center_x": "410", "roi_center_y": "363"}
    assert _build_roi_pixel_mask(center_row, context, "GCaMP8m_traces", 0) == [[410.0, 363.0, 1.0]]

    outline_row = {"roi_x_coordinates": "2 3 4 2", "roi_y_coordinates": "1 1 1 2"}
    mask = _build_roi_pixel_mask(outline_row, context, "GCaMP8m_traces", 0)
    assert mask == [[2.0, 1.0, 1.0], [3.0, 1.0, 1.0], [4.0, 1.0, 1.0], [2.0, 2.0, 1.0]]


def test_parse_coordinate_value_accepts_numeric_strings():
    import math
    from src.data_io import parse_coordinate_value

    assert parse_coordinate_value("405.0") == 405.0
    assert parse_coordinate_value("405 px") == 405.0
    assert math.isnan(parse_coordinate_value(""))


def test_beh_events_object_array_squeeze():
    import numpy as np
    from src.data_io import squeeze_object_array

    raw = np.array([np.array([1.0, 2.0]), np.array([3.0])], dtype=object)
    series = squeeze_object_array(raw)
    assert len(series) == 2
    assert np.allclose(series[0], [1.0, 2.0])
    assert np.allclose(series[1], [3.0])


def test_spike_times_forward_writes_schema_device_and_quality_description(tmp_path):
    import json
    from datetime import datetime

    from pynwb import NWBFile
    from pynwb.file import Subject

    from src.data_io import save_spike_times_npz
    from src.nwb_spike_times import apply_spike_times
    from src.table_placement import PlacementContext

    session_dir = tmp_path / "session"
    dataset_dir = tmp_path / "dataset"
    session_dir.mkdir()
    dataset_dir.mkdir()

    spikes = [[0.1, 0.2], [1.0]]
    save_spike_times_npz(session_dir / "spikeTimes_data.npz", spikes)
    (session_dir / "spikeTimes_metadata.csv").write_text(
        "unit_ID,quality\n1,1\n2,0\n",
        encoding="utf-8",
    )
    (session_dir / "spikeTimes_schema.json").write_text(
        json.dumps({"probe": "Neuropixel1.0", "acquisition_software": "SpikeGLX"}),
        encoding="utf-8",
    )

    session_record = {
        "animal_ID": "MouseA",
        "session_ID": "S01",
        "spikeTimes_probe": "Neuropixel1.0",
        "spikeTimes_acquisition_software": "SpikeGLX",
        "spikeTimes_sorting_software": "Kilosort4",
        "spikeTimes_filter_type": "bandpass",
        "spikeTimes_filter_cutoff_low__Hz": "300",
        "spikeTimes_filter_cutoff_high__Hz": "6000",
        "spikeTimes_sample_frequency__Hz": "30000",
        "spikeTimes_data_unit_measurement": "time__s",
        "spikeTimes_quality_metric": "binary_good_unit_0_1",
    }

    nwbfile = NWBFile(
        session_description="test",
        identifier="MouseA__S01",
        session_start_time=datetime(2026, 1, 1, 12, 0, 0),
        subject=Subject(subject_id="MouseA"),
    )
    nwbfile.create_device(name="GCaMP8m_traces_device", description="MISSING_REQUIRED_FOR_NWB")

    apply_spike_times(nwbfile, PlacementContext(session_record=session_record, table_rows=[]), dataset_dir, session_dir)

    assert "Neuropixel1.0" in nwbfile.devices
    assert "acquisition_software=SpikeGLX" in nwbfile.devices["Neuropixel1.0"].description
    assert "sorting_software=Kilosort4" in nwbfile.devices["Neuropixel1.0"].description
    assert "device" in nwbfile.units.colnames
    assert nwbfile.units["device"][0].name == "Neuropixel1.0"
    assert "quality_metric_description" in nwbfile.units.colnames
    assert nwbfile.units["quality_metric_description"][0] == "binary_good_unit_0_1"
    assert "SurLabSchema_spikeTimes" in nwbfile.lab_meta_data
    schema_payload = json.loads(nwbfile.lab_meta_data["SurLabSchema_spikeTimes"].schema_json)
    assert schema_payload["sample_frequency__Hz"] == 30000
    assert schema_payload["data_unit_measurement"] == "time__s"
    assert schema_payload["filter_type"] == "bandpass"


def test_ecephys_probe_reader_skips_ophys_placeholder_devices():
    from types import SimpleNamespace

    from src.nwb_table_reader import read_nwb_value_for_row

    ophys = SimpleNamespace(name="GCaMP8m_traces_device", description="MISSING_REQUIRED_FOR_NWB")
    probe = SimpleNamespace(
        name="Neuropixel1.0",
        description="acquisition_software=SpikeGLX; sorting_software=Kilosort4",
    )
    nwbfile = SimpleNamespace(
        devices={"GCaMP8m_traces_device": ophys, "Neuropixel1.0": probe},
        processing={"behavior": SimpleNamespace(description="behavioral streams")},
        units=None,
    )
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "spikeTimes_probe",
            "datatype_id": "spikeTimes",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.name",
            "nwb_type": "str",
        },
    ) == "Neuropixel1.0"
    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "spikeTimes_sorting_software",
            "datatype_id": "spikeTimes",
            "nwb_location": "NWBFile/processing",
            "nwb_fieldname": "processing_module_description",
            "nwb_type": "str",
        },
    ) == "Kilosort4"


def test_validator_rejects_spikewaves_metadata_area_column(tmp_path):
    from src.validator import SEVERITY_FAIL, _issues_spikewaves_forbidden_metadata_columns

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "spikeWaves_metadata.csv").write_text("unit_ID,area\n1,PFC\n", encoding="utf-8")
    issues = _issues_spikewaves_forbidden_metadata_columns(session_dir, {"spikeWaves"})
    assert len(issues) == 1
    assert issues[0].severity == SEVERITY_FAIL


def test_traces_forward_uses_microscope_device_and_reuses_across_streams(tmp_path):
    import json
    from datetime import datetime

    import numpy as np
    from pynwb import NWBFile
    from pynwb.file import Subject

    from src.nwb_traces import apply_traces
    from src.table_placement import PlacementContext

    session_dir = tmp_path / "session"
    dataset_dir = tmp_path / "dataset"
    session_dir.mkdir()
    dataset_dir.mkdir()

    for stream_id in ("GCaMP8m_traces", "Neuropil_traces"):
        data = np.ones((3, 2), dtype=float)
        timestamps = np.array([0.0, 1.0, 2.0])
        np.savez(session_dir / f"{stream_id}_data.npz", data=data)
        np.savez(session_dir / f"{stream_id}_timestamps.npz", timestamps=timestamps)
        (session_dir / f"{stream_id}_metadata.csv").write_text(
            "roi_ID,roi_center_x,roi_center_y\n1,10,20\n2,11,21\n",
            encoding="utf-8",
        )
        (session_dir / f"{stream_id}_schema.json").write_text(
            json.dumps(
                {
                    "indicator": "GCaMP8m",
                    "data_unit_measurement": "fluorescence__a.u.",
                    "sample_frequency__Hz": 15,
                    "microscope": "Bruker_Ultima",
                }
            ),
            encoding="utf-8",
        )

    session_record = {
        "animal_ID": "MouseA",
        "session_ID": "S01",
        "GCaMP8m_traces": "1",
        "Neuropil_traces": "1",
        "GCaMP8m_traces_microscope": "Bruker_Ultima",
        "Neuropil_traces_microscope": "Bruker_Ultima",
        "GCaMP8m_traces_microscope_description": "Two-photon; Prairie View",
        "Neuropil_traces_microscope_description": "Two-photon; Prairie View",
        "GCaMP8m_traces_indicator": "GCaMP8m",
        "Neuropil_traces_indicator": "GCaMP8m",
        "GCaMP8m_traces_data_unit_measurement": "fluorescence__a.u.",
        "Neuropil_traces_data_unit_measurement": "fluorescence__a.u.",
        "GCaMP8m_traces_sample_frequency__Hz": "15",
        "Neuropil_traces_sample_frequency__Hz": "15",
    }

    nwbfile = NWBFile(
        session_description="test",
        identifier="MouseA__S01",
        session_start_time=datetime(2026, 1, 1, 12, 0, 0),
        subject=Subject(subject_id="MouseA"),
    )

    context = PlacementContext(session_record=session_record, table_rows=[])
    discovered = {"GCaMP8m_traces", "Neuropil_traces"}
    apply_traces(nwbfile, context, dataset_dir, session_dir, discovered)

    assert "Bruker_Ultima" in nwbfile.devices
    assert "GCaMP8m_traces_device" not in nwbfile.devices
    assert nwbfile.devices["Bruker_Ultima"].description == "Two-photon; Prairie View"
    assert len(nwbfile.devices) == 1

    from src.nwb_table_reader import read_nwb_value_for_row

    assert read_nwb_value_for_row(
        nwbfile,
        {
            "fieldname_surlab": "GCaMP8m_traces_microscope",
            "datatype_id": "GCaMP8m_traces",
            "nwb_location": "NWBFile/devices",
            "nwb_fieldname": "Device.name",
            "nwb_type": "str",
        },
    ) == "Bruker_Ultima"
    assert "Neuropil_traces" in nwbfile.processing["ophys"].data_interfaces["Fluorescence"].roi_response_series


def test_spike_waves_ignores_matlab_empty_sample_frequency(tmp_path):
    import json
    import math
    from datetime import datetime

    import numpy as np
    from pynwb import NWBFile
    from pynwb.file import Subject

    from src.nwb_spike_waves import apply_spike_waves
    from src.table_placement import PlacementContext

    session_dir = tmp_path / "session"
    dataset_dir = tmp_path / "dataset"
    session_dir.mkdir()
    dataset_dir.mkdir()

    # 4 samples x 2 units
    np.savez(session_dir / "spikeWaves_data.npz", data=np.ones((4, 2)))
    (session_dir / "spikeWaves_metadata.csv").write_text(
        "unit_ID,primary_channel\n1,1\n2,2\n",
        encoding="utf-8",
    )
    (session_dir / "spikeWaves_schema.json").write_text(
        json.dumps({"sampFreq": [], "probe": "Neuropixel1.0", "data_unit_meas": "amplitude__au"}),
        encoding="utf-8",
    )

    nwbfile = NWBFile(
        session_description="test",
        identifier="MouseA__S01",
        session_start_time=datetime(2026, 1, 1, 12, 0, 0),
        subject=Subject(subject_id="MouseA"),
    )
    apply_spike_waves(
        nwbfile,
        PlacementContext(
            session_record={"spikeWaves_probe": "Neuropixel1.0"},
            table_rows=[],
        ),
        dataset_dir,
        session_dir,
    )

    assert "waveforms" in nwbfile.units.colnames
    assert len(nwbfile.units) == 2
    rate = getattr(nwbfile.units, "waveform_rate", None)
    assert rate is None or (isinstance(rate, (float, np.floating)) and math.isnan(float(rate)))


def test_traces_forward_placeholder_when_microscope_missing(tmp_path):
    import json
    from datetime import datetime

    import numpy as np
    from pynwb import NWBFile
    from pynwb.file import Subject

    from src.nwb_traces import MISSING_MARKER, apply_traces
    from src.table_placement import PlacementContext

    session_dir = tmp_path / "session"
    dataset_dir = tmp_path / "dataset"
    session_dir.mkdir()
    dataset_dir.mkdir()

    stream_id = "GCaMP8m_traces"
    np.savez(session_dir / f"{stream_id}_data.npz", data=np.ones((2, 1)))
    np.savez(session_dir / f"{stream_id}_timestamps.npz", timestamps=np.array([0.0, 1.0]))
    (session_dir / f"{stream_id}_metadata.csv").write_text("roi_ID\n1\n", encoding="utf-8")
    (session_dir / f"{stream_id}_schema.json").write_text(
        json.dumps({"indicator": "GCaMP8m", "data_unit_measurement": "fluorescence__a.u."}),
        encoding="utf-8",
    )

    session_record = {
        "animal_ID": "MouseA",
        "session_ID": "S01",
        "GCaMP8m_traces": "1",
        "GCaMP8m_traces_indicator": "GCaMP8m",
        "GCaMP8m_traces_data_unit_measurement": "fluorescence__a.u.",
    }

    nwbfile = NWBFile(
        session_description="test",
        identifier="MouseA__S01",
        session_start_time=datetime(2026, 1, 1, 12, 0, 0),
        subject=Subject(subject_id="MouseA"),
    )
    apply_traces(
        nwbfile,
        PlacementContext(session_record=session_record, table_rows=[]),
        dataset_dir,
        session_dir,
        {stream_id},
    )

    assert "GCaMP8m_traces_device" in nwbfile.devices
    assert nwbfile.devices["GCaMP8m_traces_device"].description == MISSING_MARKER
