"""Apply Task 1 LabMetaData / validate_only placement for ophys traces (stage 3)."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

LAB_META_LOC = "NWBFile/lab_meta_data/SurLabSchema_<datatypeID>"

# sessionInfo / schema key (unprefixed) -> (nwb_location, nwb_fieldname, rationale_extra)
# Only fields with no honest core NWB home.
LEFTOVER_KEYS = {
    "detection_software": (LAB_META_LOC, "detection_software"),
    "fov_depth__um": (LAB_META_LOC, "fov_depth__um"),
    "fov_height__pixels": (LAB_META_LOC, "fov_height__pixels"),
    "fov_width__pixels": (LAB_META_LOC, "fov_width__pixels"),
    "laser_name": (LAB_META_LOC, "laser_name"),
    "objectives": (LAB_META_LOC, "objectives"),
    "pixel_size__um": (LAB_META_LOC, "pixel_size__um"),
    "pixel_size__au": (LAB_META_LOC, "pixel_size__au"),
    "pixel_size_calibration": (LAB_META_LOC, "pixel_size_calibration"),
}

LAYOUT_KEYS = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}

VALIDATE_NOTE = (
    "validate_only: checked by SurLab format validator "
    "(scripts/run_surlab_format_validation.py / src/validator.py); "
    "ignored by SurLab→NWB conversion (not written to NWB)."
)

MIRROR_NOTE = (
    "Same single NWB target as sessionInfo column (no second write). "
    "SurLab dual-read: fail if sessionInfo and schema both non-empty and disagree."
)

SCAFFOLD_NOTE = (
    "Required PyNWB scaffolding SurLab does not supply (Device, ImagingPlane geometry, etc.): "
    "use explicit MISSING_REQUIRED_FOR_NWB markers — do not invent scientific values."
)


def _unprefixed(field: str) -> str:
    field = field.strip()
    if field.startswith("<datatypeID>_"):
        return field[len("<datatypeID>_") :]
    return field


def _is_traces_ophys_sessioninfo_row(row: dict) -> bool:
    """Ophys leftover / core rows live on sessionInfo with ImagingPlane or OpticalChannel today."""
    loc = str(row.get("nwb_location", ""))
    fname = str(row.get("surlab_filename", ""))
    return fname.startswith("sessionInfo") and (
        "ImagingPlane" in loc or "OpticalChannel" in loc or "RoiResponseSeries" in loc
    )


def _is_traces_schema_row(row: dict) -> bool:
    return str(row.get("surlab_filename", "")).strip() == "<datatypeID>_schema.json" and str(
        row.get("stage", "")
    ).strip() == "3"


def _is_spike_layout_row(row: dict) -> bool:
    return (
        str(row.get("surlab_filename", "")).strip() == "spikeTimes_schema.json"
        and str(row.get("fieldname_surlab", "")).strip() in LAYOUT_KEYS
    )


def update_row(row: dict) -> None:
    field = str(row.get("fieldname_surlab", "")).strip()
    key = _unprefixed(field)
    stage = str(row.get("stage", "")).strip()
    fname = str(row.get("surlab_filename", "")).strip()
    loc = str(row.get("nwb_location", "")).strip()

    # --- sessionInfo ophys leftovers + core attribute upgrades ---
    if fname.startswith("sessionInfo") and field.startswith("<datatypeID>_"):
        if key in LEFTOVER_KEYS:
            new_loc, new_field = LEFTOVER_KEYS[key]
            row["nwb_location"] = new_loc
            row["nwb_fieldname"] = new_field
            row["mapping_rationale"] = (
                "Canonical sessionInfo column. One NWB target: per-stream LabMetaData leftover "
                f"(no honest core NWB attribute). Container SurLabSchema_<datatypeID>."
            )
            notes = str(row.get("notes", "")).strip()
            if "LabMetaData" not in notes:
                row["notes"] = (
                    f"{notes} One target only; optional schema mirror shares this path. "
                    f"{SCAFFOLD_NOTE}"
                ).strip()
            return
        if key == "indicator":
            row["nwb_location"] = "NWBFile/ophys/OpticalChannel"
            row["nwb_fieldname"] = "name"
            row["mapping_rationale"] = (
                "Canonical sessionInfo column. OpticalChannel.name = indicator string "
                "(one target; not LabMetaData)."
            )
            return
        if key == "sample_frequency__Hz" and "ImagingPlane" in loc:
            row["nwb_location"] = "NWBFile/ophys/ImagingPlane"
            row["nwb_fieldname"] = "imaging_rate"
            row["mapping_rationale"] = (
                "Canonical sessionInfo column. ImagingPlane.imaging_rate when present; "
                "timestamps remain authoritative for conversion."
            )
            return
        if key == "data_unit_measurement" and "RoiResponseSeries" in loc:
            # already correct target
            return
        if key == "wavelength__nm":
            # already emission_lambda
            return

    # --- stage 3 schema.json ---
    if _is_traces_schema_row(row):
        if key in LAYOUT_KEYS:
            row["nwb_location"] = "NWBFile"
            row["nwb_fieldname"] = "validate_only"
            row["nwb_type"] = row.get("nwb_type") or "str"
            row["mapping_rationale"] = (
                "Layout / validate-only: implied by data array + timestamps + metadata row count. "
                "Do not duplicate into NWB."
            )
            row["notes"] = VALIDATE_NOTE
            if key == "X_idx":
                row["notes"] = (
                    VALIDATE_NOTE
                    + " If present alongside timestamps, format validator may warn on mismatch; "
                    "conversion ignores X_idx."
                )
            if key in {"X_size", "Y_size"}:
                row["notes"] = (
                    VALIDATE_NOTE
                    + " Prefer derive from data.shape / metadata rows; schema sizes are check-only."
                )
            return
        if key in LEFTOVER_KEYS:
            new_loc, new_field = LEFTOVER_KEYS[key]
            row["nwb_location"] = new_loc
            row["nwb_fieldname"] = new_field
            row["mapping_rationale"] = (
                "Optional legacy schema mirror of sessionInfo; same single LabMetaData target "
                "(no second NWB write)."
            )
            row["notes"] = MIRROR_NOTE
            return
        if key == "indicator":
            row["nwb_location"] = "NWBFile/ophys/OpticalChannel"
            row["nwb_fieldname"] = "name"
            row["mapping_rationale"] = (
                "Optional legacy schema mirror; same OpticalChannel.name target as sessionInfo."
            )
            row["notes"] = MIRROR_NOTE
            return
        if key == "sample_frequency__Hz":
            row["nwb_location"] = "NWBFile/ophys/ImagingPlane"
            row["nwb_fieldname"] = "imaging_rate"
            row["mapping_rationale"] = (
                "Optional legacy schema mirror; same ImagingPlane.imaging_rate target as sessionInfo. "
                "Timestamps remain authoritative."
            )
            row["notes"] = MIRROR_NOTE
            return
        if key == "data_unit_measurement":
            row["nwb_location"] = "NWBFile/ophys/RoiResponseSeries"
            row["nwb_fieldname"] = "unit"
            row["mapping_rationale"] = (
                "Optional legacy schema mirror; same RoiResponseSeries.unit as sessionInfo."
            )
            row["notes"] = MIRROR_NOTE
            return
        if key == "wavelength__nm":
            row["nwb_location"] = "NWBFile/ophys/OpticalChannel"
            row["nwb_fieldname"] = "emission_lambda"
            row["mapping_rationale"] = (
                "Optional legacy schema mirror; same OpticalChannel.emission_lambda as sessionInfo."
            )
            row["notes"] = MIRROR_NOTE
            return
        if key == "dataset_specific":
            row["nwb_location"] = LAB_META_LOC
            row["nwb_fieldname"] = "*"
            row["mapping_rationale"] = (
                "Unlisted schema keys → same per-stream LabMetaData container (wildcard). "
                "Not written to RoiResponseSeries.description."
            )
            row["notes"] = (
                "One generic row. Key/value (or JSON object) inside SurLabSchema_<datatypeID>. "
                f"{SCAFFOLD_NOTE}"
            )
            return

    # --- spikeTimes layout: validate_only for consistency ---
    if _is_spike_layout_row(row):
        row["nwb_location"] = "NWBFile"
        row["nwb_fieldname"] = "validate_only"
        row["mapping_rationale"] = (
            "Layout / validate-only for spikeTimes schema; not written to NWB Units."
        )
        row["notes"] = VALIDATE_NOTE
        return

    # --- ROI id: PlaneSegmentation ---
    if (
        stage == "3"
        and fname == "<datatypeID>_metadata.csv"
        and field == "roi_ID"
    ):
        row["nwb_location"] = "NWBFile/ophys/PlaneSegmentation"
        row["nwb_fieldname"] = "id"
        row["mapping_rationale"] = (
            "ROI identity → PlaneSegmentation row id; order matches data array ROI dimension."
        )
        return


def ensure_policy_row(rows: list[dict], header: list[str]) -> None:
    marker = "(per_stream_SurLabSchema_LabMetaData)"
    if any(str(r.get("fieldname_surlab", "")).strip() == marker for r in rows):
        return
    # Insert after per_stream_scalar_metadata if present
    policy = {key: "" for key in header}
    policy.update(
        {
            "row_type": "metadata_field",
            "surlab_file_location": "dataset_dir",
            "surlab_filename": "sessionInfo_<datasetID>.csv",
            "fieldname_surlab": marker,
            "units": "N/A",
            "requirement_level": "na",
            "requirement_condition": "always",
            "nwb_location": "NWBFile/lab_meta_data",
            "nwb_fieldname": "SurLabSchema_<datatypeID>",
            "nwb_type": "N/A",
            "mapping_rationale": (
                "Policy: one LabMetaData container per <datatypeID> stream on NWBFile.lab_meta_data. "
                "Holds resolved SurLab leftovers with no honest core NWB home (sessionInfo-first; "
                "optional schema mirror shares the same target). Layout keys are validate_only. "
                "Core ophys path: RoiResponseSeries data/timestamps/unit; ImagingPlane.imaging_rate; "
                "OpticalChannel.name/emission_lambda. Do not put leftovers in description strings. "
                "Two simultaneous FOVs require two datatypeID streams (or per-ROI metadata), "
                "not two FOV values in one stream container."
            ),
            "stage": "1",
            "notes": (
                "Applies first to traces (stage 3). Same pattern later for behTSeries/LFP. "
                f"{SCAFFOLD_NOTE} See docs/nwb_conversion_notes.md."
            ),
        }
    )
    insert_at = len(rows)
    for i, r in enumerate(rows):
        if str(r.get("fieldname_surlab", "")).strip() == "(per_stream_scalar_metadata)":
            insert_at = i + 1
            break
    rows.insert(insert_at, policy)


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    for row in rows:
        update_row(row)
    ensure_policy_row(rows, header)

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in header})

    cursor_copy = ROOT / "for_cursor" / "sur_nwb_conversion_table.csv"
    if cursor_copy.parent.is_dir():
        shutil.copy2(TABLE, cursor_copy)
    print(f"Updated {TABLE} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
