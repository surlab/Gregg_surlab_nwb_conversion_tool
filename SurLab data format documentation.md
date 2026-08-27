# Sur Lab standardized data format

The SurLab data format provides a standardized framework for storing and analyzing preprocessed neurophysiology data. It is designed to maximize accessibility and ease of use, relying on a flat and easily parsable organization.

## **Naming conventions (summary)**

- **Case and style**
  - **Tabular field names** (CSV column headers; keys in `.json` schema that describe the same semantics as those tables): **`snake_case`**. Use **full words** where applicable (**session**, **stimulus**, **behavioral**, **sample_frequency**, **grid_location**, **clustering_algorithm**, **primary_channel**, **data_unit_measurement**, etc.). Identifier columns end with a **capital `ID`**: **`_ID`** after an underscore (e.g. **`animal_ID`**, **`session_ID`**, **`roi_ID`**), not glued forms like `animalID` or lowercase `animal_id`.
  - **Standard abbreviations** in names or labels use their usual **capitalization** (e.g. **LFP**, **ROI**, **PMT**, **FOV**, **2P** for two-photon, **SNR**, **TTL**). When an abbreviation appears inside a **snake_case** name, keep the abbreviation’s letters capital (e.g. `LFP` as a modality token in documentation or column values).
  - **Datatype IDs** and **filename stems** (e.g. **`spikeTimes`**, **`sessionInfo_<datasetID>.csv`**, **`trialInfo.csv`**) may use **camelCase**; this is intentional and separate from tabular field naming.
  - **Schema axis keys** keep **`X`** and **`Y`** capital; use **`X_dim`**, **`Y_dim`**, **`X_size`**, **`Y_size`**, **`X_idx`**, **`Y_idx`** (underscore after the axis letter).
- **Micrometers** in machine-readable names use ASCII **`um`** (not the µ symbol), e.g. `depth__um`.
- **`sessionInfo.csv`**: Prefer **session-level and per-stream scalar metadata** here rather than relying on `.json` schema files (**schema is fully optional**; see Session info files). Scalar stream fields use **`{datatypeID}_{field}`** column names (e.g. **`spikeTimes_probe`**, **`GCaMP7f_traces_indicator`**).
  - **Physical / numeric quantities** put the unit in the **header** with a **dunder** (`__`): e.g. **`age__days`**, **`filter_cutoff_low__Hz`**, **`fov_width__pixels`**, **`fov_height__pixels`**, **`fov_depth__um`**, **`wavelength__nm`**, **`pixel_size__um`**. Cell values are numeric (or plain text only when the field is non-numeric).
  - **Unknown / arbitrary units:** use **`__au`** (arbitrary units) in the header instead of inventing a physical unit — e.g. **`pixel_size__au`** when pixel size is not calibrated to micrometers. Prefer **`__um`** (etc.) once calibrated.
  - **Non-quantity labels** (IDs, software names, booleans, free text) have **no** unit suffix: e.g. **`probe`**, **`indicator`**, **`detection_software`**.
  - **Unit-tag strings** (what unit the *data array* is in) use a separate column such as **`data_unit_measurement`**, with cell values in **`base__unit`** form (e.g. `amplitude__V`, `deltaF_over_F__au`).
  - **Exception:** **`session_date`** is a plain calendar column (no dunder; values **`YYYY-MM-DD`**).
- **`trialInfo.csv`**: Use **dunder + unit** in **column headers** for physical quantities (e.g. `tone_frequency__Hz`); **numeric** cell values only.
- **Dimension sizes** (`X_size`, `Y_size`, etc.): do **not** add misleading suffixes such as `__count` or `__samples`; describe meaning in prose.
- **Sampling rate** (schema or duplicated in session info): **`sample_frequency__Hz`** (float, Hz).

## **Conversion table (`sur_nwb_conversion_table.csv`)**

Machine-readable mapping from SurLab files and fields to NWB targets lives in **`sur_nwb_conversion_table.csv`** at the **repository root** (authoritative). An optional handoff copy may live under **`for_cursor/`**; keep it in sync with the root file.

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

**Stage numbers are for development tracking only.** The forward converter (`src/sur_to_nwb.py`) builds one integrated NWB file per session; `stage` is not an output artifact and is not a runtime module boundary. Use CLI `--stage` only to limit which table rows run while implementing incrementally.

NWB target columns in the table may be marked **SPECULATIVE** until validated against real data and the official NWB validator.

### **Forward conversion (Task 2)**

Implementation reference: `for_cursor/task2_implementation_decisions_and_answers.txt` (section E).

| Topic | Rule |
| :---- | :--- |
| **Placement spec** | `sur_nwb_conversion_table.csv` columns `nwb_location` + `nwb_fieldname` are read literally by code. |
| **What is present** | Inferred **from session-dir filenames first** (e.g. `spikeTimes_data*.mat` ⇒ `spikeTimes`). sessionInfo flags are secondary. |
| **Filenames** | Minimal canonical name first; then verbose alias via `<stem>*.<ext>` glob (`src/surlab_paths.py`). |
| **zero_time** | SurLab column = full **datatype ID of the reference stream** (first timestamp = 0). Stored in NWB as `notes`: `SurLab zero_time=<datatypeID>`. Not a global NWB clock field. Mismatch vs ~0 ⇒ warning only. |
| **Legacy sessionInfo** | `animalID` / `sessID` / etc. normalized to canonical names **in memory on read**; validator does not treat legacy headers as valid. On-disk CSVs are not rewritten by forward conversion. |
| **Extras** | Columns not listed in the table ⇒ `experiment_description` key=value text (interim; see table `dataset_specific` row). |
| **Identifier** | `NWBFile.identifier = f"{animal_ID}__{session_ID}"` (derived; not a SurLab CSV column). |

**NWB mapping columns.** Until the deferred **`nwb_path`** column is introduced, the converter reads **`nwb_location`** + **`nwb_fieldname`**. **Each row names exactly one destination** — no `A_or_B` placement tokens. Rows that map **`sessionInfo`** modality flags to **`NWBFile.keywords`** also carry **`nwb_keyword`** (see below).

#### Deterministic placement rule

1. Look up **`nwb_location`** → find or create the NWB container (e.g. `NWBFile`, `NWBFile/general/subject`, `NWBFile/units`).
2. Look up **`nwb_fieldname`** → write the SurLab value to **that one field** on that container.
3. If **`nwb_fieldname`** is a reserved token (below), apply the token rule — still one destination, not a choice.
4. **`mapping_rationale`** and **`notes`** are prose for humans; **`nwb_location`** + **`nwb_fieldname`** are what the converter must follow.

**`nwb_location`** — container path. Slashes are hierarchy, not alternatives. Examples: `NWBFile`, `NWBFile/general/subject` (the **`Subject`** object), `NWBFile/units`, `NWBFile/devices`, `NWBFile/processing`, `NWBFile/ophys/RoiResponseSeries`, `NWBFile/acquisition`, `NWBFile/intervals/trials`.

**`nwb_fieldname`** — single field on that container. Reserved tokens:

| Token | Meaning |
| :---- | :---- |
| **`custom_field`** | Store as a custom attribute on the container. **Always preserve** (do not drop) for round-trip. |
| **`custom_column_<name>`** | Named custom column on the table at **`nwb_location`**. |
| **`custom_columns`** | Generic **`dataset_specific`** row: preserve each extra column under its SurLab header name. |
| **`id`** | Row id column on the table. |
| **`N/A`** | No NWB target (informational / derived / file-absent rows). Do not write. |

**`nwb_keyword`** — only on rows where **`nwb_fieldname = keywords`**. Drives **`NWBFile.keywords`** forward (SurLab → NWB) and reverse (NWB → SurLab boolean columns). Leave empty on all other rows.

| `fieldname_surlab` | `nwb_keyword` | When flag = 1 |
| :---- | :---- | :---- |
| **`trialInfo`** | `trials` | append keyword `trials` |
| **`spikeTimes`** | `spike_times` | append keyword `spike_times` |
| **`spikeWaves`** | `spike_waveforms` | append keyword `spike_waveforms` |
| **`behEvents`** | `behavior_events` | append keyword `behavior_events` |
| **`lfp`** | `lfp` | append keyword `lfp` (same as column name) |
| **`(per_stream_traces)`** | `identity` | append keyword = column name when header ends `_traces` |
| **`(per_stream_behTSeries)`** | `identity` | append keyword = column name when header ends `_behTSeries` |

**Forward:** for each `sessionInfo` boolean column with flag `1`, look up its table row; if **`nwb_keyword`** is a literal token, append it to **`NWBFile.keywords`**; if **`nwb_keyword = identity`**, append the column header itself.

**Reverse:** invert fixed-modality rows via **`nwb_keyword`**; for **`identity`** rows, any keyword ending `_traces` or `_behTSeries` becomes a boolean column set to `1`.

#### Reverse-only alternate reads (`nwb_alt_fieldnames` + ecosystem CSVs)

**Purpose:** ingest **non–SurLab-native NWB** (Allen, IBL, DANDI, etc.) without forking SurLab export shape. **Forward conversion ignores all of this.**

**Two layers:**

| Layer | When loaded | What it holds |
| :---- | :---- | :---- |
| **`nwb_alt_fieldnames`** (primary table) | **Always** on reverse | Same-container renames on primary **`nwb_location`**: semicolon-separated field/column names (e.g. `brain_area;location` when primary is `custom_column_brain_area` on **`Units`**). |
| **`reverse_mapping/<ecosystem>.csv`** | **Only when user specifies** format (e.g. `--reverse-ecosystem allen`) | Structural / ecosystem-specific paths (different container, linkage notes). Join key: **`fieldname_surlab`**. See **`reverse_mapping/README.md`**. |

**Load order (reverse):**

1. Primary **`nwb_location`** + **`nwb_fieldname`** with **stream-scoped linkage** from **`mapping_rationale`** (e.g. Device linked to **`Units`**, not “first device in file”).
2. **`nwb_alt_fieldnames`** on that row (same location; try each alias in order).
3. Ecosystem file(s) named by the user — **not loaded by default**.

**Rare escape:** if an alias must use a **different** container, prefix with **`/`** + location + **`|`** + field: `/NWBFile|experiment_description` (avoid in ecosystem CSV when possible).

**Rules:**

- First **non-empty** wins within the active layers.
- **Always write** canonical SurLab (**`fieldname_surlab`**, plus schema mirror on reverse when applicable).
- If **primary and a fallback are both non-empty but differ → warn** (primary still wins). Empty vs populated is not a conflict.
- Log which layer supplied each field in the reverse report CSV.

**Linkage vs aliases:** linkage applies to the **primary** read when several NWB objects exist (e.g. which **`Device`**). **`nwb_alt_fieldnames`** are cheap column renames on the **same** container. Heavier cross-container reads live in **`reverse_mapping/*.csv`**.

**Scope:** scalar metadata first; data-array discovery (keywords, series names) stays separate (Task 4).

#### **`nwb_type` vocabulary (for validators)**

Every data/metadata row should use one of these tokens. **Do not** use bare **`array`** or **`variable`** — those are ambiguous and cannot be type-checked.

| `nwb_type` | SurLab / JSON value rule | Notes |
| :---- | :---- | :---- |
| **`str`** | Non-empty text (after trim) | Special cases: **`sex`** ∈ {M,F,O,U}; boolean-like units → 0/1 |
| **`str_or_array_of_str`** | String **or** list/array of strings | e.g. **`experimenter`** |
| **`array_of_str`** | List/array of strings (NWB keywords path) | Used with **`nwb_fieldname=keywords`** |
| **`int`** | Integer numeric cell; no unit suffix in the cell | Unit belongs in the **header** (`__Hz`, etc.) |
| **`int_or_str`** | Integer **or** non-empty string | IDs (`unit_ID`, `roi_ID`, …) |
| **`float`** / **`float64`** | Numeric float cell; no unit suffix in the cell | Same as each other for validation |
| **`float_or_str`** | Float **or** non-empty string | e.g. **`quality`**: numeric metric **or** categorical label (see **`quality_metric`**) |
| **`bool`** | 0/1 (also true/false/yes/no accepted on read) | |
| **`datetime`** | Calendar **`YYYY-MM-DD`** in SurLab | Maps to NWB datetime |
| **`array_of_float`** | JSON/Python **1-D list** of floats (or comma-separated floats if ever in CSV) | e.g. schema **`X_idx`** time coordinates (seconds) |
| **`array_of_float64`** | Same as **`array_of_float`** for validation; marks NWB float64 storage | Used on **`data_array`** / **`timestamps_array`** rows (file-level arrays; shape checked separately) |
| **`array_of_int_or_str`** | 1-D list of ints and/or strings | e.g. schema **`Y_idx`** ROI/feature indices |
| **`N/A`** | No value to type-check | Informational / derived / absent-file rows |
| **`same`** | Alias of mirror-row semantics | e.g. `sessionInfo_single_session` → same as dataset sessionInfo |

Type unions (`*_or_*`) are **acceptable value types**, not alternate NWB destinations.

#### Exceptions (only these break “obvious” mapping)

| Exception | What to do |
| :---- | :---- |
| **`requirement_level = na`** or **`nwb_fieldname = N/A`** | Rule / provenance / naming rows — not written to NWB. |
| **`(derived_file_identifier)`** | Not a SurLab column; converter **generates** `NWBFile.identifier` (e.g. `{animal_ID}__{session_ID}`). |
| **`mapping_rationale` contains SPECULATIVE** | Placement is a best guess until validated on real data; still use the listed columns until the table is updated. |
| **Deferred `nwb_path` (future)** | Two interim text targets below will move to structured **`LabMetaData`**; until then, use the table as written so round-trip works. |
| **Age conversion** | SurLab **`age__days`** (numeric) → NWB **`Subject.age`** as ISO-8601 duration (**`P{n}D`**), not a straight string copy. |
| **Session date** | SurLab **`session_date`** → NWB **`session_start_time`** (**`datetime`**); default clock time T00:00:00 if no time-of-day in source. |

#### Example mappings (including non-obvious ones)

| SurLab source | `nwb_location` | `nwb_fieldname` | Why it looks odd |
| :---- | :---- | :---- | :---- |
| Extra **`sessionInfo`** columns (`dataset_specific` rule) | `NWBFile` | **`experiment_description`** | Lab-specific session keys are appended into free text, not a dedicated extension type (interim until **`nwb_path`** / LabMetaData). |
| **`zero_time`** (optional; stream ID string, e.g. `GCaMP7f_traces`) | `NWBFile` | **`notes`** | Provenance only — records which stream was aligned to t=0. NWB has **no** global **`zero_time`** field; if the column is absent, skip it. See session clock section below. |
| **`area`** (session-level brain region) | `NWBFile/general/subject` | **`description`** | Region text lands on **`Subject.description`**, not a dedicated brain-area field at stage 1. |
| **`acquisition_software`** (spikeTimes schema) | `NWBFile/devices` | **`Device.description`** | Software name stored in device description, not **`manufacturer`**. |
| **`probe`** (spikeTimes schema) | `NWBFile/devices` | **`Device.name`** | Probe id is the device **name**. |
| Filter cutoffs / filter type (schema) | `NWBFile/processing` | **`custom_field`** | No single core NWB filter object — preserve as custom fields. |
| Schema layout keys (`X_dim`, `X_size`, …) on traces | `NWBFile/ophys/RoiResponseSeries` | **`custom_field`** | Layout metadata preserved for round-trip; not dropped because “optional”. |
| Unlisted metadata columns (`dataset_specific`) | table at **`nwb_location`** | **`custom_columns`** | Column **names** come from the CSV header at runtime. |

#### Session clock (the shared time origin) — SurLab vs NWB

**Key idea:** `zero_time` is **not a special field or value**. It is simply the **shared time origin (t = 0)** of the session. All SurLab times — every stream's **`_timestamps`**, spike times, and **`trialInfo`** **`__s`** columns — are seconds relative to this one origin.

**How the origin is defined:**

- **At least one stream has a sample at exactly `t = 0`.** That stream anchors the session origin. There is no magic; t=0 is just wherever that anchor sample falls.
- Every other stream may **begin before or after** the origin, so its first timestamp can be **negative or positive** (e.g. imaging that started before the first stimulus → negative trial onsets are valid).
- Continuous streams carry these times in **`<datatypeID>_timestamps`** files (or inside spike arrays for **`spikeTimes`**).

**Optional `zero_time` column (provenance):** **`sessionInfo.csv`** *may* include an **optional** **`zero_time`** column holding the **`<datatypeID>`** of the stream that was aligned to 0 (e.g. `GCaMP7f_traces`). This is useful **provenance** — it records the alignment choice made when the raw data were processed **into** the SurLab format (you have to pick something to align to). Once alignment is done it is **not required** for correctness: all times already share the origin, and a converter can infer the anchor as whichever stream has a first timestamp of 0. **If the column is absent, skip it.**

**NWB:** There is **no** standard top-level `zero_time` attribute. NWB expresses time through each object's **`timestamps`**, **`starting_time`**, and trial interval columns, all aligned to one session time base. For conversion you do **not** need a special origin field — just preserve each SurLab time value as-is into the corresponding NWB timestamps/start-times (do not re-zero any stream). NWB's own convention is that these are all relative to `session_start_time`.

**NWB write (interim, only if the `zero_time` column is present):** copy the stream ID string to **`NWBFile.notes`** (e.g. `SurLab zero_time stream: GCaMP7f_traces`) so the alignment choice is preserved. **Do not** invent a custom top-level NWB field named `zero_time`. Future **`nwb_path`** may move this to structured **`LabMetaData`**.

## **Data organization**

All data for each project (a **dataset**) is saved in a single folder named with a short **datasetID** (e.g. `Astro_seqBias` for astrocytes calcium recordings during a sequential go/no-go task). The format handles several **dataTypes**, including optical physiology recordings, electrophysiology spike trains, local field potentials, behavioral marker positions, single-trial behavioral events, etc. An **`experimentDesc.pdf`** file includes slides with a short description of the experiment (task design, recorded data types, numbers, etc.). A **`sessionInfo_<datasetID>.csv`** file within the dataset folder contains information about each experimental session (including session name, date, subject identity, etc.).

All data for each experimental session is saved in a separate folder named:

**`<animal_ID>_<session_ID>/`**

Use a **single underscore** between the two identifiers. **`animal_ID`** and **`session_ID`** are independent text fields from **`sessionInfo.csv`** — they are concatenated literally, even if **`session_ID`** contains dots or substrings that resemble **`animal_ID`** (e.g. `animal_ID = mouse01`, `session_ID = exp101.a1.20260204.gratings` → folder `mouse01_exp101.a1.20260204.gratings`). Do not parse or strip dots from **`session_ID`**.

Within each session folder, there are three different types of files:

- **data** are stored in **`.mat`** (Matlab) or **`.npz`** (NumPy) files. Either extension is valid; **`mat_2_py` / `py_2_mat`** convert between them. **Python-native export should prefer `.npz`**. Each file contains time series or spike times for the session.
- Session-level metadata belong in **`sessionInfo.csv`**. **Optional** **`<datatypeID>_schema.json`** files may hold **array layout** keys (`X_idx`, `Y_idx`), **unlisted** keys (`dataset_specific`), and **legacy mirrors** of scalar fields. Timestamps of each sampled time point relative to the **session origin (t = 0)** are stored in **`<datatypeID>_timestamps`**.mat / `.npz` (native frame times; see clarifications below).
- **metadata** are stored in tabular **`.csv`** files: **`trialInfo.csv`** (trial-wise events) and **`<datatypeID>_metadata.csv`** (one row per unit, ROI, electrode, feature, etc.) inside the session folder.

Therefore, each **dataType** typically has **data**, **metadata**, and **timestamps** files within each experimental session folder, plus an **optional** **`<datatypeID>_schema.json`** (except where noted, e.g. spike times). **`<datatypeID>`** is the **full stream ID** (often camelCase with an optional informative prefix, e.g. `GCaMP7f_traces`, `pupil_behTSeries`, `spikeTimes`, `lfp`).

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

See **`sur_nwb_conversion_table.csv`** for authoritative minimal patterns per row.

![][image1]

*Schematics of dataset organization*

![][image2]

*Example dataset folder files organization*

![][image3]

*Example experimental session folder files organization*

**Important (session clock):** All SurLab times (timestamps files, **`trialInfo`** **`__s`** columns, spike times) share **one origin (t = 0)**. At least one stream has a sample at exactly 0; other streams may begin before or after (**negative or positive** times). `zero_time` is **not** a special field — the optional **`sessionInfo`** **`zero_time`** column merely records which stream was aligned to 0 (provenance). NWB has no global `zero_time` field — timing is carried in each object's timestamps / start times, aligned to the same origin. See **Session clock (the shared time origin)** under NWB mapping columns above.

## **Clarifications (conversion / ingest)**

| Topic | Rule |
| :---- | :---- |
| **A. Array layout** | **Canonical SurLab layout:** **axis 0 = time**, **axis 1 = ROIs / features / units** (Matlab: `[time × …]`; Python: `(n_time, n_unit)`). Tools that emit other layouts (e.g. Suite2p **`(n_ROI, n_time)`**) **must transpose on ingest** before writing SurLab files. |
| **B. Schema X / Y** | **`X_*` describes axis 0**, **`Y_*` describes axis 1**. For **`traces`** / **`behTSeries`**: **`X_dim = time`**, **`Y_dim = ROI`** or **`features`**; **`X_size` = number of time samples**; **`Y_size` = number of ROIs/features** (must match metadata row count). |
| **C. Resampling** | **Not required** by the format. Store **native frame times** in **`_timestamps`** files. Optional **`sample_frequency__Hz`** is descriptive (e.g. median rate), not a mandate to resample (pipelines that upsample to 20 Hz should not replace timestamps unless documented). |
| **D. Session clock / `zero_time`** | Times share **one origin (t = 0)**; at least one stream has a sample at 0, and other streams/trials may be negative or positive relative to it. `zero_time` is **not** a required field: the optional **`sessionInfo`** **`zero_time`** column just records which **`<datatypeID>`** was aligned to 0 (e.g. `GCaMP7f_traces`) as provenance for how the raw data were processed into SurLab. A converter may otherwise infer the anchor as the stream whose first timestamp is 0. NWB: no global field — if the column is present, its value is copied to **`NWBFile.notes`** (interim); otherwise skip. |
| **E. Session folders** | **`{animal_ID}_{session_ID}`** with literal join; **`session_ID`** may contain dots. |
| **F. Multiple trace streams** | **One stream per indicator / channel product**, not one combined array: e.g. `GCaMP7f_traces`, `tdTomato_traces`, `mCherry_traces` as separate **`<datatypeID>`** values and separate **sessionInfo** flags. Dual-plane raw channels (**F**, **F_chan2**) → separate streams when processed separately; tricolor **classification** (mCherry / mNeptune / tdTomato) → separate streams per indicator, with class labels on **ROIs** in **metadata**, not separate streams per class unless each is a distinct recording. |
| **G. Required `sessionInfo`** | **`institution`**, **`lab`**, **`experimenter`**, **`species`**, **`sex`**, **`age__days`**, **`strain`** are **required in the exported `sessionInfo` CSV** even if absent from raw acquisition logs. Ingest may merge **dataset-level config** or a **sidecar** (e.g. `dataset_config.yaml`) before writing **`sessionInfo`**. |
| **G2. `trialInfo` optional columns** | Aside from **`start_time__s`** and **`stop_time__s`**, all standardized trial columns (stimuli, behavior, **`correct`**, etc.) are **optional** with no warn-if-missing. Include only what the experiment uses. |
| **H. Conversion table path** | Authoritative: **repo root** `sur_nwb_conversion_table.csv`; optional copy in **`for_cursor/`** for handoff. |
| **I. `.mat` vs `.npz`** | Both valid; **prefer `.npz`** for Python-exported sessions. |
| **J. Empty behavioral streams** | If a stream has no data (e.g. empty wheel array), set **sessionInfo flag = 0**, **omit** data/schema/metadata/timestamp files, and document in the README. Do not write placeholder **(0, 0)** arrays with flag **1**. |
| **K. Session filenames** | **Canonical:** minimal basenames inside `{animal_ID}_{session_ID}/` (no repeated IDs). **Optional verbose alias:** embed `<datasetID>_<animal_ID>_<session_ID>` after the role token; parsers accept both. |
| **L. Scalar stream metadata** | **Canonical:** **`sessionInfo.csv`** columns **`{datatypeID}_{field}`** (e.g. `spikeTimes_probe`, `GCaMP7f_traces_indicator`). **Optional legacy mirror:** same field name (unprefixed) in **`<datatypeID>_schema.json`**. **Read (SurLab→NWB):** check both; if both non-empty and values **disagree → fail**. If only one present, use it. **Forward conversion does not modify** source SurLab files. **Reverse (NWB→SurLab):** write to **both** sessionInfo column and schema JSON (round-trip output). **`X_size` / `Y_size`:** derive from data arrays; not sessionInfo columns. Unlisted keys stay in schema **`dataset_specific`** only. |
| **M. NWB stream linkage** | Scalar fields map to NWB via **stream-scoped linkage**, not a global scan. Examples: **`spikeTimes_probe`** ↔ **`Device`** linked to **`Units`**; **`spikeTimes_sorting_software`** ↔ sorting **`ProcessingModule`** for that stream; **`lfp_probe`** ↔ device linked to LFP; **`GCaMP7f_traces_indicator`** ↔ **`OpticalChannel` / `ImagingPlane`** linked to that stream’s **`RoiResponseSeries`**. One physical probe may populate both **`spikeTimes_probe`** and **`lfp_probe`** on reverse. Multiple ophys streams may share or split devices (scope + fiber, multiple indicators); each **`<datatypeID>`** column group is independent. |
| **N. Unit suffixes in headers** | Numeric physical fields include **`__unit`** in the **column name** (sessionInfo stream scalars and trialInfo). Examples: **`fov_width__pixels`**, **`fov_height__pixels`**, **`fov_depth__um`**, **`pixel_size__um`**, **`wavelength__nm`**, **`sample_frequency__Hz`**. Do **not** use bare `pixel_size` or `fov_width`. If the scale is unknown/arbitrary, use **`__au`** (e.g. **`pixel_size__au`**) instead of a physical unit — mutually exclusive with the calibrated name for that stream. |

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

**Optional** standardized properties include:

- **`zero_time`** — the **`<datatypeID>`** of the stream that was aligned to the session origin (t = 0), e.g. `GCaMP7f_traces`. This is **provenance only**: it records the alignment choice made when processing raw data into SurLab. It is **not** a special value and **not** required for correctness — all times already share one origin, and a converter can infer the anchor as whichever stream has a first timestamp of 0. Not a field in NWB; if present, the converter records the stream ID in **`NWBFile.notes`** (interim). See the session-clock note above.
- Boolean columns (0/1) for each **individual stream** recorded in that session. Use the **full datatype ID as the column header** — not a single aggregate flag per base type. Examples: `GCaMP7f_traces`, `pupil_behTSeries`, `wheel_behTSeries` (not one shared `traces` or `behTSeries` column). Fixed-ID modalities without a lab prefix use the base ID only (`spikeTimes`, `lfp`, `trialInfo`, …).
- **`trialInfo`**: one boolean column; at most **one** trial table per session.
- **Per-stream scalar metadata** — columns named **`{datatypeID}_{field}`** (single underscore between ID and field). Examples: **`spikeTimes_probe`**, **`spikeTimes_sorting_software`**, **`GCaMP7f_traces_indicator`**, **`pupil_behTSeries_sample_frequency__Hz`**. One column per scalar per stream; there is never a shared unprefixed `probe` column when multiple modalities exist. See tier 4 below and Table 2.
- `area` — recording area name(s); comma-separated if multiple areas were recorded simultaneously.
- `condition` — experimental condition labels (unique identifiers).
- `related_publication` — reference including DOI for related publication / preprocessing details.
- Hardware readouts such as **laser power**, **PMT**, or **Pockels** controls are often **arbitrary instrument units**. Prefer **numeric** columns for the readout and add a **separate optional calibration / conversion column** (or documented scale factor) when converting to physical units; supplying calibration is **recommended**.

### **Recommended column order**

Parsers accept any column order; converters **should** emit columns in this order when practical:

| Tier | Block | Examples |
| :---- | :---- | :---- |
| **1** | Required session metadata | `institution`, `lab`, `animal_ID`, `session_ID`, `session_date`, `species`, `sex`, `age__days`, `strain` |
| **2** | Optional session metadata | `zero_time`, `area`, `condition`, `related_publication`, … |
| **3** | Stream presence flags (0/1) | `spikeTimes`, `lfp`, `GCaMP7f_traces`, `pupil_behTSeries`, `trialInfo`, … |
| **4** | Stream scalar metadata (**grouped by stream**) | `spikeTimes_probe`, `spikeTimes_sorting_software`, … then `GCaMP7f_traces_indicator`, `GCaMP7f_traces_detection_software`, … |
| **5** | Lab-specific extras | Unlisted columns; **`dataset_specific`** spillover to NWB `experiment_description` |

Within tier 4, list all columns for one **`<datatypeID>`** together before the next stream.

### **Scalar metadata vs schema JSON**

**Canonical location** for single-value stream metadata is **`sessionInfo.csv`** (**`{datatypeID}_{field}`**). **`<datatypeID>_schema.json` is fully optional.**

| Content | sessionInfo | schema JSON |
| :---- | :---- | :---- |
| Scalar stream fields (Table 2) | **Canonical** `{datatypeID}_{field}` column | Optional **legacy mirror** (unprefixed key, e.g. `probe`) |
| Array layout (`X_idx`, `Y_idx`) | **No** | Optional |
| Axis sizes (`X_size`, `Y_size`) | **No** — derive from **data** array shape + metadata row count | Optional |
| Axis labels (`X_dim`, `Y_dim`) | **No** — infer from datatype convention | Optional |
| Unlisted / lab-specific keys | Tier 5 extras or NWB custom fields | **`dataset_specific`** blob |

**Conversion read rule:** for each scalar, check **sessionInfo column** and **schema key**. If **both non-empty and values differ → fail** (validator/converter error). If only one is populated, use it. **SurLab→NWB forward conversion does not modify** source SurLab files on disk.

**Reverse conversion:** write each scalar to **both** the sessionInfo column and the schema JSON key (round-trip / output tree). External NWB files without stream linkage may require warnings when populating sessionInfo.

To keep each session folder self-contained, include a single-session copy of the file as **`sessionInfo_single_session.csv`** (same columns; one row).

**Provenance:** Required columns above must appear in the written **`sessionInfo`** file. Raw data folders may not contain them; converters should merge **dataset-level defaults** (config file or sidecar) at ingest, then emit **`sessionInfo_<datasetID>.csv`** and **`sessionInfo_single_session.csv`**.

**Multiple optical streams:** Use **separate `<datatypeID>`** values and **separate sessionInfo 0/1 columns** per indicator or channel product (see clarifications table). Do not combine GCaMP + red indicator + tricolor lines into one **`traces`** array unless they share one processing pipeline and are distinguished only as ROIs (prefer separate streams). Each stream’s scalar metadata uses that stream’s full ID prefix (e.g. **`GCaMP7f_traces_indicator`**, **`tdTomato_traces_indicator`**). Multiple indicators may share one microscope or use separate acquisition paths (fiber + scope, etc.); NWB linkage is **per stream**, not one global ophys device.

![][image4]

## *Example sessionInfo csv file*

## **Neural and continuous-time behavioral data**

These files hold continuous-time physiology (fluorescence, LFP, …) or behavioral streams (pupil, marker positions, …). Each **dataType** has **data**, **metadata**, and **timestamps** (except where noted). **Schema JSON is optional** (layout arrays, legacy mirrors, unlisted keys).

**data** files: **`.mat`** or **`.npz`**. **Canonical file name:** `<datatypeID>_data.{mat|npz}` (verbose alias allowed; see above).

**metadata** is tabular: rows are recorded **units** or **ROIs** (or electrodes, events, features, …); columns use standardized **snake_case** names. **Canonical:** `<datatypeID>_metadata.csv`.

**timestamps** (when required): **Canonical:** `<datatypeID>_timestamps.{mat|npz}`.

**schema** (optional): **`<datatypeID>_schema.json`** — see **Scalar metadata vs schema JSON** above. Not required for validation if scalars are in sessionInfo and layout is inferable from data.

**Currently covered data types:** Optical physiology (fluorescence traces); local field potentials; spike times; spike waveforms; behavioral events; behavioral time series.

**Standards for different data types**

| Data type | dataTypeID + (Mat / Python shape) | schema name | Index / unit label |
| :---- | :---- | :---- | :---- |
| **Optical physiology** (raw fluorescence traces) | Base ID **`traces`**; optional prefix → **`<datatypeID>`** (e.g. `GCaMP7f_traces`). **Axis 0 = time, axis 1 = ROIs.** Mat: `[time × ROIs]`; Python: `(n_time, n_ROI)`. Transpose Suite2p-style `(n_ROI, n_time)` on ingest. | `<datatypeID>_schema` | ROI |
| **Spike times** | `spikeTimes`. Matlab: `{1 × n_units}` cell of variable-length `[1 × n_spikes]` arrays. Python: `(1, n_units)` object ndarray of `(n_spikes,)` float arrays. | spikeTimesSchema — *no timestamps file* | unit |
| **Spike waveforms** | `spikeWaves`. Mat: `[waveform sample index × units]` doubles (first axis: **sampling time** along the waveform snippet, distinct from experiment clock time). Python: `(waveform_samples, units)` ndarray. | spikeWavesSchema (optional) | unit |
| **Local field potentials** | `lfp`. Mat: `[time × units]` doubles. Python: `(time, units)` ndarray. **First dimension is time** (aligned with `timestamps`). | lfpSchema | electrode |
| **Behavioral events** | `behEvents` (optional prefix, e.g. `lick_behEvents`). Mat: `{1 × n_events}` cell arrays. Python: `(1, n_events)` object ndarray. | behEventsSchema — *no timestamps file* | events |
| **Behavioral time series** | Base ID **`behTSeries`**; optional prefix → full **`<datatypeID>`** (e.g. `pupil_behTSeries`, `wheel_behTSeries`). Mat: `[time × features]`. Python: `(time, features)`. | `<datatypeID>_schema` | features |
| *Deprecated (use behEvents / behTSeries)* | lever, licking, pupil, movement | — | — |

**Table 1:** Standard variable names and array layouts. Use **units** or **ROIs**, not “neurons”, when describing the **unit** dimension.

**Schema fields** (optional **`.json`**): primarily **array layout** and **legacy mirrors**. **Shared keys** (when schema is used) — **snake_case** for tabular semantics:

| Key | Description |
| :---- | :---- |
| data_unit_measurement | String; unit tag for stored values. Prefer **`base__unit`** form (e.g. `amplitude__V`). **Canonical:** **`{datatypeID}_data_unit_measurement`** in sessionInfo. |
| X_dim / Y_dim | Labels for **axis 0** (`X_*`) and **axis 1** (`Y_*`). For continuous streams: **`X_dim = time`**, **`Y_dim = ROI`** or **`features`**. Optional schema only; infer from datatype when absent. |
| X_size / Y_size | Sizes of axis 0 and axis 1. **Derive from data array shape** during processing; optional schema only — **not** sessionInfo columns. |
| X_idx / Y_idx | Index values along each axis. **Time** coordinates are **seconds** relative to the **session origin (t = 0)**. Optional schema only; continuous streams usually use **`_timestamps`** instead of `X_idx`. Omitted for **spikeTimes** (times live in spike arrays). |
| sample_frequency__Hz | Sampling frequency in Hz (float). **Canonical:** **`{datatypeID}_sample_frequency__Hz`** in sessionInfo. |

**Data-type-specific** scalar fields — **canonical sessionInfo column** = **`{datatypeID}_{field}`**; optional unprefixed mirror in schema JSON:

| Data type | sessionInfo columns (`{datatypeID}_{field}`) | metadata (per unit / ROI / channel) |
| :---- | :---- | :---- |
| **Optical physiology** | `detection_software`, `indicator`, `wavelength__nm`, **`pixel_size__um`** (or **`pixel_size__au`** if uncalibrated), `pixel_size_calibration`, `objectives`, `laser_name`, **`fov_width__pixels`**, **`fov_height__pixels`**, **`fov_depth__um`**, `data_unit_measurement`, `sample_frequency__Hz`, … | `roi_ID`, `roi_x_coordinate`, `roi_y_coordinate`, `area`, **`depth__um`**, `roi_center_x`, `roi_center_y` |
| **Spike times** | `probe` (**required when `spikeTimes=1`**), `acquisition_software`, `sorting_software`, `filter_type`, `filter_cutoff_low__Hz`, `filter_cutoff_high__Hz`, `quality_metric`, `data_unit_measurement`, `sample_frequency__Hz` | `unit_ID`, **`depth__um`**, `area`, `spike_sorting_ID`, `quality`, `grid_location` (row, col) |
| **Spike waveforms** | `probe`, `clustering_algorithm`, `sample_frequency__Hz`, `data_unit_measurement` | `unit_ID`, `primary_channel` (see LFP `channel_ID`) |
| **Local field potentials** | `probe`, `filter_type`, `filter_cutoff_low__Hz`, `filter_cutoff_high__Hz`, `data_unit_measurement`, `sample_frequency__Hz` | `channel_ID`, `channel_label`, `area`, `grid_location` |
| **Behavioral time series** | `data_unit_measurement`, `sample_frequency__Hz` | `feature_ID`, `feature_label` |
| **Behavioral events** | — | `event_ID`, `event_label` |

**Table 2:** sessionInfo scalars, optional schema mirrors, and per-unit metadata (representative fields). Example: **`spikeTimes_probe`** in sessionInfo; optional schema key **`probe`**.

## **Trial information files**

**One table per session.** Set **`trialInfo = 1`** in **`sessionInfo.csv`** when present. **Canonical file name:** `trialInfo.csv` inside the session folder (verbose alias allowed).

Tabular **`.csv`**: one row per trial.

**Required** columns (only these two; headers use **dunder + unit** where applicable):

| Column | Description |
| :---- | :---- |
| start_time__s | Trial start (seconds relative to the **session origin**, t = 0) |
| stop_time__s | Trial end (seconds relative to the **session origin**, t = 0) |

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
