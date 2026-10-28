# Demo datasets

Format docs: [basics](../docs/surlab_format_basics.md), [field catalog](../docs/surlab_field_catalog.md), [NWB conversion notes](../docs/nwb_conversion_notes.md).

Gitignores under `demo_data/`: continuous `lfp_data*` arrays, `*.nwb`,
`roundtrip_surformat/`, runlogs, and validation reports (rebuild with the
pipeline bats). Source SurLab session files for the demos stay tracked.

## Canonical: `surlab_format_demo/`

Primary end-to-end demo. Follows **current** SurLab naming and layout
(minimal filenames, dunder unit suffixes, time×channels LFP, prefixed
`lick_behEvents`, optional snippet-relative `spikeWaves_timestamps`).

Rebuild from legacy sources + synthetic LFP/events:

```bat
python developer_scripts/build_surlab_format_demo.py
```

Point bats / README / tests at this folder.

## Round-trip: `kitchen_sink_demo/`

Synthetic all-modalities session for Task 5 round-trip testing (non-empty behTSeries,
lfp, spikeWaves, behEvents, traces, operant trialInfo). Rebuild:

```bat
python developer_scripts/build_kitchen_sink_demo.py
```

Run round-trip:

```bat
run_roundtrip_kitchen_sink_demo.bat
```

See `for_cursor/dummy_dataset_empty_modalities_checklist.txt` for design notes.

## Legacy archival: `SeqBias_AstroBlock_NPX/`

Session `AstroDREADD25_20240702/` was rewritten to **canonical** SurLab naming
(headers, trialInfo, schemas, minimal stems). Binary `.mat` arrays kept.
Rebuild / re-apply:

```bat
python developer_scripts/canonicalize_seqbias_session.py
```

Other sessionInfo rows without folders remain for inventory only.
Large `lfp_data*.mat` remains gitignored when present.

Real lab data should live outside the repo and be pointed at via path args
or `src/config.py`.
