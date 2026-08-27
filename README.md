# Gregg_surlab_nwb_conversion_tool

Research-focused converter between SurLab dataset format and NWB, driven by
`sur_nwb_conversion_table.csv`.

## Installation

Requirements:
- Python 3.8+
- Conda recommended

```bash
conda env create -f environment_cross_platform.yml
conda activate surlab_nwb_conversion_tool
pip install -e .
```

## Primary Tool: SurLab -> NWB + PyNWB validation (Task 3)

Converts all implemented SurLab data under a dataset directory into one NWB per
session, then runs the official `pynwb.validate()` checker.

Default NWB filename per session: `{animal_ID}_{session_ID}.nwb` (no stage suffix).

### One-line run (cross-platform)

```bash
python scripts/run_convert_and_validate.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX
```

Open summary CSV and per-file reports after the run (Windows):

```bash
python scripts/run_convert_and_validate.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --open-results
```

### Windows run (double-click / terminal)

- **Dev demo (double-click):** `run_convert_and_validate_demo.bat`
- **Any dataset:** `run_convert_and_validate.bat demo_data\SeqBias_AstroBlock_NPX`

### Inspect NWB interactively

1. Run conversion (above).
2. Open `scripts/inspect_nwb.ipynb` and set `nwb_path` to your `.nwb` file.
3. Windows shortcut: `scripts/inspect_nwb_win_start.bat`

### Dev-only: conversion / discovery without PyNWB validation

```bash
python scripts/run_stage1_conversion.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --conversion-table sur_nwb_conversion_table.csv
```

Validate-only discovery (SurLab side, not PyNWB):

```bash
python scripts/run_stage1_conversion.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --conversion-table sur_nwb_conversion_table.csv --validate-only
```

## SurLab format validation (conventions)

Checks whether an **input** SurLab dataset follows the conversion-table conventions
(presence, naming, field types, sessionInfo↔schema agreement, modality flag vs files).
Does **not** compare to NWB or round-trip output. Skips pipeline artifacts
(`.nwb`, `roundtrip_surformat/`, validation/runlog files).

```bash
python scripts/run_surlab_format_validation.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX
python scripts/run_surlab_format_validation.py --dataset-dir demo_data/tricolor_projections
```

Windows: `run_surlab_format_validation.bat demo_data\SeqBias_AstroBlock_NPX`

Exit code **1** if any required-missing, naming, type, or sessionInfo/schema conflict
failures; recommended-missing is warn-only.

Outputs (under the dataset tree):
- Per session: `surlab_format_validation_report.csv`, `session_validation_report.csv`
- Dataset: `surlab_format_validation_summary.csv`, `session_validation_matrix.csv`
- Log: `runlog_surlab_format_validation.txt`

## Inputs and Output Formats

Inputs:
- SurLab CSV metadata files (`sessionInfo_*.csv`)
- Conversion mapping table (`sur_nwb_conversion_table.csv`)
- Session subdirectories with modality files as they are implemented

Outputs:
- NWB file per session: `{animal_ID}_{session_ID}.nwb` in the session directory
- PyNWB validation report per NWB: `{nwb_stem}_pynwb_validation_report.txt`
- Dataset validation summary: `nwb_validation_summary.csv`
- Run log: `runlog_convert_and_validate.txt`

Validation summary columns:

- `session`
- `nwb_file`
- `report_file`
- `passed`
- `failed`
- `number_failed`
- `note`

## Notes

- **Design reference:** `for_cursor/task2_implementation_decisions_and_answers.txt` (section E)
  and **Forward conversion** in `SurLab data format documentation.md`.
- One integrated NWB file per session; `stage` in the table is dev-tracking only
  (CLI `--stage` limits table rows during incremental work).
- Datatype presence is inferred from **session-dir filenames first**; shared
  resolver in `src/surlab_paths.py`.
- Legacy sessionInfo headers (`animalID`, etc.) are normalized **in memory on
  read**; the validator uses canonical names only.
- `zero_time` is the reference-stream datatype ID, stored in NWB as
  `notes`: `SurLab zero_time=<datatypeID>`; clock mismatch logs a warning only.
- Deterministic NWB identifier:
  `identifier = f"{animal_ID}__{session_ID}"`.
- Discovery outputs per session: `session_validation_report.csv`,
  `conversion_table_discovered.csv`, `runlog.txt`.

## Task 3: Validate Existing NWB Files Only

If NWB files already exist and you only need PyNWB validation:

```bash
python scripts/validate_nwb_dataset.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX
```

Windows shortcut:

- `developer_scripts/run_nwb_validation_task3_win.bat`

## Task 4: Reverse Conversion (NWB -> SurLab)

Task 4 uses `sur_nwb_conversion_table.csv` and reconstructs SurLab files from NWB. Decisions
and cross-agent instructions: `for_cursor/task4_implementation_decisions_and_answers.txt`.

Workflow (target):

1. For each `.nwb` under a dataset directory, write SurLab outputs under
   `<session_dir>/roundtrip_surformat/` (verbose filenames preferred; arrays as `.npz`).
2. Rebuild `sessionInfo_single_session.csv` and aggregate
   `sessionInfo_<datasetID>.csv` from NWB metadata (keywords, notes, subject fields).
3. As forward stages land, export spikeTimes, traces, behTSeries, and trialInfo
   using the same table (invert array layout when forward transposed on ingest).

Current code: **sessionInfo skeleton only** — see decisions file for implementation order.

One-line run:

```bash
python scripts/run_task4_reverse_conversion.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --conversion-table sur_nwb_conversion_table.csv
```

Optional dev filter (limit table rows by stage during development):

```bash
python scripts/run_task4_reverse_conversion.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --dev-max-stage 1
```

Log file: `runlog.txt` under the dataset directory.

Windows shortcut:

- `developer_scripts/run_task4_reverse_conversion_win.bat`

## Task 5: Round-Trip Validation

Task 5 runs the full pipeline in one command:

1. Snapshot original SurLab files (before reverse conversion can overwrite them)
2. Forward conversion + official PyNWB validation (`run_convert_and_validate.py`)
3. Reverse conversion (`run_task4_reverse_conversion.py`)
4. Compare every `sur_nwb_conversion_table.csv` check: original SurLab vs round-trip output

Round-trip SurLab files are read from `<session_dir>/roundtrip_surformat/` when present;
otherwise Task 5 falls back to current Task 4 output locations (for example
`sessionInfo_single_session.csv` in the session folder).

The CLI exits with code **1 only when at least one value mismatch** is found.
PyNWB validation failures are recorded in the summary but do not change the exit code.

One-line run:

```bash
python scripts/run_roundtrip_validation.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --conversion-table sur_nwb_conversion_table.csv
```

Windows shortcut:

- `developer_scripts/run_roundtrip_validation_win.bat`

Outputs (written into the dataset tree):

- Per session: `roundtrip_validation_report.csv`
- Dataset summary: `roundtrip_validation_summary.csv`
- Run log: `runlog_roundtrip_validation.txt`

Summary columns:

- `session`, `session_key`, `forward_ok`, `reverse_ok`
- `n_match`, `n_mismatch`, `n_skipped_original_missing`, `n_skipped_roundtrip_missing`, `n_skipped_non_comparable`
- `nwb_validation_passed`, `nwb_validation_note`, `report_file`

Per-check report columns include `nwb_value`, `nwb_note`, and `likely_owner`
(`task2_forward`, `task4_reverse`, `both_or_table_gap`, `data_or_spec`, `task4_not_exported`)
from table-driven NWB triangulation.
