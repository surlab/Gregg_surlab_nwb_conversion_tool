# Gregg_surlab_nwb_conversion_tool

Converter between the SurLab dataset format and NWB. Field mapping is
`sur_nwb_conversion_table.csv` at the repo root.

Format documentation:

- [Format basics](docs/surlab_format_basics.md) — folders, filenames, session clock, modalities
- [Field catalog](docs/surlab_field_catalog.md) — column and schema names
- [NWB conversion notes](docs/nwb_conversion_notes.md) — placement, keywords, reverse reads

Canonical demo: `demo_data/surlab_format_demo/` (ecephys: LFP, spike times, spike waveforms, `lick_behEvents`, `trialInfo`). Optical traces and continuous behavior: `demo_data/tricolor_projections/`. All-modality round-trip: `demo_data/kitchen_sink_demo/`. `demo_data/SeqBias_AstroBlock_NPX/` is archival.

## Installation

Requirements: Python 3.8+. Conda is the setup used for the demos.

**This repo (development and demos):**

```bash
conda env create -f environment_cross_platform.yml
conda activate surlab_nwb_conversion_tool
pip install -e .
```

**Another repo (library install from git):**

```bash
pip install "git+https://github.com/surlab/Gregg_surlab_nwb_conversion_tool.git"
```

Distribution name: `surlab-nwb-conversion`. The import package is still `src`.

```python
from src import (
    ConversionConfig,
    convert_surlab_session_to_nwb,
    default_conversion_table_path,
    validate_nwb_file,
    validate_session_format,
    ValidationConfig,
)

table = default_conversion_table_path()  # bundled table; or pass your own Path
```

A path passed as `--conversion-table` overrides the bundled table.

## Inputs and outputs

Inputs:

- SurLab session tree (see the format basics)
- `sessionInfo_<datasetID>.csv`
- Modality files the converter currently writes both ways: `spikeTimes`, `*_traces`, `*_behTSeries`, `lfp`, `spikeWaves`, `*_behEvents`, `trialInfo`
- `sur_nwb_conversion_table.csv`

Shared output rules:

- One NWB file per session, `{animal_ID}_{session_ID}.nwb`, in the session directory
- `NWBFile.identifier` is `{animal_ID}__{session_ID}`
- Which streams exist is inferred from filenames in the session folder first
- Legacy sessionInfo headers (`animalID` and similar) are renamed in memory on read; the CSV on disk is left as-is

## Convert SurLab to NWB and validate with PyNWB

Converts each session under a dataset directory, then runs `pynwb.validate()`.

```bash
python scripts/run_convert_and_validate.py --dataset-dir demo_data/surlab_format_demo
```

Same command for the optical demo: `--dataset-dir demo_data/tricolor_projections`.

Open the summary CSV and per-file reports after the run (Windows):

```bash
python scripts/run_convert_and_validate.py --dataset-dir demo_data/surlab_format_demo --open-results
```

Windows:

- Double-click the canonical demo: `run_convert_and_validate_demo.bat`
- Any dataset: `run_convert_and_validate.bat demo_data\surlab_format_demo`

Outputs under the dataset tree:

- `{animal_ID}_{session_ID}.nwb` in each session directory
- `{nwb_stem}_pynwb_validation_report.txt` next to each NWB file
- `nwb_validation_summary.csv`
- `runlog_convert_and_validate.txt`

Summary columns: `session`, `nwb_file`, `report_file`, `passed`, `failed`, `number_failed`, `note`.

Inspect a file: open `scripts/inspect_nwb.ipynb` and set `nwb_path`. Windows shortcut: `scripts/inspect_nwb_win_start.bat`.

### Conversion without the PyNWB checker

Development entry point. Writes the NWB file and the discovery CSVs. `--stage` limits table rows while a modality is being added. `--validate-only` skips the NWB write.

```bash
python scripts/run_stage1_conversion.py --dataset-dir demo_data/surlab_format_demo --conversion-table sur_nwb_conversion_table.csv
```

Per session this writes `session_validation_report.csv`, `conversion_table_discovered.csv`, and `runlog.txt`.

## Validate a SurLab dataset

Checks an **input** SurLab tree against the conversion table: presence, names, field types, sessionInfo versus schema, and modality flags versus files. It does not compare to NWB. Pipeline products are skipped (`.nwb`, `roundtrip_surformat/`, validation reports, run logs).

```bash
python scripts/run_surlab_format_validation.py --dataset-dir demo_data/surlab_format_demo
```

Windows: `run_surlab_format_validation.bat demo_data\surlab_format_demo`

Exit code is **1** when a required field is missing, or when a naming, type, sessionInfo/schema, or array load/dtype/shape check fails. A recommended field that is missing is a warning only.

For `data_array` and `timestamps_array` files (`.mat` or `.npz`) the check also covers loadability, a float64-compatible dtype, 1-D timestamps, timestamps length versus data axis 0, and schema `X_size` / `Y_size` / index lengths when those keys exist.

Outputs:

- Per session: `surlab_format_validation_report.csv`, `session_validation_report.csv`
- Dataset: `surlab_format_validation_summary.csv`, `session_validation_matrix.csv`
- Log: `runlog_surlab_format_validation.txt`

## Validate existing NWB files

PyNWB validation only, for NWB files that are already on disk:

```bash
python scripts/validate_nwb_dataset.py --dataset-dir demo_data/surlab_format_demo
```

Windows: `developer_scripts/run_nwb_validation_task3_win.bat`

## Reverse: NWB to SurLab

Rebuilds SurLab files from each `.nwb` under a dataset directory. Output goes to `<session_dir>/roundtrip_surformat/` (verbose filenames, arrays as `.npz`).

For each session it writes `sessionInfo_single_session.csv` plus the streams present in the file: `spikeTimes`, `*_traces`, `*_behTSeries`, `trialInfo`, `lfp`, `spikeWaves`, and `*_behEvents`. It also writes `sessionInfo_<datasetID>.csv` and `reverse_conversion_report.csv` under `<dataset_dir>/roundtrip_surformat/`.

```bash
python scripts/run_task4_reverse_conversion.py --dataset-dir demo_data/surlab_format_demo --conversion-table sur_nwb_conversion_table.csv
```

`--dev-max-stage N` limits table rows to `stage <= N` during development. Omit it for a full reverse. Log: `runlog.txt` in the dataset directory.

Windows: `developer_scripts/run_task4_reverse_conversion_win.bat`

Read rules (primary field, `nwb_alt_fieldnames`, optional ecosystem CSV) are in the [conversion notes](docs/nwb_conversion_notes.md). Ecosystem file layout is in `reverse_mapping/README.md`.

## Round-trip validation

One command:

1. Snapshot the original SurLab files
2. Forward conversion and PyNWB validation
3. Reverse conversion
4. Compare every conversion-table check: original SurLab versus the round-trip files

Round-trip files are read from `<session_dir>/roundtrip_surformat/` when that folder exists.

The process exits **1** only when at least one value mismatches. A PyNWB validation failure is recorded in the summary and does not by itself change the exit code.

```bash
python scripts/run_roundtrip_validation.py --dataset-dir demo_data/surlab_format_demo --conversion-table sur_nwb_conversion_table.csv
```

All-modality synthetic session:

```bash
python scripts/run_roundtrip_validation.py --dataset-dir demo_data/kitchen_sink_demo
```

Windows: `developer_scripts/run_roundtrip_validation_win.bat`, or `run_roundtrip_kitchen_sink_demo.bat` for the kitchen-sink dataset.

Outputs:

- Per session: `roundtrip_validation_report.csv`
- Dataset: `roundtrip_validation_summary.csv`
- Log: `runlog_roundtrip_validation.txt`

Summary columns: `session`, `session_key`, `forward_ok`, `reverse_ok`, `n_match`, `n_mismatch`, `n_skipped_original_missing`, `n_skipped_roundtrip_missing`, `n_skipped_non_comparable`, `nwb_validation_passed`, `nwb_validation_note`, `report_file`.

Per-check columns include `nwb_value`, `nwb_note`, and `likely_owner` (`task2_forward`, `task4_reverse`, `both_or_table_gap`, `data_or_spec`, `task4_not_exported`).
