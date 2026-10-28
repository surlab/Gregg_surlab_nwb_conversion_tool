# SeqBias_AstroBlock_NPX (archival demo)

Session `AstroDREADD25_20240702/` was rewritten to **canonical SurLab** naming
(headers, `trialInfo.csv`, schemas, minimal stems). Binary `.mat` kept.

Re-apply:

```bat
python developer_scripts/canonicalize_seqbias_session.py
```

Notes:

- `tone_frequency__Hz` cells are **Hz** (`4kHz` → `4000`).
- Missing numeric trial cells use token **`NaN`**; missing `age__days` is empty.
- `spikeWaves_metadata.csv` has no `area` (region on spikeTimes only).
- LFP is canonical **time × channels** in `lfp_data.npz` (large; gitignored,
  including verbose `lfp_data_*.npz` aliases). Schema: `X_dim=time`,
  `Y_dim=channel`. Generated `.nwb`, `roundtrip_surformat/`, and run/validation
  reports under `demo_data/` are also gitignored — rebuild with the root bats.
