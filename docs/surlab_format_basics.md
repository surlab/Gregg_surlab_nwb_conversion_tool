# SurLab format basics

The SurLab format is a flat folder layout for preprocessed neurophysiology and behavior. One dataset folder holds many session folders. Each session folder holds arrays (`.npz` or `.mat`), small CSV tables, and an optional JSON schema.

This page is the short description: folders, filenames, the shared clock, and which modalities exist. Column names are in the [field catalog](surlab_field_catalog.md). How those fields are written into NWB is in the [conversion notes](nwb_conversion_notes.md).

When a human doc and `sur_nwb_conversion_table.csv` disagree about a field the converter uses, the CSV wins.

A real session that follows this layout is `demo_data/surlab_format_demo/`. Optical traces and continuous behavior are in `demo_data/tricolor_projections/`.

## Dataset and session folders

A **dataset** is one folder. Its name is the `datasetID` (for example `surlab_format_demo`).

A **session** is one subfolder:

```text
<animal_ID>_<session_ID>/
```

Join the two identifiers with a single underscore, as written in `sessionInfo`. `session_ID` may contain dots. Example: `animal_ID = mouse01` and `session_ID = exp101.a1.20260204.gratings` produce `mouse01_exp101.a1.20260204.gratings`. The pair `(animal_ID, session_ID)` is unique inside one dataset. `session_ID` alone does not have to be unique across animals.

```text
<datasetID>/
  experimentDesc.pdf
  sessionInfo_<datasetID>.csv
  <animal_ID>_<session_ID>/
    sessionInfo_single_session.csv
    trialInfo.csv
    <datatypeID>_data.npz
    <datatypeID>_timestamps.npz          # continuous streams
    <datatypeID>_metadata.csv
    <datatypeID>_schema.json             # optional
```

`spikeTimes` and `behEvents` store times inside the data file, so they have no timestamps file. `spikeWaves` may include an optional timestamps file, and those times are snippet-relative (see below).

The canonical ecephys demo looks like this:

```text
demo_data/surlab_format_demo/
  sessionInfo_surlab_format_demo.csv
  AstroDREADD25_20240702/
    sessionInfo_single_session.csv
    trialInfo.csv
    spikeTimes_data.npz
    spikeTimes_metadata.csv
    spikeTimes_schema.json
    spikeWaves_data.npz
    spikeWaves_timestamps.npz
    spikeWaves_metadata.csv
    spikeWaves_schema.json
    lfp_data.npz
    lfp_timestamps.npz
    lfp_metadata.csv
    lfp_schema.json
    lick_behEvents_data.npz
    lick_behEvents_metadata.csv
    lick_behEvents_schema.json
```

## File roles

| File | Role |
| :---- | :---- |
| `experimentDesc.pdf` | Short slide deck for the dataset: overview, task, what was recorded, glossary of lab-specific labels. Usually 3–4 slides. |
| `sessionInfo_<datasetID>.csv` | One row per session. Subject, date, which streams exist, and per-stream scalars. |
| `sessionInfo_single_session.csv` | The same columns, one row, inside the session folder so the folder stands alone. |
| `<datatypeID>_data.npz` | The array for one stream. `.mat` is also valid. Prefer `.npz` for new Python exports. |
| `<datatypeID>_timestamps.npz` | Sample times in seconds for continuous streams, on the session clock. |
| `<datatypeID>_metadata.csv` | One row per unit, ROI, channel, feature, or event type. |
| `<datatypeID>_schema.json` | Optional. Array-layout keys, legacy mirrors of sessionInfo scalars, and lab-specific keys. |
| `trialInfo.csv` | One row per trial. At most one trial table per session. |

If a stream has no data, set its sessionInfo flag to `0` and omit its data, timestamps, metadata, and schema files. Leave a note in the dataset README. An empty `(0, 0)` array with the flag set to `1` is not a stand-in for a missing stream.

## Filenames

Inside a session folder, use **minimal** names. Do not repeat `datasetID`, `animal_ID`, or `session_ID` in the basename. New exports should write minimal names.

Readers also accept a **verbose** alias that inserts `<datasetID>_<animal_ID>_<session_ID>` after the role token. That form is for older exports and for files that have been copied out of the session folder.

| Role | Minimal (write this) | Verbose alias (still accepted) |
| :---- | :---- | :---- |
| Dataset session table | `sessionInfo_<datasetID>.csv` | name still starts with `sessionInfo_` |
| Single-session copy | `sessionInfo_single_session.csv` | — |
| Data | `<datatypeID>_data.npz` | `<datatypeID>_data_<datasetID>_<animal_ID>_<session_ID>.npz` |
| Timestamps | `<datatypeID>_timestamps.npz` | same pattern |
| Metadata | `<datatypeID>_metadata.csv` | same pattern |
| Schema | `<datatypeID>_schema.json` | same pattern |
| Trials | `trialInfo.csv` | `trialInfo_<datasetID>_<animal_ID>_<session_ID>.csv` |

`.mat` may replace `.npz` in either form.

## Names

Two naming styles are intentional.

- **CSV headers and schema keys** use `snake_case` and full words (`session`, `stimulus`, `sample_frequency`). Identifier columns end in `_ID` (`animal_ID`, `session_ID`, `roi_ID`).
- **Datatype IDs and filename stems** may use camelCase (`spikeTimes`, `trialInfo`, `GCaMP7f_traces`). A lab prefix plus a base id, joined by one underscore, is the full datatype ID: `pupil_behTSeries`, `lick_behEvents`.

Standard abbreviations keep their usual capitals (`LFP`, `ROI`, `PMT`, `FOV`). Micrometers are written `um`, not `µ`.

Physical quantities put the unit in the **header**, after a double underscore: `age__days`, `tone_frequency__Hz`, `depth__um`, `sample_frequency__Hz`. The cell is a number. If the scale is uncalibrated, use `__au` (`pixel_size__au`). IDs, software names, and free text have no unit suffix (`probe`, `indicator`). `session_date` is a calendar column (`YYYY-MM-DD`) and has no unit suffix.

The unit of a data array is a separate string column, `data_unit_measurement`, with values like `amplitude__V` or `deltaF_over_F__au`.

Size keys (`X_size`, `Y_size`) do not get a unit suffix.

## Session clock

Every SurLab time shares one origin, t = 0: timestamps files, spike times, `behEvents` times, and `trialInfo` columns that end in `__s`. At least one stream has a sample at exactly 0. Other streams and trials may start before or after that sample, so negative times are valid.

`zero_time` is an optional `sessionInfo` column. When present, it holds the datatype ID of the stream that was aligned to 0 (for example `spikeTimes` or `GCaMP7f_traces`). It records the alignment choice. The times are already on one clock without it.

`spikeWaves_timestamps`, when present, are seconds along the waveform snippet. They are not session-clock times.

## Modalities

Axis 0 is time and axis 1 is ROIs, features, channels, or units, except `spikeWaves`, where axis 0 is the waveform sample. Tools that emit another layout (Suite2p ROI-by-time, or channels-by-time LFP) transpose on the way in.

Resampling is not required. Store native sample times. `sample_frequency__Hz` describes the rate (for example the median). It does not mean the series was resampled onto a grid.

| Data | Datatype ID | Array |
| :---- | :---- | :---- |
| Fluorescence | prefix + `traces` (`GCaMP8m_traces`) | `(n_time, n_ROI)` |
| Spike times | `spikeTimes` | one 1-D time array per unit; no timestamps file |
| Spike waveforms | `spikeWaves` | `(n_waveform_samples, n_units)` |
| LFP | `lfp` | `(n_time, n_channels)` plus `lfp_timestamps` |
| Continuous behavior | prefix + `behTSeries` (`pupil_behTSeries`) | `(n_time, n_features)` plus timestamps |
| Event times | prefix + `behEvents` (`lick_behEvents`) | one 1-D time array per event type; no timestamps file |
| Trials | `trialInfo` | one CSV; not prefixed |

One indicator or channel product is one `traces` stream (`GCaMP8m_traces` and `tdTomato_traces` are separate files and separate sessionInfo flags). `trialInfo` is a single boolean column and a single file. Passive versus operant is which optional trial columns you fill, not a second datatype.

Behavior has three homes: `trialInfo.csv` for trial-wise values, `behEvents` for event times that are not tied to a trial table, and `behTSeries` for continuous series such as pupil or wheel.

## Where to go next

- Column and schema names: [field catalog](surlab_field_catalog.md)
- NWB placement, keywords, and reverse reads: [conversion notes](nwb_conversion_notes.md)
- Machine-readable list: `sur_nwb_conversion_table.csv` at the repo root
