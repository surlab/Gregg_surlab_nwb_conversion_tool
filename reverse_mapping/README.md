# Reverse mapping packs (NWB → SurLab)

Used **only by Task 4 reverse conversion**. Forward SurLab → NWB ignores these files.

## Load order

1. **`sur_nwb_conversion_table.csv`** — primary `nwb_location` + `nwb_fieldname` (with stream linkage from `mapping_rationale`).
2. **`nwb_alt_fieldnames`** on the same row — same-container renames (e.g. `brain_area` when primary is `custom_column_brain_area`). Always tried unless primary is non-empty.
3. **`reverse_mapping/<ecosystem>.csv`** — only when the user specifies the source format (e.g. CLI `--reverse-ecosystem allen` or `ibl`). Not loaded by default.

If primary and a fallback are both non-empty but **different → warn** (primary wins).

## Ecosystem file schema

| Column | Meaning |
|--------|---------|
| `fieldname_surlab` | Join key to core table (must match SurLab field name) |
| `priority` | Lower number = tried earlier within that ecosystem file |
| `nwb_location` | NWB container path |
| `nwb_fieldname` | Attribute or DynamicTable column |
| `linkage_note` | Optional; prose/token for Task 4 (e.g. `units_linked_device`) |
| `notes` | Human documentation |

## Files

- **`allen.csv`** — Allen Brain Observatory / Visual Coding fallbacks (extend with real `.nwb` tests).
- **`ibl.csv`** — IBL ONE / Brain Wide Map fallbacks (extend with real `.nwb` tests).

Add new ecosystem files as `reverse_mapping/<name>.csv` without editing the primary conversion table.
