"""Append LFP / spikeWaves / prefixed behEvents rows to sur_nwb_conversion_table.csv."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

HEADER = [
    "row_type",
    "surlab_file_location",
    "surlab_filename",
    "fieldname_surlab",
    "units",
    "requirement_level",
    "requirement_condition",
    "nwb_location",
    "nwb_fieldname",
    "nwb_alt_fieldnames",
    "nwb_keyword",
    "nwb_type",
    "mapping_rationale",
    "stage",
    "notes",
]


def row(**kwargs) -> dict[str, str]:
    out = {key: "" for key in HEADER}
    out.update(kwargs)
    return out


VALIDATE_NOTE = (
    "validate_only: checked by SurLab format validator "
    "(scripts/run_surlab_format_validation.py / src/validator.py); "
    "ignored by SurLab→NWB conversion (not written to NWB)."
)

LAB_LFP = "NWBFile/lab_meta_data/SurLabSchema_lfp"
LAB_WAVES = "NWBFile/lab_meta_data/SurLabSchema_spikeWaves"


def _normalize_modality_placement(rows: list[dict[str, str]]) -> None:
    """Align new LFP/spikeWaves rows with validate_only + SurLabSchema leftovers."""
    layout = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}
    lfp_leftover = {"filter_type", "filter_cutoff_low__Hz", "filter_cutoff_high__Hz"}
    waves_leftover = {"clustering_algorithm"}
    for r in rows:
        fname = str(r.get("surlab_filename", "")).strip()
        field = str(r.get("fieldname_surlab", "")).strip()
        stage = str(r.get("stage", "")).strip()
        if fname == "lfp_schema.json" and field in layout:
            r["nwb_location"] = "NWBFile"
            r["nwb_fieldname"] = "validate_only"
            r["mapping_rationale"] = "Layout / validate-only; implied by data + timestamps + metadata."
            r["notes"] = VALIDATE_NOTE
        if fname == "spikeWaves_schema.json" and field in layout:
            r["nwb_location"] = "NWBFile"
            r["nwb_fieldname"] = "validate_only"
            r["mapping_rationale"] = "Layout / validate-only; waveform axis not session clock."
            r["notes"] = VALIDATE_NOTE
        if fname == "lfp_schema.json" and field in lfp_leftover:
            r["nwb_location"] = LAB_LFP
            r["nwb_fieldname"] = field
            r["mapping_rationale"] = (
                "Optional legacy schema mirror; same SurLabSchema_lfp LabMetaData target as sessionInfo."
            )
            r["notes"] = "Same single NWB target as sessionInfo; dual-read conflict-fail."
        if fname == "spikeWaves_schema.json" and field in waves_leftover:
            r["nwb_location"] = LAB_WAVES
            r["nwb_fieldname"] = field
            r["mapping_rationale"] = (
                "Optional legacy schema mirror; same SurLabSchema_spikeWaves LabMetaData target."
            )
            r["notes"] = "Same single NWB target as sessionInfo; dual-read conflict-fail."
        if fname == "lfp_schema.json" and field == "dataset_specific":
            r["nwb_location"] = LAB_LFP
            r["nwb_fieldname"] = "*"
        if fname == "spikeWaves_schema.json" and field == "dataset_specific":
            r["nwb_location"] = LAB_WAVES
            r["nwb_fieldname"] = "*"
        # sessionInfo leftovers for lfp/spikeWaves filters
        if fname.startswith("sessionInfo") and field.startswith("lfp_filter"):
            key = field[len("lfp_") :]
            r["nwb_location"] = LAB_LFP
            r["nwb_fieldname"] = key
            r["mapping_rationale"] = (
                "Canonical sessionInfo; one LabMetaData target SurLabSchema_lfp (no core NWB filter object)."
            )
        if fname.startswith("sessionInfo") and field == "spikeWaves_clustering_algorithm":
            r["nwb_location"] = LAB_WAVES
            r["nwb_fieldname"] = "clustering_algorithm"
            r["mapping_rationale"] = (
                "Canonical sessionInfo; one LabMetaData target SurLabSchema_spikeWaves."
            )


NEW_ROWS = [
    # --- LFP stage 6 ---
    row(
        row_type="data_array",
        surlab_file_location="session_dir",
        surlab_filename="lfp_data.{mat|npz}",
        fieldname_surlab="NA",
        units="LFP [time x channels]; seconds via timestamps relative to session origin (t=0)",
        requirement_level="required",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="ElectricalSeries.data",
        nwb_type="array_of_float64",
        mapping_rationale="SPECULATIVE: NWB ElectricalSeries under acquisition (or ecephys ProcessingModule); confirm with dataset.",
        stage="6",
        notes="Canonical axis 0=time axis 1=channels. Prefer .npz. Transpose on ingest if legacy channels x time.",
    ),
    row(
        row_type="timestamps_array",
        surlab_file_location="session_dir",
        surlab_filename="lfp_timestamps.{mat|npz}",
        fieldname_surlab="NA",
        units="native sample times in seconds relative to session origin (t=0)",
        requirement_level="required",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="ElectricalSeries.timestamps",
        nwb_type="array_of_float64",
        mapping_rationale="SPECULATIVE: ElectricalSeries timestamps; native times no required resampling.",
        stage="6",
        notes="Required when lfp=1. Prefer .npz.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="data_unit_measurement",
        units="base__unit token string",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="ElectricalSeries.unit",
        nwb_type="str",
        mapping_rationale="Optional legacy mirror; canonical sessionInfo lfp_data_unit_measurement.",
        stage="6",
        notes="Legacy optional mirror of sessionInfo lfp_data_unit_measurement. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="X_dim",
        units="dimension label",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Canonical: X = axis 0 = time.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="Y_dim",
        units="dimension label",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Canonical: Y = axis 1 = channel.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="X_size",
        units="integer count",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="int",
        mapping_rationale="Optional; prefer derive from data.shape[0].",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="Y_size",
        units="integer count",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="int",
        mapping_rationale="Optional; prefer derive from data.shape[1] / metadata rows.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="sample_frequency__Hz",
        units="float Hz",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="ElectricalSeries.rate",
        nwb_type="float",
        mapping_rationale="Optional legacy mirror; canonical sessionInfo lfp_sample_frequency__Hz.",
        stage="6",
        notes="Legacy optional mirror of sessionInfo lfp_sample_frequency__Hz. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="probe",
        units="plain text",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/devices",
        nwb_fieldname="Device.name",
        nwb_type="str",
        mapping_rationale="Optional legacy mirror; canonical sessionInfo lfp_probe. Device linked to LFP electrodes.",
        stage="6",
        notes="Legacy optional mirror of sessionInfo lfp_probe. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="filter_type",
        units="plain text",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/processing",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Optional legacy mirror of sessionInfo lfp_filter_type.",
        stage="6",
        notes="Legacy optional mirror of sessionInfo lfp_filter_type. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="filter_cutoff_low__Hz",
        units="float Hz",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/processing",
        nwb_fieldname="custom_field",
        nwb_type="float",
        mapping_rationale="Optional legacy mirror of sessionInfo lfp_filter_cutoff_low__Hz.",
        stage="6",
        notes="Legacy optional mirror of sessionInfo lfp_filter_cutoff_low__Hz. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="filter_cutoff_high__Hz",
        units="float Hz",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/processing",
        nwb_fieldname="custom_field",
        nwb_type="float",
        mapping_rationale="Optional legacy mirror of sessionInfo lfp_filter_cutoff_high__Hz.",
        stage="6",
        notes="Legacy optional mirror of sessionInfo lfp_filter_cutoff_high__Hz. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_schema.json",
        fieldname_surlab="dataset_specific",
        units="N/A",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Unlisted schema keys preserved.",
        stage="6",
        notes="One generic row.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_metadata.csv",
        fieldname_surlab="channel_ID",
        units="integer or text id per channel",
        requirement_level="required",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/general/extracellular_ephys/electrodes",
        nwb_fieldname="id",
        nwb_type="int_or_str",
        mapping_rationale="SPECULATIVE: Electrodes table id; order matches LFP channel axis.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_metadata.csv",
        fieldname_surlab="channel_label",
        units="plain text",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/general/extracellular_ephys/electrodes",
        nwb_fieldname="custom_column_channel_label",
        nwb_type="str",
        mapping_rationale="SPECULATIVE: electrode label column.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_metadata.csv",
        fieldname_surlab="area",
        units="plain text",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/general/extracellular_ephys/electrodes",
        nwb_fieldname="location",
        nwb_alt_fieldnames="brain_area",
        nwb_type="str",
        mapping_rationale="SPECULATIVE: electrode location / brain area.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_metadata.csv",
        fieldname_surlab="depth__um",
        units="float micrometers",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/general/extracellular_ephys/electrodes",
        nwb_fieldname="custom_column_depth__um",
        nwb_alt_fieldnames="depth",
        nwb_type="float",
        mapping_rationale="SPECULATIVE: electrode depth.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_metadata.csv",
        fieldname_surlab="grid_location",
        units="row col pair",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/general/extracellular_ephys/electrodes",
        nwb_fieldname="custom_column_grid_location",
        nwb_type="str",
        mapping_rationale="Optional grid coordinate.",
        stage="6",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="lfp_metadata.csv",
        fieldname_surlab="dataset_specific",
        units="N/A",
        requirement_level="optional",
        requirement_condition="if_datatype_present:lfp",
        nwb_location="NWBFile/general/extracellular_ephys/electrodes",
        nwb_fieldname="custom_columns",
        nwb_type="str",
        mapping_rationale="Preserve unlisted electrode columns.",
        stage="6",
        notes="One generic row.",
    ),
    # --- spikeWaves stage 7 ---
    row(
        row_type="data_array",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_data.{mat|npz}",
        fieldname_surlab="NA",
        units="waveforms [waveform_samples x units]; axis 0 is snippet sample index not session clock",
        requirement_level="required",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="waveforms",
        nwb_type="array_of_float64",
        mapping_rationale="SPECULATIVE: Units waveforms / spike_waveforms extension; confirm with dataset.",
        stage="7",
        notes="Canonical axis 0=waveform sample axis 1=units. Prefer .npz. Sampling rate from sessionInfo spikeWaves_sample_frequency__Hz.",
    ),
    row(
        row_type="timestamps_array",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_timestamps.{mat|npz}",
        fieldname_surlab="NA",
        units="optional snippet-relative sample times (s from waveform start) NOT session clock",
        requirement_level="optional",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_field",
        nwb_type="array_of_float64",
        mapping_rationale="Optional explicit sample grid along waveform axis. Prefer spikeWaves_sample_frequency__Hz in sessionInfo when sufficient.",
        stage="7",
        notes="Not session-origin timestamps. Omit if sample_frequency__Hz documents the waveform axis.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_schema.json",
        fieldname_surlab="data_unit_measurement",
        units="base__unit token string",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_column_data_unit_measurement",
        nwb_type="str",
        mapping_rationale="Optional legacy mirror of sessionInfo spikeWaves_data_unit_measurement.",
        stage="7",
        notes="Legacy optional mirror of sessionInfo spikeWaves_data_unit_measurement. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_schema.json",
        fieldname_surlab="X_dim",
        units="dimension label",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Canonical: X = waveform_sample (snippet axis).",
        stage="7",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_schema.json",
        fieldname_surlab="Y_dim",
        units="dimension label",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Canonical: Y = unit.",
        stage="7",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_schema.json",
        fieldname_surlab="sample_frequency__Hz",
        units="float Hz",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_column_sampling_rate__Hz",
        nwb_type="float",
        mapping_rationale="Waveform snippet sampling rate. Canonical sessionInfo spikeWaves_sample_frequency__Hz.",
        stage="7",
        notes="Legacy optional mirror of sessionInfo spikeWaves_sample_frequency__Hz. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_schema.json",
        fieldname_surlab="probe",
        units="plain text",
        requirement_level="optional",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/devices",
        nwb_fieldname="Device.name",
        nwb_type="str",
        mapping_rationale="Optional legacy mirror of sessionInfo spikeWaves_probe.",
        stage="7",
        notes="Legacy optional mirror of sessionInfo spikeWaves_probe. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_schema.json",
        fieldname_surlab="clustering_algorithm",
        units="plain text",
        requirement_level="optional",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/processing",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Optional legacy mirror of sessionInfo spikeWaves_clustering_algorithm.",
        stage="7",
        notes="Legacy optional mirror of sessionInfo spikeWaves_clustering_algorithm. Fail if both non-empty and disagree.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_schema.json",
        fieldname_surlab="dataset_specific",
        units="N/A",
        requirement_level="optional",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Unlisted schema keys preserved.",
        stage="7",
        notes="One generic row.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_metadata.csv",
        fieldname_surlab="unit_ID",
        units="integer or text id per unit",
        requirement_level="required",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="id",
        nwb_type="int_or_str",
        mapping_rationale="Align with spikeTimes units when both present.",
        stage="7",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_metadata.csv",
        fieldname_surlab="primary_channel",
        units="channel id",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_column_primary_channel",
        nwb_type="int_or_str",
        mapping_rationale="SPECULATIVE: peak channel for waveform; relate to LFP channel_ID when shared probe.",
        stage="7",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_metadata.csv",
        fieldname_surlab="area",
        units="plain text",
        requirement_level="optional",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_column_brain_area",
        nwb_type="str",
        mapping_rationale="Optional region label.",
        stage="7",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="spikeWaves_metadata.csv",
        fieldname_surlab="dataset_specific",
        units="N/A",
        requirement_level="optional",
        requirement_condition="if_datatype_present:spikeWaves",
        nwb_location="NWBFile/units",
        nwb_fieldname="custom_columns",
        nwb_type="str",
        mapping_rationale="Preserve unlisted columns.",
        stage="7",
        notes="One generic row.",
    ),
    # --- behEvents stage 8 (prefixed streams) ---
    row(
        row_type="data_array",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_data.{mat|npz}",
        fieldname_surlab="NA",
        units="event times in seconds relative to session origin (t=0); object array of 1-D float arrays",
        requirement_level="required",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_TimeSeries_or_AnnotationSeries",
        nwb_type="array_of_float64",
        mapping_rationale="SPECULATIVE: acquisition AnnotationSeries / TimeSeries of event times; name = <datatypeID>.",
        stage="8",
        notes="Prefixed streams only (e.g. lick_behEvents). Prefer .npz. No separate timestamps file (times live in data).",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_schema.json",
        fieldname_surlab="data_unit_measurement",
        units="base__unit token string",
        requirement_level="recommended",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="unit",
        nwb_type="str",
        mapping_rationale="Usually time__s for event times.",
        stage="8",
        notes="Optional schema; prefer sessionInfo <datatypeID>_data_unit_measurement when present.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_schema.json",
        fieldname_surlab="X_dim",
        units="dimension label",
        requirement_level="optional",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Typically events.",
        stage="8",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_schema.json",
        fieldname_surlab="Y_dim",
        units="dimension label",
        requirement_level="optional",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Typically event_type / features.",
        stage="8",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_schema.json",
        fieldname_surlab="dataset_specific",
        units="N/A",
        requirement_level="optional",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_field",
        nwb_type="str",
        mapping_rationale="Unlisted schema keys preserved.",
        stage="8",
        notes="One generic row per stream.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_metadata.csv",
        fieldname_surlab="event_ID",
        units="integer or text id per event type / column",
        requirement_level="required",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_column_event_ID",
        nwb_type="int_or_str",
        mapping_rationale="SPECULATIVE: one row per event channel/type in the data object array.",
        stage="8",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_metadata.csv",
        fieldname_surlab="event_label",
        units="plain text",
        requirement_level="required",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_column_event_label",
        nwb_type="str",
        mapping_rationale="e.g. lick, lever_press.",
        stage="8",
        notes="",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="<datatypeID>_metadata.csv",
        fieldname_surlab="dataset_specific",
        units="N/A",
        requirement_level="optional",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile/acquisition",
        nwb_fieldname="custom_columns",
        nwb_type="str",
        mapping_rationale="Preserve unlisted columns.",
        stage="8",
        notes="One generic row per stream.",
    ),
    row(
        row_type="metadata_field",
        surlab_file_location="session_dir",
        surlab_filename="(no file)",
        fieldname_surlab="timestamps for behEvents",
        units="N/A",
        requirement_level="na",
        requirement_condition="if_datatype_present:<datatypeID>",
        nwb_location="NWBFile",
        nwb_fieldname="N/A",
        nwb_type="N/A",
        mapping_rationale="behEvents store times in data arrays; no separate timestamps file.",
        stage="8",
        notes="Do not require <datatypeID>_timestamps for behEvents streams.",
    ),
]


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        header = list(reader.fieldnames or HEADER)

    # Replace bare behEvents keyword row with per-stream identity rule
    updated: list[dict[str, str]] = []
    replaced_beh = False
    for existing in rows:
        field = str(existing.get("fieldname_surlab", "")).strip()
        if field == "behEvents" and str(existing.get("nwb_fieldname", "")).strip() == "keywords":
            updated.append(
                row(
                    row_type="metadata_field",
                    surlab_file_location="dataset_dir",
                    surlab_filename="sessionInfo_<datasetID>.csv",
                    fieldname_surlab="(per_stream_behEvents)",
                    units="boolean 0/1 per stream column",
                    requirement_level="optional",
                    requirement_condition="always",
                    nwb_location="NWBFile",
                    nwb_fieldname="keywords",
                    nwb_keyword="identity",
                    nwb_type="array_of_str",
                    mapping_rationale="One sessionInfo column per behEvents stream; header is full datatype ID (e.g. lick_behEvents).",
                    stage="1",
                    notes="No aggregate behEvents column. Prefer prefixed streams. See stage 8 rows.",
                )
            )
            replaced_beh = True
            continue
        # Drop previously deferred notes on lfp/spikeWaves flags
        if field == "lfp" and "deferred" in str(existing.get("notes", "")).lower():
            existing["notes"] = "When 1 expect lfp files; see stage 6 rows."
        if field == "spikeWaves" and "defer" in str(existing.get("notes", "")).lower():
            existing["notes"] = "When 1 expect spikeWaves files; see stage 7 rows."
        updated.append(existing)

    if not replaced_beh:
        print("WARNING: behEvents keyword row not found; appending per_stream rule")
        updated.insert(
            25,
            row(
                row_type="metadata_field",
                surlab_file_location="dataset_dir",
                surlab_filename="sessionInfo_<datasetID>.csv",
                fieldname_surlab="(per_stream_behEvents)",
                units="boolean 0/1 per stream column",
                requirement_level="optional",
                requirement_condition="always",
                nwb_location="NWBFile",
                nwb_fieldname="keywords",
                nwb_keyword="identity",
                nwb_type="array_of_str",
                mapping_rationale="One sessionInfo column per behEvents stream; header is full datatype ID (e.g. lick_behEvents).",
                stage="1",
                notes="No aggregate behEvents column. Prefer prefixed streams. See stage 8 rows.",
            ),
        )

    # Avoid duplicating if script re-run
    existing_keys = {
        (
            str(r.get("surlab_filename", "")),
            str(r.get("fieldname_surlab", "")),
            str(r.get("stage", "")),
            str(r.get("nwb_location", "")),
        )
        for r in updated
    }
    added = 0
    for new in NEW_ROWS:
        key = (
            new["surlab_filename"],
            new["fieldname_surlab"],
            new["stage"],
            new["nwb_location"],
        )
        if key in existing_keys:
            continue
        # Also skip if lfp_data already present
        if new["surlab_filename"].startswith("lfp_data") and any(
            str(r.get("surlab_filename", "")).startswith("lfp_data") for r in updated
        ):
            continue
        updated.append(new)
        added += 1

    _normalize_modality_placement(updated)

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in updated)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"rows={len(updated)} added={added} behEvents_replaced={replaced_beh}")


if __name__ == "__main__":
    main()
