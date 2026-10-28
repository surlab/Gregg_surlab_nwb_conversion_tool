"""Apply Task 1 spikeWaves area column policy (not-recommended mal-pattern)."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

AREA_NOTE = (
    "Mal-pattern (not-recommended): region labels belong on spikeTimes_metadata "
    "area → Units.brain_area only. Do not add area to new spikeWaves exports. "
    "If column present: validator warns; values must match spikeTimes_metadata "
    "area for the same unit_ID (fail on mismatch). Forward conversion does not "
    "write spikeWaves area to NWB."
)


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    for row in rows:
        if (
            str(row.get("surlab_filename", "")).strip() == "spikeWaves_metadata.csv"
            and str(row.get("fieldname_surlab", "")).strip() == "area"
        ):
            row["requirement_level"] = "not-recommended"
            row["nwb_location"] = "NWBFile"
            row["nwb_fieldname"] = "validate_only"
            row["nwb_alt_fieldnames"] = ""
            row["mapping_rationale"] = (
                "Do not use: per-unit brain region belongs on spikeTimes_metadata "
                "area only (NWB Units.brain_area). Waveform snippets reference the "
                "same sorted units."
            )
            row["notes"] = AREA_NOTE
            continue

        if (
            str(row.get("fieldname_surlab", "")).strip() == "unit_ID"
            and str(row.get("surlab_filename", "")).strip() == "spikeWaves_metadata.csv"
        ):
            notes = str(row.get("notes", "")).strip()
            tip = "Region labels: spikeTimes_metadata area only; see not-recommended area row."
            if tip not in notes:
                row["notes"] = f"{notes} {tip}".strip()
            continue

        if (
            str(row.get("fieldname_surlab", "")).strip() == "primary_channel"
            and str(row.get("surlab_filename", "")).strip() == "spikeWaves_metadata.csv"
        ):
            notes = str(row.get("notes", "")).strip()
            tip = "Region labels: use spikeTimes_metadata area only."
            if "not-recommended area" in notes:
                row["notes"] = tip
            continue

    if not any(
        str(r.get("surlab_filename", "")).strip() == "spikeWaves_metadata.csv"
        and str(r.get("fieldname_surlab", "")).strip() == "area"
        for r in rows
    ):
        insert_at = next(
            (
                i
                for i, r in enumerate(rows)
                if str(r.get("surlab_filename", "")).strip() == "spikeWaves_metadata.csv"
                and str(r.get("fieldname_surlab", "")).strip() == "primary_channel"
            ),
            len(rows),
        )
        new_row = {key: "" for key in header}
        new_row.update(
            {
                "row_type": "metadata_field",
                "surlab_file_location": "session_dir",
                "surlab_filename": "spikeWaves_metadata.csv",
                "fieldname_surlab": "area",
                "units": "plain text",
                "requirement_level": "not-recommended",
                "requirement_condition": "if_datatype_present:spikeWaves",
                "nwb_location": "NWBFile",
                "nwb_fieldname": "validate_only",
                "nwb_type": "str",
                "mapping_rationale": (
                    "Do not use: per-unit brain region belongs on spikeTimes_metadata "
                    "area only (NWB Units.brain_area). Waveform snippets reference the "
                    "same sorted units."
                ),
                "stage": "7",
                "notes": AREA_NOTE,
            }
        )
        rows.insert(insert_at + 1, new_row)

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in rows)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"Updated {TABLE} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
