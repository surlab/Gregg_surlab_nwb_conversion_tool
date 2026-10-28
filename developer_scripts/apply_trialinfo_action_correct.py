"""Apply trialInfo action / correct / trial_type conventions to conversion table."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

ACTION_ROW = {
    "row_type": "metadata_field",
    "surlab_file_location": "session_dir",
    "surlab_filename": "trialInfo.csv",
    "fieldname_surlab": "action",
    "units": "categorical behavioral label (extensible verb list)",
    "requirement_level": "optional",
    "requirement_condition": "if_datatype_present:trialInfo",
    "nwb_location": "NWBFile/intervals/trials",
    "nwb_fieldname": "custom_column_action",
    "nwb_alt_fieldnames": "output",
    "nwb_type": "str",
    "mapping_rationale": "What the animal did on the trial. Replaces legacy column output.",
    "stage": "5",
    "notes": (
        "Examples (extendable, not a closed enum): press, early_press, no_press, lick, "
        "early_lick, left_lick, right_lick, no_lick. early_press belongs here only — "
        "not in correct or trial_type. Legacy ingest: header output is alias for action "
        "(same values). Reverse writes canonical column action."
    ),
}

TRIAL_TYPE_ROW = {
    "row_type": "metadata_field",
    "surlab_file_location": "session_dir",
    "surlab_filename": "trialInfo.csv",
    "fieldname_surlab": "trial_type",
    "units": "SDT-style outcome when applicable",
    "requirement_level": "optional",
    "requirement_condition": "if_datatype_present:trialInfo",
    "nwb_location": "NWBFile/intervals/trials",
    "nwb_fieldname": "custom_column_trial_type",
    "nwb_type": "str",
    "mapping_rationale": "Hit/miss/fa/cr convenience label; optional when no SDT scoring.",
    "stage": "5",
    "notes": (
        "When present: hit, miss, fa, cr, or aborted (trial occurred but not classic SDT, "
        "e.g. early_press trials). early_press is NOT a trial_type value. Omit column for "
        "passive viewing with no SDT labels. Condition (go/nogo) may stay dataset_specific "
        "until a canonical name is chosen — not required with trial_type."
    ),
}

CORRECT_NOTES = (
    "When scored: correct or incorrect (verbose strings, not 0/1). Missing/nan when no "
    "operant correctness (passive viewing, early_press trials, etc.). early_press must NOT "
    "appear in correct. Legacy ingest aliases: error→incorrect; 0/1→incorrect/correct. "
    "Reverse writes canonical strings correct|incorrect or empty."
)

POLICY_ROW = {
    "row_type": "metadata_field",
    "surlab_file_location": "session_dir",
    "surlab_filename": "trialInfo.csv",
    "fieldname_surlab": "(trialinfo_action_correct_trial_type)",
    "units": "N/A",
    "requirement_level": "na",
    "requirement_condition": "if_datatype_present:trialInfo",
    "nwb_location": "NWBFile",
    "nwb_fieldname": "N/A",
    "nwb_type": "N/A",
    "mapping_rationale": (
        "Four optional layers: condition (go/nogo, dataset_specific for now); action "
        "(what animal did); trial_type (SDT + aborted); correct (operant score when "
        "applicable). Early press: action=early_press, correct missing, trial_type=aborted."
    ),
    "stage": "5",
    "notes": "Resolves for_cursor/task1_handoff_trialinfo_action_correct.txt.",
}


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    updated: list[dict[str, str]] = []
    saw_action = False
    saw_trial_type = False
    saw_policy = False

    for row in rows:
        field = str(row.get("fieldname_surlab", "")).strip()
        if field == "output":
            continue
        if field == "action":
            saw_action = True
            row.update({k: ACTION_ROW[k] for k in ACTION_ROW if k in header})
        if field == "trial_type":
            saw_trial_type = True
        if field == "(trialinfo_action_correct_trial_type)":
            saw_policy = True
        if field == "correct":
            row["units"] = "operant correctness when scored; missing when unscored"
            row["nwb_type"] = "str"
            row["mapping_rationale"] = (
                "Operant trial outcome when a correctness judgment applies; empty when unscored."
            )
            row["notes"] = CORRECT_NOTES
        if field == "(format_validation_nwb_type_rules)":
            notes = str(row.get("notes", ""))
            if "trialInfo correct/trial_type still open" in notes:
                row["notes"] = notes.replace(
                    "trialInfo correct/trial_type still open (separate consensus).",
                    "trialInfo action/correct/trial_type resolved (see stage 5).",
                )
        updated.append(row)

    insert_at = next(
        (i for i, r in enumerate(updated) if r.get("fieldname_surlab") == "dataset_specific"
         and "trialInfo" in str(r.get("surlab_filename", ""))),
        len(updated),
    )
    if not saw_policy:
        updated.insert(insert_at, {k: POLICY_ROW.get(k, "") for k in header})
        insert_at += 1
    if not saw_trial_type:
        updated.insert(insert_at, {k: TRIAL_TYPE_ROW.get(k, "") for k in header})
        insert_at += 1
    if not saw_action:
        updated.insert(insert_at, {k: ACTION_ROW.get(k, "") for k in header})

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in updated)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"rows={len(updated)}")


if __name__ == "__main__":
    main()
