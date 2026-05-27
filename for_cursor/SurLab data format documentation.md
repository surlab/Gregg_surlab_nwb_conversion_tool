# Sur Lab standardized data format

The SurLab data format provides a standardized framework for storing and analyzing preprocessed neurophysiology data. It is designed to maximize accessibility and ease of use, relying on a flat and easily parsable organization.

## **Naming conventions (summary)**

- **Case and style**
  - **Tabular field names** (CSV column headers; keys in `.json` schema that describe the same semantics as those tables): **`snake_case`**. Use **full words** where applicable (**session**, **stimulus**, **behavioral**, **sample_frequency**, **grid_location**, **clustering_algorithm**, **primary_channel**, **data_unit_measurement**, etc.). Identifier columns end with a **capital `ID`**: **`_ID`** after an underscore (e.g. **`animal_ID`**, **`session_ID`**, **`roi_ID`**), not glued forms like `animalID` or lowercase `animal_id`.
  - **Standard abbreviations** in names or labels use their usual **capitalization** (e.g. **LFP**, **ROI**, **PMT**, **FOV**, **2P** for two-photon, **SNR**, **TTL**). When an abbreviation appears inside a **snake_case** name, keep the abbreviation’s letters capital (e.g. `LFP` as a modality token in documentation or column values).
  - **Datatype IDs** and **filename stems** (e.g. **`spikeTimes`**, **`sessionInfo_<datasetID>.csv`**, **`trialInfo.csv`**) may use **camelCase**; this is intentional and separate from tabular field naming.
  - **Schema axis keys** keep **`X`** and **`Y`** capital; use **`X_dim`**, **`Y_dim`**, **`X_size`**, **`Y_size`**, **`X_idx`**, **`Y_idx`** (underscore after the axis letter).
- **Micrometers** in machine-readable names use ASCII **`um`** (not the µ symbol), e.g. `depth__um`.
- **`sessionInfo.csv`**: Prefer **session-level** metadata here rather than relying only on `.json` schema files (schema may remain for interchange). For columns that replace former schema fields, **do not** put unit suffixes in the **header**; encode the physical quantity in **cell values** using the **`base__unit`** text pattern where needed (e.g. `amplitude__V`). **Exceptions**: **`session_date`** is a plain calendar column (no dunder; values **`YYYY-MM-DD`**); **`age__days`** is the column name for age in days (numeric). Optional **calibration** columns (e.g. laser/PMT/Pockels) are **recommended** when hardware readouts are arbitrary until the user supplies a conversion.
- **`trialInfo.csv`**: Use **dunder + unit** in **column headers** for physical quantities (e.g. `tone_frequency__Hz`); **numeric** cell values only.
- **Dimension sizes** (`X_size`, `Y_size`, etc.): do **not** add misleading suffixes such as `__count` or `__samples`; describe meaning in prose.
- **Sampling rate** (schema or duplicated in session info): **`sample_frequency__Hz`** (float, Hz).

## **Conversion table (`conversion_table.csv`)**

Machine-readable mapping from SurLab files and fields to NWB targets lives in **`conversion_table.csv`** at the **repository root** (authoritative). A copy may sit beside this document under **`for_cursor/`** for handoff bundles; keep copies in sync with the root file.

Downstream tooling should treat the conversion table as the spec; this document is the human-readable companion.

**Filename and condition placeholders** (same spelling as in the table):

| Token | Meaning |
| :---- | :---- |
| `<datasetID>` | Dataset folder name |
| `<animal_ID>` | From `sessionInfo` |
| `<session_ID>` | From `sessionInfo` |
| `<datatypeID>` | **Full stream datatype ID** for one recording (optional prefix + base ID). Substitute separately for each stream present in the session (e.g. `GCaMP7f_traces`, `pupil_behTSeries`). Used in `surlab_filename`, `requirement_condition` (`if_datatype_present:<datatypeID>`), and per-stream `sessionInfo` column headers. |

**Session identity** comes from **`sessionInfo.csv`** (`animal_ID`, `session_ID`) and the session folder path **`{animal_ID}_{session_ID}/`**. The pair **`(animal_ID, session_ID)`** must be **unique within a dataset**; **`session_ID` alone** need not be globally unique.

### **Common `<datatypeID>` prefix examples (informative)**

Prefixes are **lab- or dataset-specific labels** placed **before the base datatype ID**, joined by one underscore:

**`<prefix>_<baseID>`** → full **`<datatypeID>`** (e.g. `GCaMP7f` + `_` + `traces` → **`GCaMP7f_traces`**).

They are **not standardized globally** — pick names that are clear for your archive. The table lists **common examples**; use others when needed and document new ones in the dataset README.

| Base ID | Example full `<datatypeID>` | Typical content |
| :---- | :---- | :---- |
| **`traces`** | `GCaMP7f_traces`, `GCaMP6s_traces`, `GCaMP8m_traces`, `jGCaMP8_traces` | Green calcium imaging (Suite2p / 2P) |
| **`traces`** | `tdTomato_traces`, `mCherry_traces`, `mNeptune_traces` | Red / structural / tricolor indicator lines (separate stream per line) |
| **`traces`** | `F_traces`, `F_chan2_traces` | Dual-plane or raw channel exports when kept as separate streams |
| **`behTSeries`** | `pupil_behTSeries`, `deeplabcutPupil_behTSeries`, `eye_behTSeries` | Pupil / eye position (often DeepLabCut) |
| **`behTSeries`** | `wheel_behTSeries`, `runningWheel_behTSeries` | Running wheel position or velocity |
| **`behTSeries`** | `movement_behTSeries`, `locomotion_behTSeries` | Other continuous behavioral kinematics |
| **`behEvents`** | `lick_behEvents`, `lever_behEvents` | Event times (licks, lever presses, …) |
| **`spikeTimes`**, **`lfp`** | `spikeTimes`, `lfp` (no prefix) | Fixed base IDs; use as-is in **`sessionInfo`** |
| **`trialInfo`** | `trialInfo` (no prefix) | Single trial table per session; see below |

**`trialInfo` is not prefixed.** There is one boolean column **`trialInfo`** and one file **`trialInfo.csv`** per session. “Passive” vs “behavioral” refers to **which optional columns** you include, not a separate datatype ID:

| Experiment style | Typical optional `trialInfo` columns (all optional except start/stop) |
| :---- | :---- |
| **Passive viewing** (e.g. grating, movie) | `stimulus_onset__s`, `stimulus_offset__s`, `grating_orientation__degrees`, `grating_spatial_frequency__cycles_per_degree`, `grating_drift_speed__m_per_s`, `grating_drift_direction__degrees` |
| **Operant / choice behavior** | Above as needed, plus `correct`, `output`, `reaction_time__s`, `reward`, `punish`, `num_licks` |
| **Auditory task** | `tone_frequency__Hz`, `tone_intensity__dB`, plus operant columns as needed |

**Stages** in the table: **1** session metadata; **2** spike times; **3** optical **`traces`** (one block per `<datatypeID>` stream); **4** **`behTSeries`** (one block per stream); **5** **`trialInfo`**; later stages (e.g. LFP) numbered with gaps as added.

NWB target columns in the table may be marked **SPECULATIVE** until validated against real data and the official NWB validator.

## **Data organization**

All data for each project (a **dataset**) is saved in a single folder named with a short **datasetID** (e.g. `Astro_seqBias` for astrocytes calcium recordings during a sequential go/no-go task). The format handles several **dataTypes**, including optical physiology recordings, electrophysiology spike trains, local field potentials, behavioral marker positions, single-trial behavioral events, etc. An **`experimentDesc.pdf`** file includes slides with a short description of the experiment (task design, recorded data types, numbers, etc.). A **`sessionInfo_<datasetID>.csv`** file within the dataset folder contains information about each experimental session (including session name, date, subject identity, etc.).

All data for each experimental session is saved in a separate folder named:

**`<animal_ID>_<session_ID>/`**

Use a **single underscore** between the two identifiers. **`animal_ID`** and **`session_ID`** are independent text fields from **`sessionInfo.csv`** — they are concatenated literally, even if **`session_ID`** contains dots or substrings that resemble **`animal_ID`** (e.g. `animal_ID = mouse01`, `session_ID = exp101.a1.20260204.gratings` → folder `mouse01_exp101.a1.20260204.gratings`). Do not parse or strip dots from **`session_ID`**.

Within each session folder, there are three different types of files:

- **data** are stored in **`.mat`** (Matlab) or **`.npz`** (NumPy) files. Either extension is valid; **`mat_2_py` / `py_2_mat`** convert between them. **Python-native export should prefer `.npz`**. Each file contains time series or spike times for the session.
- Session-level metadata are stored in `.json` **schema** files and should be **duplicated** in **`sessionInfo.csv`** where possible. Timestamps of each sampled time point relative to **`zero_time`** are stored in **`<datatypeID>_timestamps`**.mat / `.npz` (native frame times; see clarifications below).
- **metadata** are stored in tabular **`.csv`** files: **`trialInfo.csv`** (trial-wise events) and **`<datatypeID>_metadata.csv`** (one row per unit, ROI, electrode, feature, etc.) inside the session folder.

Therefore, each **dataType** typically has four associated files within each experimental session folder: **`<datatypeID>_data`**.mat / `.npz`, **`<datatypeID>_schema`**.json, **`<datatypeID>_metadata`**.csv, and **`<datatypeID>_timestamps`**.mat / `.npz` (except where noted, e.g. spike times). **`<datatypeID>`** is the **full stream ID** (often camelCase with an optional informative prefix, e.g. `GCaMP7f_traces`, `pupil_behTSeries`, `spikeTimes`, `lfp`).

### **Filenames: minimal (canonical) vs verbose (optional alias)**

Session scope is defined by the **parent folder** `{animal_ID}_{session_ID}/` under `{datasetID}/`. **Inside that folder**, filenames should be **minimal** — they do **not** repeat `datasetID`, `animal_ID`, or `session_ID`.

| Location | Canonical (minimal) | Verbose alias (optional) |
| :---- | :---- | :---- |
| **Dataset root** | `sessionInfo_<datasetID>.csv` | extra tokens allowed if name still starts with `sessionInfo_` |
| **Session folder** | `sessionInfo_single_session.csv` | — |
| **Per-stream data** | `<datatypeID>_data.{mat\|npz}` | `<datatypeID>_data_<datasetID>_<animal_ID>_<session_ID>.{mat\|npz}` |
| **Schema** | `<datatypeID>_schema.json` | `<datatypeID>_schema_<datasetID>_<animal_ID>_<session_ID>.json` |
| **Metadata** | `<datatypeID>_metadata.csv` | `<datatypeID>_metadata_<datasetID>_<animal_ID>_<session_ID>.csv` |
| **Timestamps** | `<datatypeID>_timestamps.{mat\|npz}` | `<datatypeID>_timestamps_<datasetID>_<animal_ID>_<session_ID>.{mat\|npz}` |
| **Trials** | `trialInfo.csv` | `trialInfo_<datasetID>_<animal_ID>_<session_ID>.csv` |

**Parsing rules**

- **Writers** (exporters) should emit **minimal** names for new SurLab packages.
- **Readers** must accept **either** minimal or verbose names when resolving files **inside** the correct session directory (match on **`<datatypeID>` + role + extension**; ignore optional middle tokens in verbose names).
- **Verbose** names are for legacy exports, loose file copies, or human search — not required for a well-formed session tree.
- Fixed-ID streams without a prefix use the base ID in the basename (e.g. `spikeTimes_data.npz`, `lfp_timestamps.npz`).

See **`conversion_table.csv`** for authoritative minimal patterns per row.

![][image1]

*Schematics of dataset organization*

![][image2]

*Example dataset folder files organization*

![][image3]

*Example experimental session folder files organization*

**Important**: All data is expressed in **seconds** relative to the session clock defined by **`zero_time`** in **`sessionInfo.csv`** (value = full **`<datatypeID>`** of the reference stream). **Default policy:** **t = 0** at the **start of acquisition** for that stream; pre-zero samples may be **negative**. Alternative alignment (e.g. first stimulus) is allowed only if documented in the **dataset README** and applied consistently to **timestamps** and **trialInfo**. The **`zero_time`** column names which stream defines the clock, not which policy was used — state the policy in the README.

## **Clarifications (conversion / ingest)**

| Topic | Rule |
| :---- | :---- |
| **A. Array layout** | **Canonical SurLab layout:** **axis 0 = time**, **axis 1 = ROIs / features / units** (Matlab: `[time × …]`; Python: `(n_time, n_unit)`). Tools that emit other layouts (e.g. Suite2p **`(n_ROI, n_time)`**) **must transpose on ingest** before writing SurLab files. |
| **B. Schema X / Y** | **`X_*` describes axis 0**, **`Y_*` describes axis 1**. For **`traces`** / **`behTSeries`**: **`X_dim = time`**, **`Y_dim = ROI`** or **`features`**; **`X_size` = number of time samples**; **`Y_size` = number of ROIs/features** (must match metadata row count). |
| **C. Resampling** | **Not required** by the format. Store **native frame times** in **`_timestamps`** files. Optional **`sample_frequency__Hz`** is descriptive (e.g. median rate), not a mandate to resample (pipelines that upsample to 20 Hz should not replace timestamps unless documented). |
| **D. `zero_time` (Tricolor / grating)** | **Canonical:** **`zero_time`** = primary calcium **`<datatypeID>`** (e.g. `GCaMP7f_traces`) with **t = 0 at imaging acquisition start**; keep native timestamps (negative pre-stim times allowed). Do **not** silently re-zero to first stimulus unless the README states that policy. |
| **E. Session folders** | **`{animal_ID}_{session_ID}`** with literal join; **`session_ID`** may contain dots. |
| **F. Multiple trace streams** | **One stream per indicator / channel product**, not one combined array: e.g. `GCaMP7f_traces`, `tdTomato_traces`, `mCherry_traces` as separate **`<datatypeID>`** values and separate **sessionInfo** flags. Dual-plane raw channels (**F**, **F_chan2**) → separate streams when processed separately; tricolor **classification** (mCherry / mNeptune / tdTomato) → separate streams per indicator, with class labels on **ROIs** in **metadata**, not separate streams per class unless each is a distinct recording. |
| **G. Required `sessionInfo`** | **`institution`**, **`lab`**, **`experimenter`**, **`species`**, **`sex`**, **`age__days`**, **`strain`** are **required in the exported `sessionInfo` CSV** even if absent from raw acquisition logs. Ingest may merge **dataset-level config** or a **sidecar** (e.g. `dataset_config.yaml`) before writing **`sessionInfo`**. |
| **G2. `trialInfo` optional columns** | Aside from **`start_time__s`** and **`stop_time__s`**, all standardized trial columns (stimuli, behavior, **`correct`**, etc.) are **optional** with no warn-if-missing. Include only what the experiment uses. |
| **H. Conversion table path** | Authoritative: **repo root** `conversion_table.csv`; optional copy in **`for_cursor/`** for handoff. |
| **I. `.mat` vs `.npz`** | Both valid; **prefer `.npz`** for Python-exported sessions. |
| **J. Empty behavioral streams** | If a stream has no data (e.g. empty wheel array), set **sessionInfo flag = 0**, **omit** data/schema/metadata/timestamp files, and document in the README. Do not write placeholder **(0, 0)** arrays with flag **1**. |
| **K. Session filenames** | **Canonical:** minimal basenames inside `{animal_ID}_{session_ID}/` (no repeated IDs). **Optional verbose alias:** embed `<datasetID>_<animal_ID>_<session_ID>` after the role token; parsers accept both. |

## **Experiment description**

This PDF file serves as a quick introduction to the experiment and the dataset. It includes summary information about the main dataset characteristics, its size, the experimental design and descriptions of dataset-specific metadata labels. This information should usually span 3–4 slides. The first slide should include 3–4 lines of dataset overview, a “unique characteristics” and a “caveats” section. The second slide should describe the experiment design. The third slide should summarize recordings (data types and Ns, e.g. number of subjects and ROIs for optical physiology). The fourth slide should provide a glossary of dataset-specific metadata labels.

## **Session info files**

These metadata files list each session as a row in a **`.csv`** file.

**File name:** `sessionInfo_<datasetID>.csv` (optional extra tokens allowed before `.csv` if the name still begins with `sessionInfo_`).

Rows correspond to sessions; columns are session properties. Names and formats align with DANDI/NWB-oriented usage. **Required** properties include:

| Column | Description |
| :---- | :---- |
| institution | Institution name, e.g. `MIT` |
| lab | Laboratory name, e.g. `SurLab` |
| experimenter | Full name of the experimenter who collected the data |
| animal_ID | Animal identifier |
| session_ID | Session identifier |
| session_date | Start date of the session (**`YYYY-MM-DD`**). No dunder in the column name. |
| species | Latin binomial, e.g. `Mus musculus` |
| sex | `M`, `F`, `O` (other), or `U` (unknown) |
| age__days | Age in **days** (numeric). |
| strain | Subspecies, breed, or common genetic modification, e.g. `C57BL/6`, or `Wild Type` if not applicable |
| zero_time | **Full `<datatypeID>`** of the reference stream (e.g. `GCaMP7f_traces`). **Default:** **t = 0** at **acquisition start** of that stream. Document any other policy (e.g. first stimulus) in the dataset README. |

**Optional** standardized properties include:

- Boolean columns (0/1) for each **individual stream** recorded in that session. Use the **full datatype ID as the column header** — not a single aggregate flag per base type. Examples: `GCaMP7f_traces`, `pupil_behTSeries`, `wheel_behTSeries` (not one shared `traces` or `behTSeries` column). Fixed-ID modalities without a lab prefix use the base ID only (`spikeTimes`, `lfp`, `trialInfo`, …).
- **`trialInfo`**: one boolean column; at most **one** trial table per session.
- `area` — recording area name(s); comma-separated if multiple areas were recorded simultaneously.
- `condition` — experimental condition labels (unique identifiers).
- `related_publication` — reference including DOI for related publication / preprocessing details.
- Hardware readouts such as **laser power**, **PMT**, or **Pockels** controls are often **arbitrary instrument units**. Prefer **numeric** columns for the readout and add a **separate optional calibration / conversion column** (or documented scale factor) when converting to physical units; supplying calibration is **recommended**.

To keep each session folder self-contained, include a single-session copy of the file as **`sessionInfo_single_session.csv`** (same schema; one row).

**Provenance:** Required columns above must appear in the written **`sessionInfo`** file. Raw data folders may not contain them; converters should merge **dataset-level defaults** (config file or sidecar) at ingest, then emit **`sessionInfo_<datasetID>.csv`** and **`sessionInfo_single_session.csv`**.

**Multiple optical streams:** Use **separate `<datatypeID>`** values and **separate sessionInfo 0/1 columns** per indicator or channel product (see clarifications table). Do not combine GCaMP + red indicator + tricolor lines into one **`traces`** array unless they share one processing pipeline and are distinguished only as ROIs (prefer separate streams).

Session-level fields that were historically only in **schema JSON** (e.g. acquisition path, filter type) should appear in **`sessionInfo.csv`** when they apply to the whole session. Where a field would have used a unit in a **schema key**, prefer a **plain column name** in **`sessionInfo.csv`** and encode the quantity in **cell values** using the **`base__unit`** pattern (e.g. `amplitude__V`) when the cell holds a **unit tag**; use **numeric** columns with documented SI units in prose when the column is purely numeric.

![][image4]

## *Example sessionInfo csv file*

## **Neural and continuous-time behavioral data**

These files hold continuous-time physiology (fluorescence, LFP, …) or behavioral streams (pupil, marker positions, …). Each **dataType** has **data**, **schema** (optional if fully mirrored in `sessionInfo`), **metadata**, and **timestamps** (except where noted).

**data** and **schema** share one **`.mat`** or **`.npz`** file. **Canonical file name:** `<datatypeID>_data.{mat|npz}` (verbose alias allowed; see above).

**metadata** is tabular: rows are recorded **units** or **ROIs** (or electrodes, events, features, …); columns use standardized **snake_case** names. **Canonical:** `<datatypeID>_metadata.csv`.

**timestamps** (when required): **Canonical:** `<datatypeID>_timestamps.{mat|npz}`.

**Currently covered data types:** Optical physiology (fluorescence traces); local field potentials; spike times; spike waveforms; behavioral events; behavioral time series.

**Standards for different data types**

| Data type | dataTypeID + (Mat / Python shape) | schema name | Index / unit label |
| :---- | :---- | :---- | :---- |
| **Optical physiology** (raw fluorescence traces) | Base ID **`traces`**; optional prefix → **`<datatypeID>`** (e.g. `GCaMP7f_traces`). **Axis 0 = time, axis 1 = ROIs.** Mat: `[time × ROIs]`; Python: `(n_time, n_ROI)`. Transpose Suite2p-style `(n_ROI, n_time)` on ingest. | `<datatypeID>_schema` | ROI |
| **Spike times** | `spikeTimes`. Matlab: `{1 × n_units}` cell of variable-length `[1 × n_spikes]` arrays. Python: `(1, n_units)` object ndarray of `(n_spikes,)` float arrays. | spikeTimesSchema — *no timestamps file* | unit |
| **Spike waveforms** | `spikeWaves`. Mat: `[waveform sample index × units]` doubles (first axis: **sampling time** along the waveform snippet, distinct from experiment clock time). Python: `(waveform_samples, units)` ndarray. Provide **`sample_frequency__Hz`** in schema or session info. | spikeWavesSchema | unit |
| **Local field potentials** | `lfp`. Mat: `[time × units]` doubles. Python: `(time, units)` ndarray. **First dimension is time** (aligned with `timestamps`). | lfpSchema | electrode |
| **Behavioral events** | `behEvents` (optional prefix, e.g. `lick_behEvents`). Mat: `{1 × n_events}` cell arrays. Python: `(1, n_events)` object ndarray. | behEventsSchema — *no timestamps file* | events |
| **Behavioral time series** | Base ID **`behTSeries`**; optional prefix → full **`<datatypeID>`** (e.g. `pupil_behTSeries`, `wheel_behTSeries`). Mat: `[time × features]`. Python: `(time, features)`. | `<datatypeID>_schema` | features |
| *Deprecated (use behEvents / behTSeries)* | lever, licking, pupil, movement | — | — |

**Table 1:** Standard variable names and array layouts. Use **units** or **ROIs**, not “neurons”, when describing the **unit** dimension.

**Schema fields** (`.json`): describe array layout for the associated **data** variable. **Shared keys** (when schema is used) — **snake_case** for tabular semantics:

| Key | Description |
| :---- | :---- |
| data_unit_measurement | String; unit tag for stored values. Prefer **`base__unit`** form (e.g. `amplitude__V`). Duplicated in **`sessionInfo.csv`** where applicable. |
| X_dim / Y_dim | Labels for **axis 0** (`X_*`) and **axis 1** (`Y_*`). For continuous streams: **`X_dim = time`**, **`Y_dim = ROI`** or **`features`**. |
| X_size / Y_size | Sizes of axis 0 and axis 1 (no `__count` suffix). **`X_size` = n_time**; **`Y_size` = n_ROI / n_features** (match metadata rows). |
| X_idx / Y_idx | Index values along each axis. **Time** coordinates are **seconds** relative to **`zero_time`**. Omitted for **spikeTimes** (times live in spike arrays). |
| sample_frequency__Hz | Sampling frequency in Hz (float). |

**Data-type-specific** schema / metadata (and typical **`dataType_metadata.csv`** columns) — use **`um`** in names for micrometers:

| Data type | Specific schema / session fields | metadata (per unit / ROI / channel) |
| :---- | :---- | :---- |
| **Optical physiology** | Laser name, objectives, `pixel_size` (µm in value; optional column `pixel_size_calibration`), FOV sizes in pixels, FOV depth (**`um`**), indicator, **`wavelength__nm`**, PMT / laser power columns with optional **calibration** columns as above, `detection_software` | `roi_ID`, `roi_x_coordinate`, `roi_y_coordinate`, `area`, **`depth__um`**, `roi_center_x`, `roi_center_y` |
| **Spike times** | `probe`, `acquisition_software`, `sorting_software`, **`filter_type`**, **`filter_cutoff_low__Hz`**, **`filter_cutoff_high__Hz`**, `quality_metric` | `unit_ID`, **`depth__um`**, `area`, `spike_sorting_ID`, `quality`, `grid_location` (row, col) |
| **Spike waveforms** | `probe`, `clustering_algorithm` | `unit_ID`, `primary_channel` (see LFP `channel_ID`) |
| **Local field potentials** | `probe`, **`filter_type`**, **`filter_cutoff_low__Hz`**, **`filter_cutoff_high__Hz`** | `channel_ID`, `channel_label`, `area`, `grid_location` |
| **Behavioral time series** | — | `feature_ID`, `feature_label` |
| **Behavioral events** | — | `event_ID`, `event_label` |

**Table 2:** Schema, session, and per-unit metadata (representative fields).

## **Trial information files**

**One table per session.** Set **`trialInfo = 1`** in **`sessionInfo.csv`** when present. **Canonical file name:** `trialInfo.csv` inside the session folder (verbose alias allowed).

Tabular **`.csv`**: one row per trial.

**Required** columns (only these two; headers use **dunder + unit** where applicable):

| Column | Description |
| :---- | :---- |
| start_time__s | Trial start (seconds relative to **`zero_time`**) |
| stop_time__s | Trial end (seconds relative to **`zero_time`**) |

All other standardized columns below are **optional** — include only those that apply to the experiment. Validators should **not** warn when optional columns are absent.

**Stimuli** (optional)

| Column | Description |
| :---- | :---- |
| stimulus_onset__s | Stimulus onset (s) |
| stimulus_offset__s | Stimulus offset (s) |
| tone_frequency__Hz | Auditory tone frequency |
| tone_intensity__dB | Auditory level (dB) |
| grating_orientation__degrees | Grating orientation |
| grating_spatial_frequency__cycles_per_degree | Visual grating spatial frequency (cycles per degree); if your pipeline uses a different convention, document it in the dataset README |
| grating_drift_speed__m_per_s | Drift speed (m/s) |
| grating_drift_direction__degrees | Drift direction |

**Behavioral outputs** (optional)

| Column | Description |
| :---- | :---- |
| reaction_time__s | Reaction time (s) from `stimulus_onset__s` |
| output | Categorical labels (`press`, `no_press`, …) |
| num_licks | Count of licks in the trial (integer) |

**Reinforcement** (optional)

| Column | Description |
| :---- | :---- |
| reward | Boolean: reward delivered |
| punish | Boolean: punishment delivered |

**Outcome** (optional)

| Column | Description |
| :---- | :---- |
| correct | **Binary** `0` or `1` when present; omit for passive viewing with no operant outcome. Non-binary legacy encodings should be converted with a validation warning. |

![][image5]

*Example trialInfo file*

If there are multiple events of the same type, append an integer to the label (e.g. `stimulus_onset__s_1`, `stimulus_onset__s_2`) — keep the same **`__s`** / unit pattern before the suffix.

## **FAQ**

**Where should I store behavioral data?**

Three structures: **`trialInfo.csv`** (trial-wise), **`behEvents`** (event times without strict trials), **`behTSeries`** (continuous streams). **`behEvents`** follows spike-time–like storage; **`behTSeries`** follows traces-like storage (**time × features**, time on the first axis).

## **Functions**

- **trials_parse**: data, schema, metadata, and `trialInfo` → trial-aligned arrays (**time × units × trials**), aligned to a chosen `trialInfo` field.
- **validate**: validate a file given its type (data, schema, `trialInfo`, …).
- **surlab_2_nwb**: build per-session NWB files compatible with DANDI.

Useful link for NWB metadata keywords (e.g. NWB 2.9): https://nwb-schema.readthedocs.io/en/latest/format.html

**mat_2_py** / **py_2_mat**: convert Matlab ↔ Python file containers.

Converters from common lab tools (e.g. Suite2P) into SurLab layout may be provided separately.
