"""Apply Task 1 ophys microscope Device placement (traces / stage 3)."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

DEVICES = "NWBFile/devices"
MICROSCOPE_NOTE = (
    "Examples: Bruker_Ultima, Thorlabs_Bergamo_II, Femtonics_Atlas. "
    "Short instrument identity for Device.name — not objectives/detection_software. "
    "Same physical scope: repeat value on each traces stream; Task 2 dedupes one NWB Device."
)
DESCRIPTION_NOTE = (
    "Optional rig notes (galvo/resonant path, room nickname, manufacturer/model text). "
    "Do not duplicate detection_software here."
)


def _blank_row(header: list[str]) -> dict[str, str]:
    return {key: "" for key in header}


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    for row in rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if field == "(per_stream_SurLabSchema_LabMetaData)":
            row["mapping_rationale"] = (
                "Policy: one LabMetaData container per <datatypeID> stream on "
                "NWBFile.lab_meta_data. Holds resolved SurLab leftovers with no honest "
                "core NWB home (sessionInfo-first; optional schema mirror shares the same "
                "target). Layout keys are validate_only. Core ophys path: RoiResponseSeries "
                "data/timestamps/unit; ImagingPlane.imaging_rate; OpticalChannel.name/"
                "emission_lambda; microscope Device.name from {datatypeID}_microscope when "
                "present (ImagingPlane.device link). Do not put leftovers in description "
                "strings. Two simultaneous FOVs require two datatypeID streams (or per-ROI "
                "metadata), not two FOV values in one stream container."
            )
            row["notes"] = (
                "Applies first to traces (stage 3); behTSeries core uses TimeSeries + "
                "features table (stage 4); LFP uses SurLabSchema_lfp, spikeWaves uses "
                "SurLabSchema_spikeWaves (stages 6–7). Microscope Device: sourced from SurLab "
                "when {datatypeID}_microscope present; MISSING_REQUIRED_FOR_NWB placeholder "
                "when absent. Other ImagingPlane geometry (location, grid_spacing, …) may "
                "still use MISSING markers when SurLab lacks honest values."
            )
            continue

        if field == "(behTSeries_TimeSeries_and_features_table)":
            continue

    marker = "(traces_microscope_Device_and_ImagingPlane)"
    if not any(str(r.get("fieldname_surlab", "")).strip() == marker for r in rows):
        insert_at = next(
            (
                i
                for i, r in enumerate(rows)
                if str(r.get("stage", "")).strip() == "3"
                and str(r.get("row_type", "")).strip() == "data_array"
            ),
            len(rows),
        )
        policy = _blank_row(header)
        policy.update(
            {
                "row_type": "metadata_field",
                "surlab_file_location": "session_dir",
                "surlab_filename": "<datatypeID>_data.{mat|npz}",
                "fieldname_surlab": marker,
                "units": "N/A",
                "requirement_level": "na",
                "requirement_condition": "if_datatype_present:<datatypeID>",
                "nwb_location": DEVICES,
                "nwb_fieldname": "N/A",
                "nwb_type": "N/A",
                "mapping_rationale": (
                    "Policy (stage 3 traces): microscope identity from sessionInfo "
                    "{datatypeID}_microscope → stock Device.name; optional "
                    "{datatypeID}_microscope_description → Device.description. "
                    "ImagingPlane.device links to that Device for this stream. One NWB Device "
                    "per distinct name (shared when multiple traces streams repeat the same "
                    "value). When column absent, Task 2 uses MISSING_REQUIRED_FOR_NWB device "
                    "name. Read/write via ImagingPlane.device for stream-scoped linkage — not "
                    "first device in file. objectives/detection_software/indicator stay in "
                    "SurLabSchema / OpticalChannel — not Device.name."
                ),
                "stage": "3",
                "notes": "Resolves for_cursor/task1_handoff_ophys_microscope_device.txt.",
            }
        )
        rows.insert(insert_at, policy)

    session_rows = [
        {
            "fieldname_surlab": "<datatypeID>_microscope",
            "units": "plain text (short instrument identity)",
            "requirement_level": "recommended",
            "nwb_fieldname": "Device.name",
            "mapping_rationale": (
                "Canonical sessionInfo column. Microscope / imaging rig identity for "
                "ImagingPlane.device. Per-stream column; repeat same value when streams "
                "share one scope. Not objectives, detection_software, or indicator."
            ),
            "notes": (
                f"{MICROSCOPE_NOTE} Legacy optional mirror: <datatypeID>_schema.json key "
                "microscope. Fail if both non-empty and disagree. Validator warns when "
                "multiple traces streams both set microscope and values differ."
            ),
        },
        {
            "fieldname_surlab": "<datatypeID>_microscope_description",
            "units": "plain text (optional rig notes)",
            "requirement_level": "optional",
            "nwb_fieldname": "Device.description",
            "mapping_rationale": (
                "Optional extended hardware notes on the microscope Device linked from "
                "ImagingPlane.device. Manufacturer/model text acceptable here until "
                "structured DeviceModel columns exist."
            ),
            "notes": (
                f"{DESCRIPTION_NOTE} Legacy optional mirror: <datatypeID>_schema.json key "
                "microscope_description. Fail if both non-empty and disagree."
            ),
        },
    ]

    if not any(
        str(r.get("fieldname_surlab", "")).strip() == "<datatypeID>_microscope"
        for r in rows
    ):
        insert_at = next(
            (
                i
                for i, r in enumerate(rows)
                if str(r.get("fieldname_surlab", "")).strip() == "<datatypeID>_indicator"
            ),
            len(rows),
        )
        for offset, spec in enumerate(session_rows):
            new_row = _blank_row(header)
            new_row.update(
                {
                    "row_type": "metadata_field",
                    "surlab_file_location": "dataset_dir",
                    "surlab_filename": "sessionInfo_<datasetID>.csv",
                    "fieldname_surlab": spec["fieldname_surlab"],
                    "units": spec["units"],
                    "requirement_level": spec["requirement_level"],
                    "requirement_condition": "if_datatype_present:<datatypeID>",
                    "nwb_location": DEVICES,
                    "nwb_fieldname": spec["nwb_fieldname"],
                    "nwb_type": "str",
                    "mapping_rationale": spec["mapping_rationale"],
                    "stage": "1",
                    "notes": spec["notes"],
                }
            )
            rows.insert(insert_at + 1 + offset, new_row)

    schema_rows = [
        {
            "fieldname_surlab": "microscope",
            "session_field": "<datatypeID>_microscope",
            "nwb_fieldname": "Device.name",
            "requirement_level": "optional",
            "mapping_rationale": (
                "Optional legacy schema mirror; same Device.name target as sessionInfo "
                "{datatypeID}_microscope."
            ),
        },
        {
            "fieldname_surlab": "microscope_description",
            "session_field": "<datatypeID>_microscope_description",
            "nwb_fieldname": "Device.description",
            "requirement_level": "optional",
            "mapping_rationale": (
                "Optional legacy schema mirror; same Device.description as sessionInfo "
                "{datatypeID}_microscope_description."
            ),
        },
    ]

    if not any(
        str(r.get("surlab_filename", "")).strip() == "<datatypeID>_schema.json"
        and str(r.get("fieldname_surlab", "")).strip() == "microscope"
        for r in rows
    ):
        insert_at = next(
            (
                i
                for i, r in enumerate(rows)
                if str(r.get("surlab_filename", "")).strip() == "<datatypeID>_schema.json"
                and str(r.get("fieldname_surlab", "")).strip() == "objectives"
            ),
            len(rows),
        )
        for offset, spec in enumerate(schema_rows):
            new_row = _blank_row(header)
            new_row.update(
                {
                    "row_type": "metadata_field",
                    "surlab_file_location": "session_dir",
                    "surlab_filename": "<datatypeID>_schema.json",
                    "fieldname_surlab": spec["fieldname_surlab"],
                    "units": "plain text",
                    "requirement_level": spec["requirement_level"],
                    "requirement_condition": "if_datatype_present:<datatypeID>",
                    "nwb_location": DEVICES,
                    "nwb_fieldname": spec["nwb_fieldname"],
                    "nwb_type": "str",
                    "mapping_rationale": spec["mapping_rationale"],
                    "stage": "3",
                    "notes": (
                        f"Legacy optional mirror of sessionInfo {spec['session_field']}. "
                        "Fail if both non-empty and disagree."
                    ),
                }
            )
            rows.insert(insert_at + 1 + offset, new_row)

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in rows)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"Updated {TABLE} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
