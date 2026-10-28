"""Build synthetic all-modalities SurLab demo for round-trip testing.

See for_cursor/dummy_dataset_empty_modalities_checklist.txt for design notes.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_io import save_numeric_array_npz, save_spike_times_npz

OUT_DATASET = ROOT / "demo_data" / "kitchen_sink_demo"
DATASET_ID = "kitchen_sink_demo"
ANIMAL_ID = "KitchenSink01"
SESSION_ID = "20260827_roundtrip"
SESSION_DIRNAME = f"{ANIMAL_ID}_{SESSION_ID}"

RNG = np.random.default_rng(42)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _imaging_session_scalars(stream_id: str, indicator: str) -> dict[str, str]:
    """Per-stream sessionInfo columns shared by traces and behTSeries."""
    return {
        f"{stream_id}_indicator": indicator,
        f"{stream_id}_detection_software": "Suite2p" if stream_id.endswith("_traces") else "DeepLabCut",
        f"{stream_id}_wavelength__nm": "920",
        f"{stream_id}_laser_name": "Insight Pockels",
        f"{stream_id}_objectives": "16X_0.8NA",
        f"{stream_id}_fov_width__pixels": "512",
        f"{stream_id}_fov_height__pixels": "512",
        f"{stream_id}_fov_depth__um": "180",
        f"{stream_id}_pixel_size__um": "1.61",
        f"{stream_id}_pixel_size_calibration": "calibrated from stage micrometer 2026-01-15",
    }


def _imaging_schema(
    stream_id: str,
    indicator: str,
    n_time: int,
    n_y: int,
    sample_hz: float,
    data_unit: str,
    y_dim: str,
) -> dict:
    y_idx = list(range(n_y))
    payload = {
        "data_unit_measurement": data_unit,
        "X_dim": "time",
        "Y_dim": y_dim,
        "X_size": n_time,
        "Y_size": n_y,
        "Y_idx": y_idx,
        "sample_frequency__Hz": sample_hz,
        "indicator": indicator,
        "detection_software": "Suite2p" if stream_id.endswith("_traces") else "DeepLabCut",
        "wavelength__nm": 920.0,
        "laser_name": "Insight Pockels",
        "objectives": "16X_0.8NA",
        "fov_width__pixels": 512,
        "fov_height__pixels": 512,
        "fov_depth__um": 180.0,
        "pixel_size__um": 1.61,
        "pixel_size_calibration": "calibrated from stage micrometer 2026-01-15",
    }
    return payload


def build_session_info(session_dir: Path) -> dict[str, str]:
    row: dict[str, str] = {
        "institution": "MIT",
        "lab": "SurLab",
        "experimenter": "Roundtrip Test",
        "animal_ID": ANIMAL_ID,
        "session_ID": SESSION_ID,
        "session_date": "2026-08-27",
        "species": "Mus musculus",
        "sex": "M",
        "age__days": "120",
        "strain": "C57BL/6",
        "area": "VISp+PFC",
        "condition": "synthetic kitchen-sink roundtrip",
        "related_publication": "internal demo only",
        "zero_time": "GCaMP8m_traces",
        "spikeTimes": "1",
        "spikeWaves": "1",
        "lfp": "1",
        "trialInfo": "1",
        "GCaMP8m_traces": "1",
        "Neuropil_traces": "1",
        "pupil_behTSeries": "1",
        "wheel_behTSeries": "0",
        "lick_behEvents": "1",
        "spikeTimes_probe": "Neuropixel1.0",
        "spikeTimes_acquisition_software": "SpikeGLX",
        "spikeTimes_sorting_software": "Kilosort4",
        "spikeTimes_sample_frequency__Hz": "30000",
        "spikeTimes_data_unit_measurement": "time__s",
        "spikeTimes_quality_metric": "binary_good_unit_0_1",
        "spikeTimes_filter_type": "bandpass",
        "spikeTimes_filter_cutoff_low__Hz": "300",
        "spikeTimes_filter_cutoff_high__Hz": "6000",
        "lfp_probe": "Neuropixel1.0",
        "lfp_sample_frequency__Hz": "2500",
        "lfp_data_unit_measurement": "amplitude__V",
        "lfp_filter_type": "bandpass",
        "lfp_filter_cutoff_low__Hz": "0.5",
        "lfp_filter_cutoff_high__Hz": "300",
        "spikeWaves_probe": "Neuropixel1.0",
        "spikeWaves_sample_frequency__Hz": "30000",
        "spikeWaves_data_unit_measurement": "amplitude__au",
        "spikeWaves_clustering_algorithm": "Kilosort4",
    }
    row.update(_imaging_session_scalars("GCaMP8m_traces", "GCaMP8m"))
    row.update(_imaging_session_scalars("Neuropil_traces", "Neuropil"))
    row.update(_imaging_session_scalars("pupil_behTSeries", "pupil"))

    headers = list(row.keys())
    _write_csv(session_dir / "sessionInfo_single_session.csv", headers, [row])
    _write_csv(OUT_DATASET / f"sessionInfo_{DATASET_ID}.csv", headers, [row])
    return row


def build_spike_times(session_dir: Path) -> None:
    n_units = 10
    series = []
    for unit_index in range(n_units):
        spike_count = int(RNG.integers(8, 16))
        times = np.sort(RNG.uniform(0.5, 30.0, size=spike_count))
        series.append(times.astype(float))
    save_spike_times_npz(session_dir / "spikeTimes_data.npz", series)

    meta_rows = []
    for unit_index in range(n_units):
        meta_rows.append(
            {
                "unit_ID": str(unit_index + 1),
                "depth__um": str(100 + 40 * unit_index),
                "area": "PFC" if unit_index < 5 else "VISp",
                "spike_sorting_ID": str(unit_index + 1),
                "quality": "1" if unit_index % 3 else "0",
            }
        )
    _write_csv(
        session_dir / "spikeTimes_metadata.csv",
        ["unit_ID", "depth__um", "area", "spike_sorting_ID", "quality"],
        meta_rows,
    )
    _write_json(
        session_dir / "spikeTimes_schema.json",
        {
            "data_unit_measurement": "time__s",
            "sample_frequency__Hz": 30000.0,
            "probe": "Neuropixel1.0",
            "acquisition_software": "SpikeGLX",
            "sorting_software": "Kilosort4",
            "quality_metric": "binary_good_unit_0_1",
            "filter_type": "bandpass",
            "filter_cutoff_low__Hz": 300.0,
            "filter_cutoff_high__Hz": 6000.0,
            "X_dim": "units",
            "Y_dim": "spikes",
            "X_size": n_units,
        },
    )


def build_traces(session_dir: Path, stream_id: str, indicator: str, n_time: int, n_roi: int, sample_hz: float) -> None:
    timestamps = np.arange(n_time, dtype=float) / sample_hz
    t = timestamps[:, None]
    data = np.zeros((n_time, n_roi), dtype=float)
    for roi_index in range(n_roi):
        freq = 0.5 + 0.1 * roi_index
        phase = float(RNG.uniform(0, 2 * np.pi))
        amplitude = 0.8 if indicator == "GCaMP8m" else 0.3
        data[:, roi_index] = amplitude * (1.0 + 0.2 * np.sin(2 * np.pi * freq * t[:, 0] + phase))
        data[:, roi_index] += RNG.normal(0, 0.02, size=n_time)
    save_numeric_array_npz(session_dir / f"{stream_id}_data.npz", data)
    save_numeric_array_npz(session_dir / f"{stream_id}_timestamps.npz", timestamps, array_key="timestamps")

    meta_rows = []
    for roi_index in range(n_roi):
        meta_rows.append(
            {
                "roi_ID": str(roi_index),
                "roi_x_coordinates": str(100 + 20 * roi_index),
                "roi_y_coordinates": str(200 + 15 * roi_index),
                "roi_center_x": str(105 + 20 * roi_index),
                "roi_center_y": str(205 + 15 * roi_index),
                "area": "VISp",
                "iscell": "1",
                "fluorophore_class": indicator,
            }
        )
    _write_csv(
        session_dir / f"{stream_id}_metadata.csv",
        [
            "roi_ID",
            "roi_x_coordinates",
            "roi_y_coordinates",
            "roi_center_x",
            "roi_center_y",
            "area",
            "iscell",
            "fluorophore_class",
        ],
        meta_rows,
    )
    _write_json(
        session_dir / f"{stream_id}_schema.json",
        _imaging_schema(
            stream_id,
            indicator,
            n_time,
            n_roi,
            sample_hz,
            "fluorescence__a.u.",
            "ROI",
        ),
    )


def build_pupil_beh_tseries(session_dir: Path) -> None:
    stream_id = "pupil_behTSeries"
    n_time = 500
    n_features = 3
    sample_hz = 30.0
    timestamps = np.arange(n_time, dtype=float) / sample_hz
    t = timestamps
    area = 0.5 + 0.1 * np.sin(2 * np.pi * 0.3 * t) + RNG.normal(0, 0.01, size=n_time)
    x_pos = 0.1 * np.sin(2 * np.pi * 0.2 * t + 0.5) + RNG.normal(0, 0.005, size=n_time)
    y_pos = 0.08 * np.cos(2 * np.pi * 0.25 * t) + RNG.normal(0, 0.005, size=n_time)
    data = np.column_stack([area, x_pos, y_pos])
    save_numeric_array_npz(session_dir / f"{stream_id}_data.npz", data)
    save_numeric_array_npz(session_dir / f"{stream_id}_timestamps.npz", timestamps, array_key="timestamps")
    _write_csv(
        session_dir / f"{stream_id}_metadata.csv",
        ["feature_ID", "feature_label"],
        [
            {"feature_ID": "0", "feature_label": "pupil_area_norm"},
            {"feature_ID": "1", "feature_label": "pupil_x_norm"},
            {"feature_ID": "2", "feature_label": "pupil_y_norm"},
        ],
    )
    _write_json(
        session_dir / f"{stream_id}_schema.json",
        _imaging_schema(
            stream_id,
            "pupil",
            n_time,
            n_features,
            sample_hz,
            "mixed__see_metadata",
            "features",
        ),
    )


def build_lfp(session_dir: Path) -> None:
    n_time = 1000
    n_channels = 16
    sample_hz = 2500.0
    timestamps = np.arange(n_time, dtype=float) / sample_hz
    data = (
        np.sin(2 * np.pi * 8.0 * timestamps)[:, None] * np.linspace(0.5, 1.0, n_channels)
    ).astype(float)
    save_numeric_array_npz(session_dir / "lfp_data.npz", data)
    save_numeric_array_npz(session_dir / "lfp_timestamps.npz", timestamps, array_key="timestamps")
    meta = [
        {
            "channel_ID": str(i + 1),
            "channel_label": f"ch{i + 1}",
            "area": "PFC" if i < 8 else "VISp",
            "grid_location": f"{i // 4},{i % 4}",
            "depth__um": str(20 * (i + 1)),
        }
        for i in range(n_channels)
    ]
    _write_csv(
        session_dir / "lfp_metadata.csv",
        ["channel_ID", "channel_label", "area", "grid_location", "depth__um"],
        meta,
    )
    _write_json(
        session_dir / "lfp_schema.json",
        {
            "data_unit_measurement": "amplitude__V",
            "sample_frequency__Hz": sample_hz,
            "probe": "Neuropixel1.0",
            "filter_type": "bandpass",
            "filter_cutoff_low__Hz": 0.5,
            "filter_cutoff_high__Hz": 300.0,
            "X_dim": "time",
            "Y_dim": "channel",
            "X_size": n_time,
            "Y_size": n_channels,
        },
    )


def build_spike_waves(session_dir: Path) -> None:
    n_samples = 40
    n_units = 10
    t = np.linspace(-1, 1, n_samples)
    waves = np.zeros((n_samples, n_units), dtype=float)
    for unit_index in range(n_units):
        center = -0.2 + 0.05 * unit_index
        width = 0.08 + 0.01 * unit_index
        waves[:, unit_index] = -0.8 * np.exp(-((t - center) ** 2) / (2 * width**2))
        waves[:, unit_index] += RNG.normal(0, 0.02, size=n_samples)
    save_numeric_array_npz(session_dir / "spikeWaves_data.npz", waves)
    snippet_hz = 30000.0
    snippet_times = np.arange(n_samples, dtype=float) / snippet_hz
    save_numeric_array_npz(session_dir / "spikeWaves_timestamps.npz", snippet_times, array_key="timestamps")
    meta = [{"unit_ID": str(i + 1), "primary_channel": str(i + 1)} for i in range(n_units)]
    _write_csv(
        session_dir / "spikeWaves_metadata.csv",
        ["unit_ID", "primary_channel"],
        meta,
    )
    _write_json(
        session_dir / "spikeWaves_schema.json",
        {
            "data_unit_measurement": "amplitude__au",
            "sample_frequency__Hz": snippet_hz,
            "probe": "Neuropixel1.0",
            "clustering_algorithm": "Kilosort4",
            "X_dim": "waveform_sample",
            "Y_dim": "unit",
            "X_size": n_samples,
            "Y_size": n_units,
        },
    )


def build_beh_events(session_dir: Path) -> None:
    event_times = np.sort(RNG.uniform(0.5, 25.0, size=50)).astype(float)
    container = np.empty((1, 1), dtype=object)
    container[0, 0] = event_times
    save_numeric_array_npz(session_dir / "lick_behEvents_data.npz", container)
    _write_csv(
        session_dir / "lick_behEvents_metadata.csv",
        ["event_ID", "event_label"],
        [{"event_ID": "1", "event_label": "lick"}],
    )
    _write_json(
        session_dir / "lick_behEvents_schema.json",
        {
            "data_unit_measurement": "time__s",
            "X_dim": "event_type",
            "Y_dim": "events",
            "X_size": 1,
            "Y_size": 1,
        },
    )


def build_trial_info(session_dir: Path) -> None:
    rows = []
    trial_types = ["hit", "miss", "fa", "cr", "aborted"]
    actions = ["press", "no_press", "early_press"]
    start = 10.0
    for trial_index in range(20):
        trial_type = trial_types[trial_index % len(trial_types)]
        if trial_type == "aborted":
            action = "early_press"
            correct = ""
        elif trial_type == "hit":
            action = "press"
            correct = "correct"
        elif trial_type == "miss":
            action = "no_press"
            correct = "incorrect"
        elif trial_type == "fa":
            action = "press"
            correct = "incorrect"
        else:
            action = "no_press"
            correct = "correct"
        # Values are Hz to match tone_frequency__Hz (4/8/12 kHz tones).
        tone_hz = (4 + (trial_index % 3) * 4) * 1000
        tone_db = 5 + (trial_index % 4) * 10
        stim_on = start + 0.6
        stim_off = stim_on + 0.5
        stop = start + 6.0
        reaction = (
            "NaN"
            if action in {"", "no_press", "early_press"}
            else f"{0.15 + 0.02 * trial_index:.4f}"
        )
        rows.append(
            {
                "start_time__s": f"{start:.4f}",
                "stop_time__s": f"{stop:.4f}",
                "stimulus_onset__s": f"{stim_on:.4f}",
                "stimulus_offset__s": f"{stim_off:.4f}",
                "tone_frequency__Hz": str(tone_hz),
                "tone_intensity__dB": str(tone_db),
                "action": action,
                "reaction_time__s": reaction,
                "correct": correct,
                "trial_type": trial_type,
            }
        )
        start = stop + 0.12
    _write_csv(
        session_dir / "trialInfo.csv",
        [
            "start_time__s",
            "stop_time__s",
            "stimulus_onset__s",
            "stimulus_offset__s",
            "tone_frequency__Hz",
            "tone_intensity__dB",
            "action",
            "reaction_time__s",
            "correct",
            "trial_type",
        ],
        rows,
    )


def main() -> None:
    if OUT_DATASET.exists():
        shutil.rmtree(OUT_DATASET)
    session_dir = OUT_DATASET / SESSION_DIRNAME
    session_dir.mkdir(parents=True)

    build_session_info(session_dir)
    build_spike_times(session_dir)
    build_traces(session_dir, "GCaMP8m_traces", "GCaMP8m", n_time=100, n_roi=5, sample_hz=15.0)
    build_traces(session_dir, "Neuropil_traces", "Neuropil", n_time=100, n_roi=5, sample_hz=15.0)
    build_pupil_beh_tseries(session_dir)
    build_lfp(session_dir)
    build_spike_waves(session_dir)
    build_beh_events(session_dir)
    build_trial_info(session_dir)

    readme = OUT_DATASET / "README.md"
    readme.write_text(
        f"""# `{DATASET_ID}` — round-trip kitchen sink demo

Fully **synthetic** single-session dataset covering all implemented SurLab modalities
with **non-empty** arrays and populated optional metadata. Intended for Task 5
round-trip validation, not as the primary format-validation demo.

Session folder: `{SESSION_DIRNAME}/`

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
""",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_DATASET}")


if __name__ == "__main__":
    main()
