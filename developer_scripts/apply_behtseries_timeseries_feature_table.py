"""Apply Task 1 behTSeries TimeSeries + feature DynamicTable placement (stage 4)."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

TS_LOC = "NWBFile/acquisition/<datatypeID>"
FEAT_LOC = "NWBFile/processing/behavior/<datatypeID>_features"

ALIGN_NOTE = (
    "Alignment: metadata row i ↔ TimeSeries data column i (axis 1). "
    "No formal DynamicTableRegion link (stock TimeSeries has no features slot). "
    "Not ndx-pose; one TimeSeries per stream named <datatypeID>."
)


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        rows = list(reader)

    for row in rows:
        stage = str(row.get("stage", "")).strip()
        fname = str(row.get("surlab_filename", "")).strip()
        field = str(row.get("fieldname_surlab", "")).strip()
        loc = str(row.get("nwb_location", "")).strip()
        nwb_field = str(row.get("nwb_fieldname", "")).strip()

        # sessionInfo stream scalars for behTSeries (stage 1, acquisition target)
        if (
            fname.startswith("sessionInfo")
            and field == "<datatypeID>_data_unit_measurement"
            and loc == "NWBFile/acquisition"
        ):
            row["nwb_location"] = TS_LOC
            row["nwb_fieldname"] = "unit"
            row["mapping_rationale"] = (
                "Canonical sessionInfo column. TimeSeries.unit on acquisition object "
                "named <datatypeID> (behTSeries streams)."
            )
            continue

        if (
            fname.startswith("sessionInfo")
            and field == "<datatypeID>_sample_frequency__Hz"
            and loc == "NWBFile/acquisition"
        ):
            row["nwb_location"] = TS_LOC
            row["nwb_fieldname"] = "rate"
            row["mapping_rationale"] = (
                "Canonical sessionInfo column. Optional TimeSeries.rate on acquisition "
                "<datatypeID>; timestamps remain authoritative."
            )
            continue

        if stage != "4":
            continue

        if fname.startswith("<datatypeID>_data.") and row.get("row_type") == "data_array":
            row["nwb_location"] = TS_LOC
            row["nwb_fieldname"] = "data"
            row["mapping_rationale"] = (
                "Stock PyNWB TimeSeries under acquisition; object name = full <datatypeID> "
                "(e.g. pupil_behTSeries). One series per stream; no ndx-pose."
            )
            notes = str(row.get("notes", "")).strip()
            if "Alignment:" not in notes:
                row["notes"] = f"{notes} {ALIGN_NOTE}".strip()
            continue

        if fname.startswith("<datatypeID>_timestamps.") and row.get("row_type") == "timestamps_array":
            row["nwb_location"] = TS_LOC
            row["nwb_fieldname"] = "timestamps"
            row["mapping_rationale"] = (
                "Same TimeSeries object as data (acquisition/<datatypeID>). "
                "Native times; no required resampling."
            )
            continue

        if fname == "<datatypeID>_schema.json" and field == "data_unit_measurement":
            row["nwb_location"] = TS_LOC
            row["nwb_fieldname"] = "unit"
            row["mapping_rationale"] = (
                "Optional legacy schema mirror; same TimeSeries.unit target as sessionInfo."
            )
            continue

        if fname == "<datatypeID>_schema.json" and field == "sample_frequency__Hz":
            row["nwb_location"] = TS_LOC
            row["nwb_fieldname"] = "rate"
            row["mapping_rationale"] = (
                "Optional legacy schema mirror; same TimeSeries.rate as sessionInfo. "
                "Timestamps remain authoritative."
            )
            continue

        # layout + schema dataset_specific already validate_only / LabMetaData — leave

        if fname == "<datatypeID>_metadata.csv" and field == "feature_ID":
            row["nwb_location"] = FEAT_LOC
            row["nwb_fieldname"] = "feature_ID"
            row["mapping_rationale"] = (
                "Stock DynamicTable in processing module 'behavior'. "
                "feature_ID is a named column; table id may mirror row index. "
                f"{ALIGN_NOTE}"
            )
            row["notes"] = (
                "Required when stream present. Row order must match TimeSeries data axis 1."
            )
            continue

        if fname == "<datatypeID>_metadata.csv" and field == "feature_label":
            row["nwb_location"] = FEAT_LOC
            row["nwb_fieldname"] = "feature_label"
            row["mapping_rationale"] = (
                "Feature label column on processing/behavior/<datatypeID>_features "
                "(e.g. pupil_x, tongue_likelihood)."
            )
            continue

        if fname == "<datatypeID>_metadata.csv" and field == "dataset_specific":
            row["nwb_location"] = FEAT_LOC
            row["nwb_fieldname"] = "custom_columns"
            row["mapping_rationale"] = (
                "Unlisted metadata columns preserved as additional DynamicTable columns "
                "on <datatypeID>_features (not acquisition custom_columns)."
            )
            continue

    # Policy row for behTSeries placement
    marker = "(behTSeries_TimeSeries_and_features_table)"
    if not any(str(r.get("fieldname_surlab", "")).strip() == marker for r in rows):
        policy = {key: "" for key in header}
        policy.update(
            {
                "row_type": "metadata_field",
                "surlab_file_location": "session_dir",
                "surlab_filename": "<datatypeID>_data.{mat|npz}",
                "fieldname_surlab": marker,
                "units": "N/A",
                "requirement_level": "na",
                "requirement_condition": "if_datatype_present:<datatypeID>",
                "nwb_location": "NWBFile/acquisition",
                "nwb_fieldname": "N/A",
                "nwb_type": "N/A",
                "mapping_rationale": (
                    "Policy (stage 4): core behTSeries = stock acquisition/<datatypeID> "
                    "TimeSeries (data, timestamps, unit, optional rate) + stock "
                    "processing/behavior/<datatypeID>_features DynamicTable. "
                    "Row i ↔ data column i. No ndx-pose / custom TimeSeries subclass. "
                    "Layout validate_only; rare schema leftovers → SurLabSchema_<datatypeID> "
                    "(ndx-surlab-schema extension). Same feature-table pattern may apply later "
                    "to behEvents (event_ID/event_label)."
                ),
                "stage": "4",
                "notes": "Resolves for_cursor/task1_handoff_behtseries_timeseries_feature_table.txt.",
            }
        )
        # insert before first stage-4 data_array
        insert_at = next(
            (
                i
                for i, r in enumerate(rows)
                if str(r.get("stage", "")).strip() == "4"
                and str(r.get("row_type", "")).strip() == "data_array"
            ),
            len(rows),
        )
        rows.insert(insert_at, policy)

    # Optional forward note on stage-8 event metadata (one-liner in notes)
    for row in rows:
        if (
            str(row.get("stage", "")).strip() == "8"
            and str(row.get("fieldname_surlab", "")).strip() == "event_ID"
        ):
            notes = str(row.get("notes", "")).strip()
            tip = (
                "Future: prefer processing/behavior/<datatypeID>_events DynamicTable "
                "(same pattern as behTSeries features); current acquisition custom_column is interim."
            )
            if tip not in notes:
                row["notes"] = f"{notes} {tip}".strip()

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in rows)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"Updated {TABLE} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
