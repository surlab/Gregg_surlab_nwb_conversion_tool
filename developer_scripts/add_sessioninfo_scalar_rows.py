"""One-off helper: add sessionInfo scalar metadata rows to sur_nwb_conversion_table.csv."""

from __future__ import annotations

import csv
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

LAYOUT_ONLY = {
    "X_dim",
    "Y_dim",
    "X_size",
    "Y_size",
    "X_idx",
    "Y_idx",
    "dataset_specific",
    "N/A",
    "NA",
}

FIXED_DATATYPE_BY_STAGE = {
    2: "spikeTimes",
}

# stage 6 scalars documented before full data rows exist
STAGE6_SESSIONINFO_SCALARS = {
    "lfp": [
        ("probe", "plain text", "recommended", "NWBFile/devices", "Device.name", "str",
         "LFP probe identity; Device linked to LFP electrodes for this stream. Same physical probe as spikeTimes may repeat value in lfp_probe."),
        ("filter_type", "plain text", "recommended", "NWBFile/processing", "custom_field", "str",
         "Filter type for LFP stream; processing custom field linked to LFP."),
        ("filter_cutoff_low__Hz", "float Hz", "recommended", "NWBFile/processing", "custom_field", "float",
         "Low cutoff paired with filter_cutoff_high__Hz."),
        ("filter_cutoff_high__Hz", "float Hz", "recommended", "NWBFile/processing", "custom_field", "float",
         "High cutoff paired with filter_cutoff_low__Hz."),
        ("data_unit_measurement", "base__unit token string", "recommended", "NWBFile/acquisition", "unit", "str",
         "Unit tag for stored LFP values."),
        ("sample_frequency__Hz", "float Hz", "recommended", "NWBFile/acquisition", "rate", "float",
         "LFP sampling rate."),
    ],
    "spikeWaves": [
        ("probe", "plain text", "recommended", "NWBFile/devices", "Device.name", "str",
         "Probe for spike waveforms; Device linked to waveform source."),
        ("clustering_algorithm", "plain text", "recommended", "NWBFile/processing", "custom_field", "str",
         "Clustering algorithm for waveforms."),
        ("sample_frequency__Hz", "float Hz", "recommended", "NWBFile/units", "custom_column_sampling_rate__Hz", "float",
         "Waveform snippet sampling rate."),
        ("data_unit_measurement", "base__unit token string", "recommended", "NWBFile/units", "custom_column_data_unit_measurement", "str",
         "Unit tag for waveform amplitudes."),
    ],
}

INFO_ROWS = [
    {
        "row_type": "metadata_field",
        "surlab_file_location": "dataset_dir",
        "surlab_filename": "sessionInfo_<datasetID>.csv",
        "fieldname_surlab": "(sessioninfo_column_order)",
        "units": "na",
        "requirement_level": "na",
        "requirement_condition": "always",
        "nwb_location": "NWBFile",
        "nwb_fieldname": "N/A",
        "nwb_keyword": "",
        "nwb_type": "N/A",
        "mapping_rationale": "Recommended sessionInfo column tiers: required session metadata; optional session metadata; stream presence flags; stream scalar metadata grouped by datatypeID; lab extras.",
        "stage": "1",
        "notes": "See documentation Recommended column order. Not a column header.",
    },
    {
        "row_type": "metadata_field",
        "surlab_file_location": "dataset_dir",
        "surlab_filename": "sessionInfo_<datasetID>.csv",
        "fieldname_surlab": "(stream_scalar_metadata_rules)",
        "units": "na",
        "requirement_level": "na",
        "requirement_condition": "always",
        "nwb_location": "NWBFile",
        "nwb_fieldname": "N/A",
        "nwb_keyword": "",
        "nwb_type": "N/A",
        "mapping_rationale": "Canonical scalar location is sessionInfo {datatypeID}_{field}. Optional legacy mirror in schema JSON unprefixed key. Read both on forward; fail if both non-empty and disagree; forward does not modify source SurLab. Reverse writes both.",
        "stage": "1",
        "notes": "X_size/Y_size not sessionInfo columns; derive from data arrays. Unlisted keys stay in schema dataset_specific.",
    },
    {
        "row_type": "metadata_field",
        "surlab_file_location": "dataset_dir",
        "surlab_filename": "sessionInfo_<datasetID>.csv",
        "fieldname_surlab": "(per_stream_scalar_metadata)",
        "units": "na",
        "requirement_level": "na",
        "requirement_condition": "always",
        "nwb_location": "NWBFile",
        "nwb_fieldname": "N/A",
        "nwb_keyword": "",
        "nwb_type": "N/A",
        "mapping_rationale": "Per-stream scalar columns use {datatypeID}_{field} in sessionInfo (e.g. GCaMP7f_traces_indicator). Table rows use <datatypeID>_field template in fieldname_surlab.",
        "stage": "1",
        "notes": "Fixed-ID streams use literal prefix (spikeTimes_probe). See stage 3/4 sessionInfo rows and stage 6 lfp/spikeWaves rows.",
    },
]


def is_scalar_schema_row(row: dict[str, str]) -> bool:
    filename = str(row.get("surlab_filename", ""))
    if "_schema.json" not in filename:
        return False
    field = str(row.get("fieldname_surlab", "")).strip()
    return field not in LAYOUT_ONLY


def sessioninfo_fieldname(row: dict[str, str]) -> str:
    field = str(row.get("fieldname_surlab", "")).strip()
    stage = str(row.get("stage", "")).strip()
    condition = str(row.get("requirement_condition", "")).strip()

    if condition.startswith("if_datatype_present:"):
        token = condition.split(":", 1)[1].strip()
        if token != "<datatypeID>":
            return f"{token}_{field}"
    if stage in FIXED_DATATYPE_BY_STAGE:
        return f"{FIXED_DATATYPE_BY_STAGE[stage]}_{field}"
    if "<datatypeID>" in str(row.get("surlab_filename", "")):
        return f"<datatypeID>_{field}"
    return field


def make_sessioninfo_row(schema_row: dict[str, str]) -> dict[str, str]:
    out = deepcopy(schema_row)
    out["surlab_file_location"] = "dataset_dir"
    out["surlab_filename"] = "sessionInfo_<datasetID>.csv"
    out["fieldname_surlab"] = sessioninfo_fieldname(schema_row)
    rationale = str(schema_row.get("mapping_rationale", "")).strip()
    field = str(schema_row.get("fieldname_surlab", "")).strip()
    out["mapping_rationale"] = (
        f"Canonical sessionInfo column. Stream-scoped NWB linkage. {rationale}"
    ).strip()
    out["stage"] = "1"
    existing = str(schema_row.get("notes", "")).strip()
    field = str(schema_row.get("fieldname_surlab", "")).strip()
    mirror_file = str(schema_row.get("surlab_filename", "")).strip()
    out["notes"] = (
        f"Legacy optional mirror: {mirror_file} key {field}. "
        "Fail if both non-empty and disagree."
    )
    if field == "probe" and str(schema_row.get("requirement_condition", "")).endswith("spikeTimes"):
        out["requirement_level"] = "required"
    stage = str(schema_row.get("stage", "")).strip()
    out["stage"] = stage if stage == "6" else "1"
    return out


def make_stage6_row(
    datatype_id: str,
    field: str,
    units: str,
    requirement_level: str,
    nwb_location: str,
    nwb_fieldname: str,
    nwb_type: str,
    mapping_rationale: str,
) -> dict[str, str]:
    return {
        "row_type": "metadata_field",
        "surlab_file_location": "dataset_dir",
        "surlab_filename": "sessionInfo_<datasetID>.csv",
        "fieldname_surlab": f"{datatype_id}_{field}",
        "units": units,
        "requirement_level": requirement_level,
        "requirement_condition": f"if_datatype_present:{datatype_id}",
        "nwb_location": nwb_location,
        "nwb_fieldname": nwb_fieldname,
        "nwb_keyword": "",
        "nwb_type": nwb_type,
        "mapping_rationale": f"Canonical sessionInfo column. Stream-scoped NWB linkage. {mapping_rationale}",
        "stage": "6",
        "notes": f"Legacy optional mirror: {datatype_id}_schema.json key {field}. Fail if both non-empty and disagree. Stage 6 data rows deferred.",
    }


def update_schema_row(row: dict[str, str]) -> dict[str, str]:
    if not is_scalar_schema_row(row):
        return row
    out = deepcopy(row)
    field = str(out.get("fieldname_surlab", "")).strip()
    canonical = sessioninfo_fieldname(row)
    legacy = (
        f"Legacy optional mirror of sessionInfo {canonical}. "
        "Fail if both non-empty and disagree."
    )
    existing = str(out.get("notes", "")).strip()
    out["notes"] = f"{legacy} {existing}".strip()
    if field == "probe":
        out["requirement_level"] = "optional"
    out["mapping_rationale"] = (
        str(out.get("mapping_rationale", "")).strip()
        + " Optional legacy mirror; canonical column in sessionInfo."
    ).strip()
    return out


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = list(reader)

    updated: list[dict[str, str]] = []
    new_sessioninfo: list[dict[str, str]] = []
    seen_sessioninfo: set[str] = set()

    for row in rows:
        if is_scalar_schema_row(row):
            row = update_schema_row(row)
            session_row = make_sessioninfo_row(row)
            key = (
                session_row["fieldname_surlab"],
                session_row["requirement_condition"],
                session_row["stage"],
            )
            if key not in seen_sessioninfo:
                seen_sessioninfo.add(key)
                new_sessioninfo.append(session_row)
        updated.append(row)

    insert_at = None
    for index, row in enumerate(updated):
        if str(row.get("fieldname_surlab", "")).strip() == "dataset_specific":
            insert_at = index
            break
    if insert_at is None:
        raise RuntimeError("Could not find dataset_specific row")

    tier4_fixed: list[dict[str, str]] = []
    tier4_template: list[dict[str, str]] = []
    for row in new_sessioninfo:
        fieldname = str(row.get("fieldname_surlab", ""))
        if fieldname.startswith("<datatypeID>_"):
            tier4_template.append(row)
        else:
            tier4_fixed.append(row)

    def sort_key(row: dict[str, str]) -> tuple:
        field = str(row.get("fieldname_surlab", ""))
        return (field.split("_", 1)[0], field)

    tier4_fixed.sort(key=sort_key)
    tier4_template.sort(key=lambda r: str(r.get("fieldname_surlab", "")))

    stage6_rows: list[dict[str, str]] = []
    for datatype_id, specs in STAGE6_SESSIONINFO_SCALARS.items():
        for spec in specs:
            stage6_rows.append(make_stage6_row(datatype_id, *spec))

    block = INFO_ROWS + tier4_fixed + stage6_rows + tier4_template
    final = updated[:insert_at] + block + updated[insert_at:]

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(final)

    print(f"Wrote {len(final)} rows ({len(block)} inserted before dataset_specific)")


if __name__ == "__main__":
    main()
