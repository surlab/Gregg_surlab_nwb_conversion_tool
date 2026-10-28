# NWB conversion notes

How SurLab fields are written to NWB, and how NWB is read back. Folder layout is in the [format basics](surlab_format_basics.md). SurLab column names are in the [field catalog](surlab_field_catalog.md).

The converter reads `sur_nwb_conversion_table.csv` at the repo root. An optional handoff copy may live under `for_cursor/`; keep it identical to the root file. If this page and the CSV disagree about a placement the code follows, the CSV wins.

Implementation notes that led to the current rules:

- Forward placement: `for_cursor/task2_implementation_decisions_and_answers.txt` (section E)
- Reverse and round-trip: `for_cursor/task4_implementation_decisions_and_answers.txt`

`stage` in the table is development bookkeeping only (`1` session metadata, `2` spike times, `3` traces, `4` behTSeries, `5` trialInfo, `6` lfp, `7` spikeWaves, `8` behEvents). The forward converter writes one NWB file per session. `--stage` / `--dev-max-stage` only limit which table rows run during incremental work. NWB targets marked **SPECULATIVE** in `mapping_rationale` are still followed until the table is updated.

## What the converter reads

Presence of a stream is inferred from filenames in the session folder first (`spikeTimes_data*.npz` means `spikeTimes` is present). sessionInfo flags are secondary. Resolution is in `src/surlab_paths.py`: minimal name first, then a verbose `<stem>*.<ext>` alias.

Legacy sessionInfo headers (`animalID`, `sessID`, and similar) are renamed to the canonical headers in memory on read. The validator accepts canonical names only. Forward conversion does not rewrite the CSV on disk.

Columns that are not listed in the table are appended to `NWBFile.experiment_description` as key=value text (interim; the table’s `dataset_specific` row). Session-level LabMetaData is the intended later home.

`NWBFile.identifier` is generated as `{animal_ID}__{session_ID}`. It is not a SurLab column. The row token is `(derived_file_identifier)`.

## Placement columns

Until a deferred `nwb_path` column exists, code reads `nwb_location` and `nwb_fieldname`. Each row names one destination. Rows that map sessionInfo flags onto `NWBFile.keywords` also set `nwb_keyword`.

1. `nwb_location` finds or creates the container (`NWBFile`, `NWBFile/general/subject`, `NWBFile/units`, `NWBFile/devices`, `NWBFile/acquisition`, `NWBFile/intervals/trials`, `NWBFile/ophys/RoiResponseSeries`, `NWBFile/processing`). Slashes are hierarchy.
2. `nwb_fieldname` is the one field written on that container.
3. Reserved tokens below are still one destination.
4. `mapping_rationale` and `notes` are for people. The two placement columns are what the code follows.

| `nwb_fieldname` token | Meaning |
| :---- | :---- |
| `custom_field` | Rare custom attribute on a core container. Prefer `SurLabSchema_*` LabMetaData for leftovers. |
| `custom_column_<name>` | Named custom column on the table at `nwb_location`. |
| `custom_columns` | `dataset_specific` row: keep each extra column under its SurLab header. |
| `id` | Row id column of a DynamicTable. |
| `validate_only` | Checked by the SurLab format validator. Not written to NWB. |
| `N/A` | Nothing to write (rule, provenance, or absent-file row). |
| `*` | Wildcard keys inside a LabMetaData container (unlisted schema keys). |

Per-stream leftovers use `nwb_location = NWBFile/lab_meta_data/SurLabSchema_<datatypeID>`.

### Keywords

`nwb_keyword` is set only on rows whose `nwb_fieldname` is `keywords`.

| `fieldname_surlab` | `nwb_keyword` | When the flag is `1` |
| :---- | :---- | :---- |
| `trialInfo` | `trials` | append keyword `trials` |
| `spikeTimes` | `spike_times` | append keyword `spike_times` |
| `spikeWaves` | `spike_waveforms` | append keyword `spike_waveforms` |
| `lfp` | `lfp` | append keyword `lfp` |
| `(per_stream_traces)` | `identity` | append the column header when it ends in `_traces` |
| `(per_stream_behTSeries)` | `identity` | append the column header when it ends in `_behTSeries` |
| `(per_stream_behEvents)` | `identity` | append the column header when it ends in `_behEvents` |

Reverse inverts the fixed rows via `nwb_keyword`. For `identity` rows, any keyword ending `_traces`, `_behTSeries`, or `_behEvents` becomes a boolean column set to `1`.

### `nwb_type` tokens

Use one of these on every data or metadata row. Bare `array` and bare `variable` are rejected; they cannot be type-checked. A union (`float_or_str`) is a set of acceptable value types, not a choice of NWB destinations.

| `nwb_type` | Value rule |
| :---- | :---- |
| `str` | Non-empty text. `sex` is one of `M`, `F`, `O`, `U`. |
| `str_or_array_of_str` | String or list of strings (`experimenter`). |
| `array_of_str` | List of strings. Used with `nwb_fieldname=keywords`. |
| `int` | Integer cell. The unit is in the header. |
| `int_or_str` | Integer or non-empty string (IDs). |
| `float` / `float64` | Float cell. The unit is in the header. Treated the same by the validator. |
| `float_or_str` | Float or non-empty string (`quality`). |
| `bool` | `0`/`1`. `true`/`false`/`yes`/`no` are accepted on read. |
| `datetime` | SurLab `YYYY-MM-DD`, stored as an NWB datetime. |
| `array_of_float` | 1-D list of floats (schema `X_idx`, seconds). |
| `array_of_float64` | Same check as `array_of_float`; marks float64 storage on `data_array` / `timestamps_array` rows. |
| `array_of_int_or_str` | 1-D list of ints and/or strings (schema `Y_idx`). |
| `N/A` | Skip the type check. |
| `same` | Mirror row (single-session sessionInfo matches the dataset sessionInfo row). |

| Token | Format validator | SurLab → NWB |
| :---- | :---- | :---- |
| `nwb_fieldname = validate_only` | Type-checks the SurLab value and layout | Does not write |
| `nwb_type = N/A` | Skips the type check | Usually nothing to write |
| `X_size` / `Y_size` / index lengths | When present: `len(X_idx) == X_size` and `len(Y_idx) == Y_size` | Ignored |
| `data_array` / `timestamps_array` | File present if required, loadable, numeric dtype, shape versus schema sizes or the paired timestamps | Written per the table |

Run the format check with:

```bash
python scripts/run_surlab_format_validation.py --dataset-dir demo_data/surlab_format_demo
```

### Exceptions to a direct copy

| Case | What happens |
| :---- | :---- |
| `requirement_level = na` or `nwb_fieldname = N/A` | Not written. |
| `requirement_level = not-recommended` | Documented bad pattern (spike-waveform `area`). Validator warns. May require a match to `spikeTimes_metadata.area` per `unit_ID`. Not written. |
| `nwb_fieldname = validate_only` | Format-checked, not written. Different from `nwb_type = N/A`, which skips the type check. |
| `(derived_file_identifier)` | Converter sets `NWBFile.identifier`. |
| `mapping_rationale` contains `SPECULATIVE` | Follow the listed columns until the table is updated. |
| Missing NWB scaffolding | Microscope `Device` comes from `{datatypeID}_microscope` when that column is present. Other ImagingPlane geometry without a SurLab value is marked `MISSING_REQUIRED_FOR_NWB`. Do not invent a scientific value to fill a required NWB field. |
| Age | See below. |
| Session date | `session_date` → `session_start_time`. The converter parses `YYYY-MM-DD` (and, on read, `MM-DD-YYYY` or `MM/DD/YYYY`) and stores midnight UTC when the source has no time of day. |

### Age

`age__days` is a number of days in SurLab and an ISO-8601 duration on `Subject.age` (`P90D` for 90 days). `U` and `UNKNOWN` are invalid. The format spec says forward conversion must refuse missing, empty, or non-positive age unless the caller explicitly allows it.

Current code (`normalize_age_days` in `src/session_record.py`) raises on a negative value, returns nothing for empty, `U`, `UNKNOWN`, `NA`, or `//`, and then skips the `Subject.age` write. There is no `--allow-missing-age` flag yet.

### Session clock in NWB

NWB has no top-level `zero_time`. Each object's `timestamps`, `starting_time`, and trial interval columns carry time on one session base, relative to `session_start_time`. Copy SurLab times through as stored. Do not re-zero a stream.

When the `zero_time` column is present, its datatype ID is written to `NWBFile.notes` as `SurLab zero_time=<datatypeID>`. When the column is absent, skip it. A later `nwb_path` may move this into LabMetaData.

A clock mismatch (no stream sample at about 0) is a warning only.

### Odd placements

| SurLab source | `nwb_location` | `nwb_fieldname` | Why |
| :---- | :---- | :---- | :---- |
| Extra sessionInfo columns (`dataset_specific`) | `NWBFile` | `experiment_description` | Lab-specific keys go into free text until session-level LabMetaData exists. |
| `zero_time` | `NWBFile` | `notes` | Provenance string. No core `zero_time` field. |
| `area` (session-level) | `NWBFile/general/subject` | `description` | Region text on `Subject.description` at the session-metadata step. |
| `acquisition_software` (spikeTimes) | `NWBFile/devices` | `Device.description` | Software name, not `manufacturer`. |
| `probe` (spikeTimes) | `NWBFile/devices` | `Device.name` | Probe id is the device name. |
| Filter cutoffs / filter type | `NWBFile/lab_meta_data/SurLabSchema_spikeTimes` or `SurLabSchema_lfp` | field key | No core NWB filter object. |
| spikeTimes / spikeWaves `data_unit_measurement` | matching `SurLabSchema_*` | `data_unit_measurement` | Round-trip token. Spike times in NWB are seconds. `Units.waveform_unit` is fixed by NWB. |
| Schema `X_dim`, `X_size`, … | `NWBFile` | `validate_only` | Format validator only. |
| Ophys leftovers (FOV, pixel size, detection software, …) | `SurLabSchema_<datatypeID>` | field key | No honest core attribute. |
| behTSeries data / timestamps | `NWBFile/acquisition/<datatypeID>` | `data` / `timestamps` | Stock `TimeSeries`. |
| behTSeries `feature_ID` / `feature_label` | `NWBFile/processing/behavior/<datatypeID>_features` | column name | Stock DynamicTable. Row `i` is data column `i`. |
| `{datatypeID}_microscope` | `NWBFile/devices` | `Device.name` | Linked from that stream's `ImagingPlane.device`. |
| `{datatypeID}_microscope_description` | same Device | `Device.description` | Rig notes, not detection software. |
| LFP data / timestamps | `NWBFile/acquisition/lfp` | `data` / `timestamps` | Stock `ElectricalSeries` named `lfp`. |
| LFP channel metadata | `NWBFile/general/extracellular_ephys/electrodes` | `id`, `location`, `x`, `y`, `z`, custom columns | LFP-only table. `ElectricalSeries.electrodes` is a `DynamicTableRegion`. |
| LFP `sample_frequency__Hz` when timestamps exist | `SurLabSchema_lfp` | `sample_frequency__Hz` | PyNWB forbids `rate` and `timestamps` on the same series. |
| behEvents times | `NWBFile/acquisition/<datatypeID>` | `AnnotationSeries.timestamps` | Times are in the data object-array. |
| behEvents `event_ID` / `event_label` | `NWBFile/processing/behavior/<datatypeID>_events` | column name | Row `i` is object-array index `i`. |
| Unlisted metadata columns | table at `nwb_location` | `custom_columns` | Names come from the CSV header at runtime. |

Scalar fields are linked to the NWB object for that stream, not to “the first device in the file.” Examples: `spikeTimes_probe` is the `Device` linked to `Units`; `lfp_probe` is the device linked to the LFP series; `GCaMP8m_traces_indicator` is the `OpticalChannel` / `ImagingPlane` for that `RoiResponseSeries`. One physical probe may fill both `spikeTimes_probe` and `lfp_probe` on reverse. Several ophys streams may share one Device name or use different ones.

## Per-stream LabMetaData

Each SurLab value has one NWB target. Core values use real PyNWB attributes. Layout that is already implied by the arrays is `validate_only`. Remaining stream scalars go in one LabMetaData container per stream:

`NWBFile.lab_meta_data["SurLabSchema_<datatypeID>"]`

Table path: `nwb_location = NWBFile/lab_meta_data/SurLabSchema_<datatypeID>`, `nwb_fieldname` = the key, or `*` for unlisted schema keys.

The canonical scalar is the sessionInfo column `{datatypeID}_{field}`. Optional schema JSON is a legacy mirror of the same target. Reverse rebuilds both from core NWB fields plus this container. It does not parse prose in `description` or `notes` to recover scalars (the `zero_time` notes string is the exception above).

### Traces

| Class | SurLab fields | NWB |
| :---- | :---- | :---- |
| Core | data, timestamps, `microscope`, `data_unit_measurement`, `sample_frequency__Hz`, `wavelength__nm`, `indicator`, `roi_ID` and ROI columns | `Device.name` and `ImagingPlane.device`; `RoiResponseSeries.data` / `.timestamps` / `.unit`; `ImagingPlane.imaging_rate` (timestamps stay authoritative); `OpticalChannel.emission_lambda` and `.name`; PlaneSegmentation / ROI `custom_column_*` |
| `validate_only` | `X_dim`, `Y_dim`, `X_size`, `Y_size`, `X_idx`, `Y_idx` | Not written. `X_idx` is ignored even if it sits beside a timestamps file. |
| LabMetaData | `detection_software`, `objectives`, `laser_name`, `pixel_size__um` or `__au`, `pixel_size_calibration`, FOV sizes and depth, unlisted schema keys | Keys on `SurLabSchema_<datatypeID>` |

**Microscope Device.** Stock PyNWB `Device`, linked from `ImagingPlane.device`.

| SurLab | NWB |
| :---- | :---- |
| `{datatypeID}_microscope` (recommended) | `Device.name` |
| `{datatypeID}_microscope_description` (optional) | `Device.description` |
| schema keys `microscope` / `microscope_description` | same targets; fail if they disagree with sessionInfo |
| (derived) | `ImagingPlane.device` for this stream |

Good `Device.name` values are short scope identities (`Bruker_Ultima`, `Femtonics_Atlas`, `Thorlabs_Bergamo_II`). Scan hardware and acquisition software belong in `microscope_description` (`resonant + galvo; Prairie View 5.4`).

One NWB Device per distinct name; streams that repeat the same name share it. `objectives`, `detection_software`, `laser_name`, and `indicator` stay in SurLabSchema or on `OpticalChannel`. If `{datatypeID}_microscope` is absent, the device name is the placeholder `MISSING_REQUIRED_FOR_NWB`. The format validator warns when two or more `_traces` streams set microscope and the values disagree.

Demo: `demo_data/tricolor_projections/` (`GCaMP8m_traces` and `Neuropil_traces` share `Bruker_Ultima`).

The same LabMetaData container is used for behTSeries, LFP, spikeTimes, spikeWaves, and behEvents (`SurLabSchema_<datatypeID>`, or the fixed ids `SurLabSchema_lfp`, `SurLabSchema_spikeTimes`, `SurLabSchema_spikeWaves`). Optional `spikeWaves_timestamps` land as the LabMetaData key `snippet_timestamps`.

### behTSeries

Stock `TimeSeries` plus a `DynamicTable`. No ndx-pose extension and no custom TimeSeries subclass.

| SurLab | NWB |
| :---- | :---- |
| `<datatypeID>_data.*` | `NWBFile/acquisition/<datatypeID>` → `TimeSeries.data` |
| `<datatypeID>_timestamps.*` | same object → `TimeSeries.timestamps` |
| `data_unit_measurement` | `TimeSeries.unit` |
| `sample_frequency__Hz` | `TimeSeries.rate` only when it is used; timestamps stay authoritative |
| `<datatypeID>_metadata.csv` | `NWBFile/processing/behavior/<datatypeID>_features` |
| `X_*` / `Y_*` | `validate_only` |
| Rare schema leftovers | `SurLabSchema_<datatypeID>` (`ndx-surlab-schema` / `SurLabSchemaMeta.schema_json`) |

One TimeSeries per stream, named with the full datatype ID. Canonical shape `(n_time, n_features)`; transpose on ingest when needed. The feature table is under a processing module named `behavior`. `feature_ID` and `feature_label` are named columns. Extra metadata columns become extra table columns. Row `i` corresponds to data column `i`. That alignment is a convention: core `TimeSeries` has no features slot, and a `DynamicTableRegion` would need an extension, which this path does not use. Core arrays and feature identity are not stored only in LabMetaData.

Forward names for the TimeSeries and the feature table both come from `<datatypeID>`, so reverse can find the stream from acquisition names or from keywords ending `_behTSeries`.

### LFP

Stock `ElectricalSeries` plus the electrodes table.

| SurLab | NWB |
| :---- | :---- |
| `lfp_data.*` | `NWBFile/acquisition/lfp` → `ElectricalSeries.data` |
| `lfp_timestamps.*` | same object → `ElectricalSeries.timestamps` |
| `lfp_data_unit_measurement` | `ElectricalSeries.unit` |
| `lfp_sample_frequency__Hz` | `SurLabSchema_lfp` key `sample_frequency__Hz` when timestamps are written |
| `lfp_metadata.csv` | `NWBFile/general/extracellular_ephys/electrodes` |
| `depth__um` | electrode `z` |
| `channel_x_coordinate` / `channel_y_coordinate` | electrode `x` / `y` (`NaN` when absent) |
| `area` | `location` |
| `lfp_probe` / schema `probe` | `Device.name` and one `ElectrodeGroup` on that Device |
| Filters, layout keys, unlisted schema | `SurLabSchema_lfp` or `validate_only` |

Fixed object name `lfp`. Canonical shape `(n_time, n_channels)`. One electrode row per channel. `ElectricalSeries.electrodes` is a `DynamicTableRegion` over rows `[0 .. n_channels-1]`. This electrodes table is built only from `lfp_metadata.csv`; it is not merged with `Units` rows. `add_electrode` requires `imp` and `filtering`; those are `MISSING_REQUIRED_FOR_NWB` when SurLab does not supply them.

Demo: `demo_data/surlab_format_demo/AstroDREADD25_20240702/`.

### behEvents

Same companion-table pattern as behTSeries. Acquisition is an `AnnotationSeries`. The table name ends in `_events`.

| SurLab | NWB |
| :---- | :---- |
| `<datatypeID>_data.*` (object array of 1-D time vectors) | `NWBFile/acquisition/<datatypeID>` → `AnnotationSeries` |
| times in each vector | `AnnotationSeries.timestamps` (seconds, session origin) |
| (derived) | `AnnotationSeries.data` = ones, the PyNWB convention |
| unit token | `description` / documented semantics (`time__s`) |
| `<datatypeID>_metadata.csv` | `NWBFile/processing/behavior/<datatypeID>_events` |
| `X_*` / `Y_*` | `validate_only` |
| Rare schema leftovers | `SurLabSchema_<datatypeID>` |

Object name is the full datatype ID (`lick_behEvents`). One event type: one `AnnotationSeries` with that name. Several event types (`Y_size > 1`): one `AnnotationSeries` per metadata row, named `<datatypeID>_<event_label>` after sanitizing the label for NWB name rules. Row `i` corresponds to object-array index `i`. `DynamicTableRegion` is not used. The events table lives under processing module `behavior`.

Demo: `demo_data/surlab_format_demo/AstroDREADD25_20240702/` (`lick_behEvents`).

## Reverse conversion (NWB → SurLab)

Forward conversion ignores this section.

Reverse writes under `<session_dir>/roundtrip_surformat/` (override with `--output-subdir`). For each implemented stream present in the NWB file it writes the SurLab data, metadata, timestamps, and schema files, using verbose filenames and `.npz` arrays. It also writes `sessionInfo_single_session.csv` in that folder and `sessionInfo_<datasetID>.csv` under `<dataset_dir>/roundtrip_surformat/`. A `reverse_conversion_report.csv` is written next to the dataset sessionInfo. The log is `<dataset_dir>/runlog.txt`.

Implemented exports: sessionInfo, `spikeTimes`, `*_traces`, `*_behTSeries`, `trialInfo`, `lfp`, `spikeWaves`, `*_behEvents`.

Array layout is inverted when forward conversion transposed on ingest. Each scalar is written to both the sessionInfo column and the schema key.

### Where a value is read from

1. Primary `nwb_location` + `nwb_fieldname`, with stream linkage from `mapping_rationale` (the Device linked to `Units`, not the first device in the file).
2. `nwb_alt_fieldnames` on that same row: semicolon-separated names on the same container (for example `brain_area;location` when the primary field is `custom_column_brain_area`). Always considered.
3. `reverse_mapping/<ecosystem>.csv`, only when the user names a source format (`--reverse-ecosystem allen` or `ibl`). Not loaded by default. Column layout and the Allen / IBL files are documented in [`reverse_mapping/README.md`](../reverse_mapping/README.md).

The first non-empty value wins. Output is always canonical SurLab (`fieldname_surlab`, plus the schema mirror when that applies). If the primary value and a fallback are both non-empty and they differ, warn and keep the primary. Empty versus filled is not a conflict. The reverse report records which layer supplied each field.

`nwb_alt_fieldnames` are renames on the same container. A different container is a rare escape: prefix with `/`, the location, `|`, and the field (`/NWBFile|experiment_description`). Prefer an ecosystem CSV for that case. Heavier cross-container reads belong in `reverse_mapping/*.csv`.

Add a new source archive as `reverse_mapping/<name>.csv`. That does not require editing the primary conversion table.
