"""Tighten nwb_type notes: length rules, data/timestamps validation depth."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

LAYOUT_LEN = (
    "Length rule: when present, len(X_idx)==X_size and len(Y_idx)==Y_size "
    "(if those size keys are present). Format validator enforces; conversion ignores."
)
DATA_CHECK = (
    "Format validation: file must be present (when required) and loadable; "
    "basic dtype numeric/float-compatible. Shape vs schema/timestamps checked when "
    "X_size/Y_size or timestamps exist (warn/fail per validator); not presence-only."
)
TS_CHECK = (
    "Format validation: file must be present (when required) and loadable; "
    "1-D float times. Length should match data axis-0 when data is present."
)
QUALITY_NOTE = (
    "Type float_or_str: numeric → quality score; non-empty string → categorical label; "
    "empty/missing → omit. Meaning from quality_metric / spikeTimes_quality_metric. "
    "Not free-form untyped."
)
VALIDATE_ONLY_CLARIFY = (
    "nwb_fieldname=validate_only means: SurLab format validator STILL type-checks "
    "the SurLab value; conversion does not write it to NWB. "
    "To skip type-checking entirely use nwb_type=N/A (not validate_only)."
)


def append_note(row: dict[str, str], text: str) -> None:
    notes = str(row.get("notes", "") or "").strip()
    if text in notes:
        return
    row["notes"] = f"{notes} {text}".strip() if notes else text


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    for row in rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        row_type = str(row.get("row_type", "")).strip()
        nwb_field = str(row.get("nwb_fieldname", "")).strip()
        nwb_type = str(row.get("nwb_type", "")).strip()

        if field in {"X_idx", "Y_idx", "X_size", "Y_size"}:
            append_note(row, LAYOUT_LEN)
            if nwb_field == "validate_only":
                append_note(row, VALIDATE_ONLY_CLARIFY)

        if field in {"X_dim", "Y_dim"} and nwb_field == "validate_only":
            append_note(row, VALIDATE_ONLY_CLARIFY)

        if row_type == "data_array" and nwb_type.startswith("array_of_"):
            append_note(row, DATA_CHECK)

        if row_type == "timestamps_array" and nwb_type.startswith("array_of_"):
            append_note(row, TS_CHECK)

        if field == "quality" and nwb_type == "float_or_str":
            # replace thin note with full policy if needed
            if "numeric → quality score" not in str(row.get("notes", "")):
                row["notes"] = QUALITY_NOTE

    # Policy row for format-validation depth
    marker = "(format_validation_nwb_type_rules)"
    if not any(str(r.get("fieldname_surlab", "")).strip() == marker for r in rows):
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
                "nwb_location": "NWBFile",
                "nwb_fieldname": "N/A",
                "nwb_type": "N/A",
                "mapping_rationale": (
                    "Policy for SurLab format validator (Task 5): never use bare nwb_type "
                    "variable or array. Use unions (float_or_str) or element-qualified arrays. "
                    "data_array/timestamps_array: presence + loadable + basic dtype; shape/"
                    "length checks when schema sizes or paired timestamps exist. "
                    "nwb_fieldname=validate_only still type-checks SurLab values; "
                    "nwb_type=N/A skips type-check. Demo: demo_data/surlab_format_demo."
                ),
                "stage": "1",
                "notes": (
                    "Resolves for_cursor/task1_handoff_nwb_type_precision.txt. "
                    "trialInfo correct/trial_type still open (separate consensus)."
                ),
            }
        )
        rows.insert(1, policy)

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in rows)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"rows={len(rows)}")


if __name__ == "__main__":
    main()
