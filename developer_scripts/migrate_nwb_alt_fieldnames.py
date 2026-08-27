"""Migrate nwb_alt_location + nwb_alt_fieldname -> nwb_alt_fieldnames; populate inline aliases."""

from __future__ import annotations

import csv
from pathlib import Path

TABLE = Path(__file__).resolve().parents[1] / "sur_nwb_conversion_table.csv"

# Same-container field/column renames (reverse-only). Key: fieldname_surlab.
INLINE_FIELDNAME_ALIASES: dict[str, str] = {
    "area": "brain_area;location",
    "depth__um": "depth",
    "spike_sorting_ID": "sorting_id;cluster_id",
    "quality": "quality_label",
    "unit_ID": "unit_id",
    "spikeTimes_sample_frequency__Hz": "sampling_rate",
    "spikeTimes_data_unit_measurement": "data_unit_measurement",
    "spikeTimes_quality_metric": "quality_metric",
    "sample_frequency__Hz": "sampling_rate",
    "data_unit_measurement": "data_unit_measurement",
    "quality_metric": "quality_metric",
}


def main() -> None:
    with TABLE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        old_header = list(reader.fieldnames or [])
        rows = list(reader)

    new_header = [col for col in old_header if col not in {"nwb_alt_location", "nwb_alt_fieldname"}]
    if "nwb_alt_fieldnames" not in new_header:
        idx = new_header.index("nwb_fieldname") + 1
        new_header.insert(idx, "nwb_alt_fieldnames")

    populated = 0
    for row in rows:
        fieldname = str(row.get("fieldname_surlab", "")).strip()
        merged = str(row.get("nwb_alt_fieldnames", "")).strip()

        old_locs = str(row.get("nwb_alt_location", "")).strip()
        old_fields = str(row.get("nwb_alt_fieldname", "")).strip()
        if old_fields and not merged:
            loc_parts = [part.strip() for part in old_locs.split(";") if part.strip()]
            field_parts = [part.strip() for part in old_fields.split(";") if part.strip()]
            primary_loc = str(row.get("nwb_location", "")).strip()
            alias_parts: list[str] = []
            for index, alt_field in enumerate(field_parts):
                alt_loc = loc_parts[index] if index < len(loc_parts) else primary_loc
                if alt_loc and alt_loc != primary_loc:
                    alias_parts.append(f"/{alt_loc}|{alt_field}")
                else:
                    alias_parts.append(alt_field)
            merged = ";".join(alias_parts)

        if not merged and fieldname in INLINE_FIELDNAME_ALIASES:
            merged = INLINE_FIELDNAME_ALIASES[fieldname]
            populated += 1
        elif merged and fieldname in INLINE_FIELDNAME_ALIASES:
            populated += 1

        row["nwb_alt_fieldnames"] = merged
        for drop in ("nwb_alt_location", "nwb_alt_fieldname"):
            row.pop(drop, None)

        if str(row.get("fieldname_surlab", "")).strip() == "(nwb_reverse_alternate_reads)":
            row["fieldname_surlab"] = "(nwb_alt_fieldnames_rules)"
            row["mapping_rationale"] = (
                "Reverse-only: semicolon-separated field/column names on primary nwb_location. "
                "Forward ignores. Primary wins; warn if primary and alias both non-empty and differ. "
                "Rare /location|field escape for different container. Ecosystem-specific paths: reverse_mapping/*.csv."
            )
            row["notes"] = (
                "Load order: primary+linkage, then nwb_alt_fieldnames, then reverse_mapping/<ecosystem>.csv "
                "only when user specifies ecosystem (e.g. allen, ibl)."
            )

    with TABLE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=new_header, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in new_header} for row in rows)

    print(f"migrated {len(rows)} rows; inline aliases on {populated} rows")


if __name__ == "__main__":
    main()
