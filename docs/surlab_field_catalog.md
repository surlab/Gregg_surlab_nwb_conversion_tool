# SurLab field catalog

Column names, schema keys, and per-modality fields. Folder layout, filename rules, and the session clock are in the [format basics](surlab_format_basics.md). NWB targets are in the [conversion notes](nwb_conversion_notes.md).

`sur_nwb_conversion_table.csv` is the list the converter and the format validator read. If this catalog and that CSV disagree about a field the tools enforce, the CSV wins. This page is the version meant to be read while writing a session.

Names follow the basics page: `snake_case` headers, `_ID` identifier columns, `__unit` on numeric quantities, and `{datatypeID}_{field}` for per-stream scalars in `sessionInfo`.

## Datatype IDs

A full datatype ID is `<prefix>_<baseID>` when a prefix is used (`GCaMP8m_traces`), or the base ID alone when the stream is fixed (`spikeTimes`, `lfp`, `spikeWaves`, `trialInfo`). Prefixes are lab labels, not a global vocabulary. Document a new one in the dataset README.

| Base ID | Example full ID | Typical content |
| :---- | :---- | :---- |
| `traces` | `GCaMP8m_traces`, `tdTomato_traces`, `F_chan2_traces` | One fluorescence product or channel |
| `behTSeries` | `pupil_behTSeries`, `wheel_behTSeries` | Continuous behavior |
| `behEvents` | `lick_behEvents`, `lever_behEvents` | Event-time vectors |
| `spikeTimes`, `spikeWaves`, `lfp`, `trialInfo` | same as the base ID | One stream of that kind per session |

`trialInfo` is not prefixed. There is one boolean column `trialInfo` and one file `trialInfo.csv`.

## sessionInfo

**Files.** `sessionInfo_<datasetID>.csv` at the dataset root (one row per session), and `sessionInfo_single_session.csv` in each session folder (same columns, one row).

Required subject columns must be in the written CSV even when the raw acquisition folder did not have them. Fill them from a dataset-level config or sidecar at ingest, then write both sessionInfo files.

### Required columns

| Column | Contents |
| :---- | :---- |
| `institution` | Institution name, e.g. `MIT` |
| `lab` | Laboratory name, e.g. `SurLab` |
| `experimenter` | Full name of the person who collected the data |
| `animal_ID` | Animal identifier |
| `session_ID` | Session identifier |
| `session_date` | Session start date, `YYYY-MM-DD` |
| `species` | Latin binomial, e.g. `Mus musculus` |
| `sex` | `M`, `F`, `O` (other), or `U` (unknown) |
| `age__days` | Age in days, numeric. See below. |
| `strain` | Background or line, e.g. `C57BL/6`, or `Wild Type` |

**`age__days`.** Put a real number in this cell. `U` and `UNKNOWN` are not valid here (`U` is only for `sex`). If age is truly unknown, leave the cell empty or `nan`. Use `0` only when a filled cell cannot be avoided and the zero is an obvious placeholder. Forward conversion is specified to refuse a session with missing, empty, or non-positive age unless the caller explicitly allows it. Details of the NWB duration string are in the conversion notes.

### Optional session columns

| Column | Contents |
| :---- | :---- |
| `zero_time` | Datatype ID of the stream aligned to t = 0, e.g. `GCaMP8m_traces`. Provenance only. |
| `area` | Recording area name or names, comma-separated when several areas were recorded together |
| `condition` | Experimental condition label |
| `related_publication` | Citation, including a DOI when there is one |

Instrument readouts such as laser power, PMT gain, or Pockels values are often in arbitrary instrument units. Store the number in its own column and add a separate calibration column when you can convert it to a physical unit.

### Stream flags and per-stream scalars

Each recorded stream gets its own `0`/`1` column. The header is the full datatype ID: `GCaMP8m_traces`, `pupil_behTSeries`, `lick_behEvents`, `spikeTimes`, `lfp`, `trialInfo`. There is no shared `traces` or `behEvents` flag.

Single-value stream metadata uses `{datatypeID}_{field}`:

- `spikeTimes_probe`
- `spikeTimes_sorting_software`
- `GCaMP8m_traces_indicator`
- `pupil_behTSeries_sample_frequency__Hz`

Those columns are the canonical copy. The same key may also appear, unprefixed, inside `<datatypeID>_schema.json` as a legacy mirror. If both are filled and they differ, conversion fails. If only one is filled, that value is used. NWB receives one write.

### Column order

Parsers accept any order. Writers should emit columns in this order:

| Tier | Block | Examples |
| :---- | :---- | :---- |
| 1 | Required session metadata | `institution`, `lab`, `experimenter`, `animal_ID`, `session_ID`, `session_date`, `species`, `sex`, `age__days`, `strain` |
| 2 | Optional session metadata | `zero_time`, `area`, `condition`, `related_publication` |
| 3 | Stream flags (`0`/`1`) | `spikeTimes`, `lfp`, `GCaMP8m_traces`, `pupil_behTSeries`, `trialInfo` |
| 4 | Stream scalars, grouped by stream | all `spikeTimes_*` columns, then all `GCaMP8m_traces_*` columns |
| 5 | Lab-specific extras | columns that are not in the standard lists |

## Schema JSON

`<datatypeID>_schema.json` is optional. A session can validate from sessionInfo plus the arrays.

| Key | Meaning |
| :---- | :---- |
| `data_unit_measurement` | Unit tag for the stored array, `base__unit` form (`amplitude__V`). Canonical copy: `{datatypeID}_data_unit_measurement` in sessionInfo. |
| `sample_frequency__Hz` | Sampling frequency in Hz. Canonical copy is the sessionInfo column of the same field name. |
| `X_dim` / `Y_dim` | Labels for axis 0 and axis 1. Continuous streams: `X_dim = time`, `Y_dim` is `ROI`, `features`, or `channel`. `spikeWaves`: `X_dim = waveform_sample`, `Y_dim = unit`. |
| `X_size` / `Y_size` | Length of axis 0 and axis 1. Taken from the array shape. Not sessionInfo columns. |
| `X_idx` / `Y_idx` | Coordinates along each axis. Time values are seconds on the session clock. Continuous streams usually use the timestamps file instead of `X_idx`. Omitted for `spikeTimes`. |

`X_*` is axis 0 and `Y_*` is axis 1. When both a size and an index are present, their lengths match.

## Optical physiology (`traces`)

**Files.** `<datatypeID>_data.npz`, `<datatypeID>_timestamps.npz`, `<datatypeID>_metadata.csv`, optional schema.

**Shape.** Matlab `[time × ROIs]`. Python `(n_time, n_ROI)`. Transpose Suite2p `(n_ROI, n_time)` before writing.

**sessionInfo scalars** (`{datatypeID}_{field}`):

| Field | Notes |
| :---- | :---- |
| `microscope` | Recommended. Short rig name, e.g. `Bruker_Ultima`. |
| `microscope_description` | Optional rig notes (scan path, software). |
| `detection_software` | e.g. `Suite2p` |
| `indicator` | e.g. `GCaMP8m` |
| `wavelength__nm` | |
| `pixel_size__um` or `pixel_size__au` | One or the other, not both |
| `pixel_size_calibration` | How pixel size was obtained, when relevant |
| `objectives` | |
| `laser_name` | |
| `fov_width__pixels`, `fov_height__pixels`, `fov_depth__um` | |
| `data_unit_measurement` | |
| `sample_frequency__Hz` | Descriptive. Timestamps stay authoritative. |

Two simultaneous fields of view are two datatype IDs (or per-ROI fields in metadata), not two FOV values on one stream.

**Metadata** (one row per ROI): `roi_ID`, `roi_x_coordinates`, `roi_y_coordinates`, `roi_center_x`, `roi_center_y`, `area`, `depth__um`. Singular `roi_x_coordinate` / `roi_y_coordinate` are accepted as legacy aliases. Extra columns (for example a fluorophore class) are lab-specific.

NWB placement for this stream is in the conversion notes (Device, ImagingPlane, RoiResponseSeries, and `SurLabSchema_<datatypeID>`).

## Spike times (`spikeTimes`)

**Files.** `spikeTimes_data.npz`, `spikeTimes_metadata.csv`, optional schema. No timestamps file. Times live in the spike arrays, in seconds on the session clock.

**Shape.** Matlab `{1 × n_units}` cell of `[1 × n_spikes]` vectors. Python object array of shape `(1, n_units)`, each element a 1-D float array.

**sessionInfo scalars.** `probe` is required when `spikeTimes` is `1`. Also: `acquisition_software`, `sorting_software`, `filter_type`, `filter_cutoff_low__Hz`, `filter_cutoff_high__Hz`, `quality_metric`, `data_unit_measurement`, `sample_frequency__Hz`.

**Metadata** (one row per unit): `unit_ID`, `depth__um`, `area`, `spike_sorting_ID`, `quality`, `grid_location` (row, column). `quality` may be a number or a label. `quality_metric` says which.

## Spike waveforms (`spikeWaves`)

**Files.** `spikeWaves_data.npz`, `spikeWaves_metadata.csv`, optional schema. Optional `spikeWaves_timestamps.npz` holds snippet-relative sample times (seconds from the start of the waveform), not session time.

**Shape.** Matlab `[waveform sample × units]`. Python `(n_waveform_samples, n_units)`.

**sessionInfo scalars.** `probe`, `clustering_algorithm`, `sample_frequency__Hz` (snippet rate), `data_unit_measurement`.

**Metadata** (one row per unit): `unit_ID`, `primary_channel` (matches LFP `channel_ID` when both exist).

Do not put `area` on the spike-waveform metadata table. Brain area for a unit lives on `spikeTimes_metadata` (`area`). A legacy `area` column here is a known bad pattern: the validator warns, and the value must match `spikeTimes_metadata` for the same `unit_ID`. It is not written to NWB.

## Local field potentials (`lfp`)

**Files.** `lfp_data.npz`, `lfp_timestamps.npz`, `lfp_metadata.csv`, optional schema.

**Shape.** Matlab `[time × channels]`. Python `(n_time, n_channels)`. Axis 0 matches `lfp_timestamps`. Transpose a legacy channels-by-time array on ingest.

**sessionInfo scalars.** `probe`, `filter_type`, `filter_cutoff_low__Hz`, `filter_cutoff_high__Hz`, `data_unit_measurement`, `sample_frequency__Hz`.

**Metadata** (one row per channel): `channel_ID`, `channel_label`, `area`, `depth__um`, `channel_x_coordinate`, `channel_y_coordinate`, `grid_location`. Lateral coordinates are optional.

## Behavioral time series (`behTSeries`)

**Files.** `<datatypeID>_data.npz`, `<datatypeID>_timestamps.npz`, `<datatypeID>_metadata.csv`, optional schema. Example ID: `pupil_behTSeries`.

**Shape.** Matlab `[time × features]`. Python `(n_time, n_features)`.

**sessionInfo scalars.** `data_unit_measurement`, `sample_frequency__Hz`.

**Metadata** (one row per feature): `feature_ID`, `feature_label`. DeepLabCut-style names (`tongue_x`, `tongue_likelihood`) belong in `feature_label`. Row `i` lines up with data column `i`.

## Behavioral events (`behEvents`)

**Files.** `<datatypeID>_data.npz`, `<datatypeID>_metadata.csv`, optional schema. No timestamps file. Example ID: `lick_behEvents`. Prefer a prefix so each event family is its own stream.

**Shape.** Matlab `{1 × n_event_types}` cell of time vectors. Python object array of shape `(1, n_event_types)`. Times are seconds on the session clock.

**sessionInfo scalars.** None required beyond the `0`/`1` flag column named `<datatypeID>`.

**Metadata** (one row per event type): `event_ID`, `event_label`. Row `i` lines up with object-array index `i`.

Older names `lever`, `licking`, `pupil`, and `movement` are retired. Use `behEvents` or `behTSeries`.

## trialInfo

**File.** `trialInfo.csv` in the session folder. Set `trialInfo` to `1` in sessionInfo when the file is present. One table per session.

One row per trial. Only two columns are required. Everything else is optional, and a missing optional column is not a warning. Include the columns the experiment uses.

CSV time columns use 4 decimal places (tenths of a millisecond).

### Required

| Column | Contents |
| :---- | :---- |
| `start_time__s` | Trial start, seconds from the session origin |
| `stop_time__s` | Trial end, seconds from the session origin |

### Stimuli (optional)

| Column | Contents |
| :---- | :---- |
| `stimulus_onset__s` | Stimulus onset (s) |
| `stimulus_offset__s` | Stimulus offset (s) |
| `tone_frequency__Hz` | Tone frequency |
| `tone_intensity__dB` | Sound level (dB) |
| `grating_orientation__degrees` | Grating orientation |
| `grating_spatial_frequency__cycles_per_degree` | Cycles per degree. Document a different convention in the dataset README. |
| `grating_drift_speed__m_per_s` | Drift speed |
| `grating_drift_direction__degrees` | Drift direction |

Repeated events of the same kind add an integer after the unit: `stimulus_onset__s_1`, `stimulus_onset__s_2`.

### Action, score, reinforcement (optional)

| Column | Contents |
| :---- | :---- |
| `action` | What the animal did. Extensible labels: `press`, `early_press`, `no_press`, `lick`, `early_lick`, `left_lick`, `right_lick`, `no_lick`. `early_press` belongs only in this column. Legacy header `output` is accepted on read as an alias for `action`. |
| `trial_type` | Signal-detection label when the trial was scored: `hit`, `miss`, `fa`, `cr`, or `aborted`. `early_press` is not a `trial_type` value. Omit the column for passive viewing. |
| `correct` | `correct` or `incorrect` when a judgment applies. Leave the cell empty when it does not (passive viewing, `early_press`). Do not write `early_press` here. On read, `error` becomes `incorrect`, and `0`/`1` become `incorrect`/`correct`. |
| `reaction_time__s` | Seconds from `stimulus_onset__s`. Unknown values use the token `NaN`, not a blank cell. |
| `num_licks` | Integer lick count in the trial |
| `reward` | Boolean: reward delivered |
| `punish` | Boolean: punishment delivered |

A go/no-go condition label has no standard column yet. Keep it as a lab-specific column and describe it in the dataset README.

Optional float cells that are present but unknown (`reaction_time__s`, a stimulus time) use the token `NaN`. Empty cells are for string columns such as `correct`.

Early-press trials in the SeqBias style: `action=early_press`, `correct` empty, `trial_type=aborted`.

Passive viewing typically uses the stimulus columns and omits `action`, `correct`, and `trial_type`. An auditory operant task adds `tone_frequency__Hz`, `tone_intensity__dB`, and the action columns it scores.
