"""Apply Task 1 LFP (stage 6) + behEvents (stage 8) placement from handoff."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "sur_nwb_conversion_table.csv"

LFP_SERIES = "NWBFile/acquisition/lfp"
ELECTRODES = "NWBFile/general/extracellular_ephys/electrodes"
LAB_LFP = "NWBFile/lab_meta_data/SurLabSchema_lfp"
BEH_ACQ = "NWBFile/acquisition/<datatypeID>"
BEH_EVENTS = "NWBFile/processing/behavior/<datatypeID>_events"

LFP_ALIGN_NOTE = (
    "Alignment: metadata row i ↔ ElectricalSeries data column i (axis 1). "
    "ElectricalSeries.electrodes = DynamicTableRegion over those electrode rows "
    "[0..n_channels-1]. LFP-only table (do not merge spikeTimes rows in this phase)."
)
BEH_ALIGN_NOTE = (
    "Alignment: metadata row i ↔ object-array slot i (event-type index). "
    "No formal DynamicTableRegion on AnnotationSeries (not supported in core PyNWB). "
    "When Y_size > 1: one AnnotationSeries per metadata row named "
    "<datatypeID>_<event_label> (default) or single series per stream policy."
)


def _blank_row(header: list[str]) -> dict[str, str]:
    return {key: "" for key in header}


def _insert_before_stage_data(rows: list[dict], header: list[str], stage: str, policy: dict) -> None:
    insert_at = next(
        (
            i
            for i, r in enumerate(rows)
            if str(r.get("stage", "")).strip() == stage
            and str(r.get("row_type", "")).strip() == "data_array"
        ),
        len(rows),
    )
    rows.insert(insert_at, policy)


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
        row_type = str(row.get("row_type", "")).strip()

        # --- behTSeries policy: cross-reference behEvents _events suffix ---
        if field == "(behTSeries_TimeSeries_and_features_table)":
            row["mapping_rationale"] = (
                "Policy (stage 4): core behTSeries = stock acquisition/<datatypeID> "
                "TimeSeries (data, timestamps, unit, optional rate) + stock "
                "processing/behavior/<datatypeID>_features DynamicTable. "
                "Row i ↔ data column i. No ndx-pose / custom TimeSeries subclass. "
                "Layout validate_only; rare schema leftovers → SurLabSchema_<datatypeID> "
                "(ndx-surlab-schema extension). behEvents (stage 8) uses the same "
                "companion-table pattern with _events suffix (not _features)."
            )
            continue

        # --- LFP sessionInfo scalars (stage 1 rows with stage 6) ---
        if fname.startswith("sessionInfo") and field == "lfp_data_unit_measurement":
            row["nwb_location"] = LFP_SERIES
            row["nwb_fieldname"] = "unit"
            row["mapping_rationale"] = (
                "Canonical sessionInfo column. ElectricalSeries.unit on acquisition "
                "object named lfp."
            )
            continue

        if fname.startswith("sessionInfo") and field == "lfp_sample_frequency__Hz":
            row["nwb_location"] = LAB_LFP
            row["nwb_fieldname"] = "sample_frequency__Hz"
            row["mapping_rationale"] = (
                "Canonical sessionInfo column. Descriptive rate only: PyNWB forbids "
                "ElectricalSeries.rate when timestamps are written. Stored in "
                "SurLabSchema_lfp; timestamps remain authoritative."
            )
            continue

        if stage != "6" and stage != "8":
            continue

        # --- LFP stage 6 ---
        if stage == "6":
            if fname.startswith("lfp_data.") and row_type == "data_array":
                row["nwb_location"] = LFP_SERIES
                row["nwb_fieldname"] = "data"
                row["mapping_rationale"] = (
                    "Stock PyNWB ElectricalSeries under acquisition/lfp. "
                    "Canonical shape (n_time, n_channels); transpose on ingest if needed."
                )
                notes = str(row.get("notes", "")).strip()
                if "Alignment:" not in notes:
                    row["notes"] = f"{notes} {LFP_ALIGN_NOTE}".strip()
                continue

            if fname.startswith("lfp_timestamps.") and row_type == "timestamps_array":
                row["nwb_location"] = LFP_SERIES
                row["nwb_fieldname"] = "timestamps"
                row["mapping_rationale"] = (
                    "Same ElectricalSeries object as lfp_data (acquisition/lfp). "
                    "Native times; timestamps are authoritative for session clock."
                )
                continue

            if fname == "lfp_schema.json" and field == "data_unit_measurement":
                row["nwb_location"] = LFP_SERIES
                row["nwb_fieldname"] = "unit"
                row["mapping_rationale"] = (
                    "Optional legacy schema mirror; same ElectricalSeries.unit as sessionInfo."
                )
                continue

            if fname == "lfp_schema.json" and field == "sample_frequency__Hz":
                row["nwb_location"] = LAB_LFP
                row["nwb_fieldname"] = "sample_frequency__Hz"
                row["mapping_rationale"] = (
                    "Optional legacy mirror; same SurLabSchema_lfp target as sessionInfo. "
                    "Not written on ElectricalSeries when timestamps present."
                )
                continue

            if fname == "lfp_metadata.csv":
                if field == "channel_ID":
                    row["nwb_location"] = ELECTRODES
                    row["nwb_fieldname"] = "id"
                    row["mapping_rationale"] = (
                        "Electrodes table row id; order matches LFP channel axis (column i)."
                    )
                    row["notes"] = "Required when lfp=1. One electrode row per channel."
                    continue
                if field == "channel_label":
                    row["nwb_location"] = ELECTRODES
                    row["nwb_fieldname"] = "custom_column_channel_label"
                    row["mapping_rationale"] = "Electrode custom column channel_label."
                    continue
                if field == "area":
                    row["nwb_location"] = ELECTRODES
                    row["nwb_fieldname"] = "location"
                    row["nwb_alt_fieldnames"] = "brain_area"
                    row["mapping_rationale"] = "Electrode location / brain area."
                    continue
                if field == "depth__um":
                    row["nwb_location"] = ELECTRODES
                    row["nwb_fieldname"] = "z"
                    row["nwb_alt_fieldnames"] = ""
                    row["mapping_rationale"] = (
                        "Primary depth axis on electrode (most important geometry). "
                        "When absent use NaN; x/y also NaN when coordinates absent."
                    )
                    continue
                if field == "grid_location":
                    row["nwb_location"] = ELECTRODES
                    row["nwb_fieldname"] = "custom_column_grid_location"
                    row["mapping_rationale"] = "Optional grid coordinate on electrode row."
                    continue
                if field == "dataset_specific":
                    row["nwb_location"] = ELECTRODES
                    row["nwb_fieldname"] = "custom_columns"
                    row["mapping_rationale"] = (
                        "Unlisted lfp_metadata.csv columns → additional electrode custom columns."
                    )
                    continue

        # --- behEvents stage 8 ---
        if stage == "8":
            if fname.startswith("<datatypeID>_data.") and row_type == "data_array":
                row["nwb_location"] = BEH_ACQ
                row["nwb_fieldname"] = "timestamps"
                row["nwb_type"] = "array_of_float64"
                row["mapping_rationale"] = (
                    "Stock AnnotationSeries under acquisition/<datatypeID>. "
                    "SurLab data object-array slot i holds event times (seconds); "
                    "converter writes AnnotationSeries.timestamps (data = ones per PyNWB)."
                )
                notes = str(row.get("notes", "")).strip()
                if "Alignment:" not in notes:
                    row["notes"] = f"{notes} {BEH_ALIGN_NOTE}".strip()
                continue

            if fname == "<datatypeID>_schema.json" and field == "data_unit_measurement":
                row["nwb_location"] = BEH_ACQ
                row["nwb_fieldname"] = "description"
                row["mapping_rationale"] = (
                    "Unit token documents timestamp semantics (typically time__s) on "
                    "AnnotationSeries; times live in timestamps not a separate file."
                )
                continue

            if fname == "<datatypeID>_metadata.csv" and field == "event_ID":
                row["nwb_location"] = BEH_EVENTS
                row["nwb_fieldname"] = "event_ID"
                row["mapping_rationale"] = (
                    "Stock DynamicTable in processing module behavior. "
                    "event_ID is a named column; table id may mirror row index. "
                    f"{BEH_ALIGN_NOTE}"
                )
                row["notes"] = (
                    "Required when stream present. Row order must match data object-array index."
                )
                continue

            if fname == "<datatypeID>_metadata.csv" and field == "event_label":
                row["nwb_location"] = BEH_EVENTS
                row["nwb_fieldname"] = "event_label"
                row["mapping_rationale"] = (
                    "Event label column on processing/behavior/<datatypeID>_events "
                    "(e.g. lick, lever_press)."
                )
                continue

            if fname == "<datatypeID>_metadata.csv" and field == "dataset_specific":
                row["nwb_location"] = BEH_EVENTS
                row["nwb_fieldname"] = "custom_columns"
                row["mapping_rationale"] = (
                    "Unlisted metadata columns preserved as additional DynamicTable columns "
                    "on <datatypeID>_events (not acquisition custom_columns)."
                )
                continue

    # New LFP metadata rows: channel_x_coordinate, channel_y_coordinate
    if not any(
        str(r.get("fieldname_surlab", "")).strip() == "channel_x_coordinate"
        and str(r.get("surlab_filename", "")).strip() == "lfp_metadata.csv"
        for r in rows
    ):
        coord_rows = [
            {
                "fieldname_surlab": "channel_x_coordinate",
                "units": "float (same spirit as roi_x_coordinate on traces)",
                "requirement_level": "optional",
                "nwb_fieldname": "x",
                "nwb_type": "float",
                "mapping_rationale": (
                    "Optional electrode x coordinate. When absent converter writes NaN "
                    "(valid in PyNWB); depth__um → z remains primary."
                ),
            },
            {
                "fieldname_surlab": "channel_y_coordinate",
                "units": "float (same spirit as roi_y_coordinate on traces)",
                "requirement_level": "optional",
                "nwb_fieldname": "y",
                "nwb_type": "float",
                "mapping_rationale": (
                    "Optional electrode y coordinate. When absent converter writes NaN."
                ),
            },
        ]
        insert_at = next(
            (
                i
                for i, r in enumerate(rows)
                if str(r.get("surlab_filename", "")).strip() == "lfp_metadata.csv"
                and str(r.get("fieldname_surlab", "")).strip() == "grid_location"
            ),
            len(rows),
        )
        for offset, spec in enumerate(coord_rows):
            new_row = _blank_row(header)
            new_row.update(
                {
                    "row_type": "metadata_field",
                    "surlab_file_location": "session_dir",
                    "surlab_filename": "lfp_metadata.csv",
                    "fieldname_surlab": spec["fieldname_surlab"],
                    "units": spec["units"],
                    "requirement_level": spec["requirement_level"],
                    "requirement_condition": "if_datatype_present:lfp",
                    "nwb_location": ELECTRODES,
                    "nwb_fieldname": spec["nwb_fieldname"],
                    "nwb_type": spec["nwb_type"],
                    "mapping_rationale": spec["mapping_rationale"],
                    "stage": "6",
                    "notes": "",
                }
            )
            rows.insert(insert_at + offset, new_row)

    # Policy row: LFP ElectricalSeries + electrodes
    lfp_marker = "(lfp_ElectricalSeries_and_electrodes_table)"
    if not any(str(r.get("fieldname_surlab", "")).strip() == lfp_marker for r in rows):
        policy = _blank_row(header)
        policy.update(
            {
                "row_type": "metadata_field",
                "surlab_file_location": "session_dir",
                "surlab_filename": "lfp_data.{mat|npz}",
                "fieldname_surlab": lfp_marker,
                "units": "N/A",
                "requirement_level": "na",
                "requirement_condition": "if_datatype_present:lfp",
                "nwb_location": LFP_SERIES,
                "nwb_fieldname": "N/A",
                "nwb_type": "N/A",
                "mapping_rationale": (
                    "Policy (stage 6): core LFP = stock acquisition/lfp ElectricalSeries "
                    "(data, timestamps, unit) with formal ElectricalSeries.electrodes "
                    "DynamicTableRegion on general/extracellular_ephys/electrodes built "
                    "from lfp_metadata.csv only (LFP-only; no spikeTimes merge). "
                    "Row i ↔ channel column i. depth__um → z; optional channel_x/y → x/y "
                    "(NaN when absent). sample_frequency__Hz → SurLabSchema_lfp when "
                    "timestamps written (PyNWB forbids rate+timestamps). Filters → "
                    "SurLabSchema_lfp. imp/filtering on add_electrode: "
                    "MISSING_REQUIRED_FOR_NWB when SurLab does not supply."
                ),
                "stage": "6",
                "notes": "Resolves for_cursor/task1_handoff_lfp_and_behevents.txt (Part A).",
            }
        )
        _insert_before_stage_data(rows, header, "6", policy)

    # Policy row: behEvents AnnotationSeries + events table
    beh_marker = "(behEvents_AnnotationSeries_and_events_table)"
    if not any(str(r.get("fieldname_surlab", "")).strip() == beh_marker for r in rows):
        policy = _blank_row(header)
        policy.update(
            {
                "row_type": "metadata_field",
                "surlab_file_location": "session_dir",
                "surlab_filename": "<datatypeID>_data.{mat|npz}",
                "fieldname_surlab": beh_marker,
                "units": "N/A",
                "requirement_level": "na",
                "requirement_condition": "if_datatype_present:<datatypeID>",
                "nwb_location": BEH_ACQ,
                "nwb_fieldname": "N/A",
                "nwb_type": "N/A",
                "mapping_rationale": (
                    "Policy (stage 8): core behEvents = stock acquisition/<datatypeID> "
                    "AnnotationSeries (timestamps from data object-array; data=ones) + "
                    "stock processing/behavior/<datatypeID>_events DynamicTable. "
                    "Row i ↔ object-array index i. No formal metadata link on "
                    "AnnotationSeries (convention only). Layout validate_only; rare "
                    "schema leftovers → SurLabSchema_<datatypeID>. Same companion-table "
                    "pattern as behTSeries (_events suffix not _features)."
                ),
                "stage": "8",
                "notes": "Resolves for_cursor/task1_handoff_lfp_and_behevents.txt (Part B).",
            }
        )
        _insert_before_stage_data(rows, header, "8", policy)

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: r.get(key, "") for key in header} for r in rows)

    shutil.copy2(TABLE, ROOT / "for_cursor" / "sur_nwb_conversion_table.csv")
    print(f"Updated {TABLE} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
