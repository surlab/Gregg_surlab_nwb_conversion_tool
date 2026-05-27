# Gregg_surlab_nwb_conversion_tool

Research-focused converter between SurLab dataset format and NWB, driven by
`conversion_table.csv`.

## Installation

Requirements:
- Python 3.8+
- Conda recommended

```bash
conda env create -f environment_cross_platform.yml
conda activate Gregg_surlab_nwb_conversion_tool
pip install -e .
```

## Primary Tool: Stage-1 SurLab -> NWB

Stage 1 converts session metadata from:
- `sessionInfo_<datasetID>.csv` in dataset directory, and/or
- `sessionInfo_single_session.csv` in session directory

Mapping and required/recommended checks are defined in `conversion_table.csv`.

### One-line run (cross-platform)

```bash
python scripts/run_stage1_conversion.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --session-dir demo_data/SeqBias_AstroBlock_NPX/AstroDREADD25_20240702 --conversion-table conversion_table.csv --output-nwb demo_results/AstroDREADD25_20240702_stage1.nwb --output-matrix demo_results/session_validation_matrix.csv --stage 1
```

### Windows run (double-click / terminal)

Use `developer_scripts/run_stage1_conversion_win.bat`.

### Validate-only mode

```bash
python scripts/run_stage1_conversion.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --session-dir demo_data/SeqBias_AstroBlock_NPX/AstroDREADD25_20240702 --conversion-table conversion_table.csv --output-nwb demo_results/AstroDREADD25_20240702_stage1.nwb --output-matrix demo_results/session_validation_matrix.csv --stage 1 --validate-only
```

## Inputs and Output Formats

Inputs:
- SurLab CSV metadata files (`sessionInfo_*.csv`)
- Conversion mapping table (`conversion_table.csv`)
- Stage flag (current phase)

Outputs:
- NWB file (PyNWB)
- Validation matrix CSV where:
  - columns are sessions
  - rows are conversion-table checks
  - status values include:
    - `found`
    - `missing (Required)`
    - `not found (recommended)`

## Notes

- Current implementation focuses on stage 1 metadata and uses a file-level
  stage guard (skip files belonging to later stages).
- Deterministic NWB identifier rule:
  `identifier = f"{animal_ID}__{session_ID}"`.

## Task 3: Validate Existing NWB Files

Use official `pynwb.validate()` to validate every `.nwb` file under one dataset
directory.

One-line run:

```bash
python scripts/validate_nwb_dataset.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX
```

Windows shortcut:

- `developer_scripts/run_nwb_validation_task3_win.bat`

Outputs:

- Per-NWB validation report text file in the same directory as each NWB file:
  `<nwb_stem>_pynwb_validation_report.txt`
- Dataset-level summary table in dataset root:
  `nwb_validation_summary.csv`

Summary table columns:

- `session`
- `nwb_file`
- `report_file`
- `passed`
- `failed`
- `number_failed`
- `note`

## Task 4: Reverse Conversion (NWB -> SurLab)

Task 4 uses `conversion_table.csv` (stage-filtered) and reconstructs SurLab session
metadata from NWB files.

Workflow:

1. For each `.nwb` found under a dataset directory, write a one-row
   `sessionInfo_single_session.csv` in that NWB file's session directory.
2. Concatenate those single-session rows into one dataset-level
   `sessionInfo_<datasetID>.csv` in the dataset root.

One-line run:

```bash
python scripts/run_task4_reverse_conversion.py --dataset-dir demo_data/SeqBias_AstroBlock_NPX --conversion-table conversion_table.csv --stage 4
```

Windows shortcut:

- `developer_scripts/run_task4_reverse_conversion_win.bat`
