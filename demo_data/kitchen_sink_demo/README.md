# `kitchen_sink_demo` — round-trip kitchen sink demo

Fully **synthetic** single-session dataset covering all implemented SurLab modalities
with **non-empty** arrays and populated optional metadata. Intended for Task 5
round-trip validation, not as the primary format-validation demo.

Session folder: `KitchenSink01_20260827_roundtrip/`

| Modality | Notes |
| :---- | :---- |
| spikeTimes | 10 units, synthetic spike trains |
| GCaMP8m_traces, Neuropil_traces | 100 frames × 5 ROIs @ 15 Hz |
| pupil_behTSeries | 500 samples × 3 features @ 30 Hz (non-empty) |
| wheel_behTSeries | **flag=0**, no files (N/A path test) |
| lfp | 1000 samples × 16 channels @ 2.5 kHz |
| spikeWaves | 40 samples × 10 units |
| lick_behEvents | 50 lick times |
| trialInfo | 20 operant trials |

Design checklist: `for_cursor/dummy_dataset_empty_modalities_checklist.txt`

Rebuild:

```bat
python developer_scripts/build_kitchen_sink_demo.py
```

Round-trip:

```bat
run_roundtrip_kitchen_sink_demo.bat
```
