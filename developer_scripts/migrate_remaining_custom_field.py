"""Migrate remaining nwb_fieldname=custom_field to LabMetaData or validate_only."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

VALIDATE_NOTE = (
    "validate_only: checked by SurLab format validator "
    "(scripts/run_surlab_format_validation.py / src/validator.py); "
    "ignored by SurLab→NWB conversion (not written to NWB)."
)
MIRROR_NOTE = (
    "Same single NWB target as sessionInfo column (no second write). "
    "SurLab dual-read: fail if sessionInfo and schema both non-empty and disagree."
)

LAYOUT = {"X_dim", "Y_dim", "X_size", "Y_size", "X_idx", "Y_idx"}
SPIKE_FILTER = {"filter_type", "filter_cutoff_low__Hz", "filter_cutoff_high__Hz"}
LAB_SPIKE = "NWBFile/lab_meta_data/SurLabSchema_spikeTimes"
LAB_WAVES = "NWBFile/lab_meta_data/SurLabSchema_spikeWaves"
LAB_STREAM = "NWBFile/lab_meta_data/SurLabSchema_<datatypeID>"


def migrate(row: dict[str, str]) -> bool:
    if str(row.get("nwb_fieldname", "")).strip() != "custom_field":
        return False

    field = str(row.get("fieldname_surlab", "")).strip()
    fname = str(row.get("surlab_filename", "")).strip()
    stage = str(row.get("stage", "")).strip()
    key = field[len("spikeTimes_") :] if field.startswith("spikeTimes_") else field

    # spikeTimes filters
    if key in SPIKE_FILTER and (
        fname.startswith("sessionInfo") or fname == "spikeTimes_schema.json"
    ):
        row["nwb_location"] = LAB_SPIKE
        row["nwb_fieldname"] = key
        if fname.startswith("sessionInfo"):
            row["mapping_rationale"] = (
                "Canonical sessionInfo; one LabMetaData target SurLabSchema_spikeTimes "
                "(no core NWB filter object)."
            )
        else:
            row["mapping_rationale"] = (
                "Optional legacy schema mirror; same SurLabSchema_spikeTimes LabMetaData target."
            )
            row["notes"] = MIRROR_NOTE
        return True

    # behTSeries / behEvents layout
    if field in LAYOUT and stage in {"4", "8"}:
        row["nwb_location"] = "NWBFile"
        row["nwb_fieldname"] = "validate_only"
        row["mapping_rationale"] = (
            "Layout / validate-only; implied by data + timestamps/metadata. Do not write to NWB."
        )
        row["notes"] = VALIDATE_NOTE
        return True

    # stream schema dataset_specific (behTSeries stage 4, behEvents stage 8)
    if field == "dataset_specific" and stage in {"4", "8"}:
        row["nwb_location"] = LAB_STREAM
        row["nwb_fieldname"] = "*"
        row["mapping_rationale"] = (
            "Unlisted schema keys → per-stream SurLabSchema_<datatypeID> LabMetaData (wildcard). "
            "Not written to description / acquisition custom_field."
        )
        row["notes"] = "One generic row per stream. Key/value or JSON object inside LabMetaData."
        return True

    # optional spikeWaves snippet timestamps (not session clock)
    if fname.startswith("spikeWaves_timestamps"):
        row["nwb_location"] = LAB_WAVES
        row["nwb_fieldname"] = "snippet_timestamps"
        row["mapping_rationale"] = (
            "Optional snippet-relative sample grid (not session clock). "
            "Stored in SurLabSchema_spikeWaves LabMetaData; prefer sample_frequency__Hz when enough."
        )
        row["notes"] = (
            "Not session-origin timestamps. Omit if spikeWaves_sample_frequency__Hz documents the axis."
        )
        return True

    return False


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    changed = 0
    leftover = []
    for row in rows:
        if migrate(row):
            changed += 1
        elif str(row.get("nwb_fieldname", "")).strip() == "custom_field":
            leftover.append(
                (
                    row.get("surlab_filename"),
                    row.get("fieldname_surlab"),
                    row.get("stage"),
                )
            )

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in rows)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"changed={changed} remaining_custom_field={len(leftover)}")
    for item in leftover:
        print("  leftover:", item)


if __name__ == "__main__":
    main()
