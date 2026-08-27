"""Fix stage and notes on sessionInfo scalar rows after add_sessioninfo_scalar_rows.py."""

from __future__ import annotations

import csv
import re
from pathlib import Path

TABLE = Path(__file__).resolve().parents[1] / "sur_nwb_conversion_table.csv"

SESSIONINFO_CORE = {
    "animal_ID",
    "session_ID",
    "session_date",
    "age__days",
    "related_publication",
    "zero_time",
}


def legacy_mirror_note(fieldname: str) -> str:
    if fieldname.startswith("<datatypeID>_"):
        schema_key = fieldname.split("_", 1)[1]
        mirror_file = "<datatypeID>_schema.json"
    else:
        datatype_id, schema_key = fieldname.split("_", 1)
        mirror_file = f"{datatype_id}_schema.json"
    return (
        f"Legacy optional mirror: {mirror_file} key {schema_key}. "
        "Fail if both non-empty and disagree."
    )


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    for row in rows:
        filename = str(row.get("surlab_filename", ""))
        fieldname = str(row.get("fieldname_surlab", "")).strip()
        if "sessionInfo" not in filename or not fieldname or fieldname.startswith("("):
            continue
        if fieldname in SESSIONINFO_CORE:
            continue
        if fieldname.startswith("<datatypeID>_") or (
            "_" in fieldname and not fieldname.endswith("_metadata")
        ):
            if str(row.get("stage", "")).strip() != "6":
                row["stage"] = "1"
            row["notes"] = legacy_mirror_note(fieldname)
            rationale = str(row.get("mapping_rationale", "")).replace(
                " Optional legacy mirror; canonical column in sessionInfo.", ""
            )
            row["mapping_rationale"] = rationale.strip()

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print("patched sessionInfo scalar rows")


if __name__ == "__main__":
    main()
