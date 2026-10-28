"""Build a small SurLab-format-compliant demo dataset (no legacy headers/layouts)."""

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

from src.data_io import load_numeric_array, load_spike_times_by_unit, save_spike_times_npz

LEGACY = ROOT / "demo_data" / "SeqBias_AstroBlock_NPX" / "AstroDREADD25_20240702"
OUT_DATASET = ROOT / "demo_data" / "surlab_format_demo"
DATASET_ID = "surlab_format_demo"
ANIMAL_ID = "AstroDREADD25"
SESSION_ID = "20240702"
SESSION_DIRNAME = f"{ANIMAL_ID}_{SESSION_ID}"


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


def _savez(path: Path, key: str, array: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **{key: array})


def build_session_info(session_dir: Path) -> dict[str, str]:
    row = {
        "institution": "MIT",
        "lab": "SurLab",
        "experimenter": "Gabrielle Drummond",
        "animal_ID": ANIMAL_ID,
        "session_ID": SESSION_ID,
        "session_date": "2024-07-02",
        "species": "Mus musculus",
        "sex": "U",
        "age__days": "90",
        "strain": "C57BL/6",
        "area": "PFC",
        "condition": "CNO",
        "related_publication": "Drummond et al. (2024). doi: 10.1101/2024.10.24.620009",
        "zero_time": "spikeTimes",
        "spikeTimes": "1",
        "spikeWaves": "1",
        "lfp": "1",
        "trialInfo": "1",
        "lick_behEvents": "1",
        "spikeTimes_probe": "Neuropixel1.0",
        "spikeTimes_acquisition_software": "SpikeGLX",
        "spikeTimes_sorting_software": "Kilosort",
        "spikeTimes_sample_frequency__Hz": "30000",
        "spikeTimes_data_unit_measurement": "time__s",
        "spikeTimes_quality_metric": "binary_good_unit_0_1",
        "lfp_probe": "Neuropixel1.0",
        "lfp_sample_frequency__Hz": "2500",
        "lfp_data_unit_measurement": "amplitude__V",
        "lfp_filter_type": "bandpass",
        "lfp_filter_cutoff_low__Hz": "0.5",
        "lfp_filter_cutoff_high__Hz": "300",
        "spikeWaves_probe": "Neuropixel1.0",
        "spikeWaves_sample_frequency__Hz": "30000",
        "spikeWaves_data_unit_measurement": "amplitude__au",
        "spikeWaves_clustering_algorithm": "Kilosort",
    }
    headers = list(row.keys())
    _write_csv(session_dir / "sessionInfo_single_session.csv", headers, [row])
    _write_csv(OUT_DATASET / f"sessionInfo_{DATASET_ID}.csv", headers, [row])
    return row


def build_spike_times(session_dir: Path) -> None:
    legacy = LEGACY / "spikeTimes_data.mat"
    if not legacy.exists():
        legacy = LEGACY / "spikeTimes_data_SeqBias_AstroBlock_NPX_examp_AstroDREADD25_20240702.mat"
    series = load_spike_times_by_unit(legacy)[:5]
    save_spike_times_npz(session_dir / "spikeTimes_data.npz", series)

    meta_rows = []
    legacy_meta = LEGACY / "spikeTimes_metadata.csv"
    if not legacy_meta.exists():
        legacy_meta = LEGACY / "spikeTimes_metadata_SeqBias_AstroBlock_NPX_examp_AstroDREADD25_20240702.csv"
    with legacy_meta.open(encoding="utf-8", newline="") as handle:
        for index, record in enumerate(csv.DictReader(handle)):
            if index >= 5:
                break
            meta_rows.append(
                {
                    "unit_ID": str(index + 1),
                    "depth__um": record.get("depth__um") or record.get("depth", ""),
                    "area": record.get("area", "PFC"),
                    "spike_sorting_ID": record.get("spike_sorting_ID") or record.get("spikesorting_ID", ""),
                    "quality": record.get("quality", "0"),
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
            "X_dim": "units",
            "Y_dim": "spikes",
            "X_size": len(series),
        },
    )


def build_lfp(session_dir: Path) -> None:
    n_time = 1000
    n_channels = 8
    sample_hz = 2500.0
    timestamps = np.arange(n_time, dtype=float) / sample_hz
    # Canonical SurLab: time x channels
    data = (np.sin(2 * np.pi * 8.0 * timestamps)[:, None] * np.linspace(0.5, 1.0, n_channels)).astype(
        float
    )
    _savez(session_dir / "lfp_data.npz", "data", data)
    _savez(session_dir / "lfp_timestamps.npz", "timestamps", timestamps)
    meta = [
        {
            "channel_ID": str(i + 1),
            "channel_label": f"ch{i + 1}",
            "area": "PFC",
            "grid_location": f"{i // 2},{i % 2}",
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
            "X_dim": "time",
            "Y_dim": "channel",
            "X_size": n_time,
            "Y_size": n_channels,
        },
    )


def build_spike_waves(session_dir: Path) -> None:
    legacy = LEGACY / "spikeWaves_data.mat"
    if not legacy.exists():
        legacy = LEGACY / "spikeWaves_data_SeqBias_AstroBlock_NPX_examp_AstroDREADD25_20240702.mat"

    raw = load_numeric_array(legacy)
    # Expect waveform_samples x units; keep first 5 units, all samples or truncate
    if raw.ndim != 2:
        raise ValueError(f"Unexpected spikeWaves shape {raw.shape}")
    waves = np.asarray(raw[:, :5], dtype=float)
    _savez(session_dir / "spikeWaves_data.npz", "data", waves)
    meta = [
        {"unit_ID": str(i + 1), "primary_channel": str(i + 1)}
        for i in range(waves.shape[1])
    ]
    _write_csv(
        session_dir / "spikeWaves_metadata.csv",
        ["unit_ID", "primary_channel"],
        meta,
    )
    # Optional: snippet-relative sample times (NOT session clock). Makes sampling explicit.
    snippet_hz = 30000.0
    snippet_times = np.arange(waves.shape[0], dtype=float) / snippet_hz
    _savez(session_dir / "spikeWaves_timestamps.npz", "timestamps", snippet_times)
    _write_json(
        session_dir / "spikeWaves_schema.json",
        {
            "data_unit_measurement": "amplitude__au",
            "sample_frequency__Hz": snippet_hz,
            "probe": "Neuropixel1.0",
            "X_dim": "waveform_sample",
            "Y_dim": "unit",
            "X_size": int(waves.shape[0]),
            "Y_size": int(waves.shape[1]),
        },
    )


def build_beh_events(session_dir: Path) -> None:
    # Prefixed stream: lick_behEvents. Event times in seconds (session clock).
    event_times = np.array([1.2, 3.4, 5.6, 8.0, 12.5], dtype=float)
    container = np.empty((1, 1), dtype=object)
    container[0, 0] = event_times
    _savez(session_dir / "lick_behEvents_data.npz", "data", container)
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
    # Prefer canonical SeqBias trialInfo; fall back to legacy filename during migration.
    legacy = LEGACY / "trialInfo.csv"
    if not legacy.exists():
        legacy = LEGACY / "trialInfo_SeqBias_AstroBlock_NPX_examp_AstroDREADD25_20240702.csv"
    rows = []
    with legacy.open(encoding="utf-8", newline="") as handle:
        for index, record in enumerate(csv.DictReader(handle)):
            if index >= 20:
                break
            # Already-canonical SeqBias rows use action/correct/dunder headers.
            if "action" in record and "tone_frequency__Hz" in record:
                rows.append(
                    {
                        "start_time__s": record.get("start_time__s", ""),
                        "stop_time__s": record.get("stop_time__s", ""),
                        "stimulus_onset__s": record.get("stimulus_onset__s", ""),
                        "stimulus_offset__s": record.get("stimulus_offset__s", ""),
                        "tone_frequency__Hz": record.get("tone_frequency__Hz", "NaN"),
                        "tone_intensity__dB": record.get("tone_intensity__dB", "NaN"),
                        "action": record.get("action", ""),
                        "reaction_time__s": _missing_numeric_token(record.get("reaction_time__s", "")),
                        "correct": record.get("correct", ""),
                        "trial_type": record.get("trial_type", ""),
                    }
                )
                continue
            action, correct, trial_type = _canonical_trial_behavior(record)
            rows.append(
                {
                    "start_time__s": record.get("start_time", ""),
                    "stop_time__s": record.get("stop_time", ""),
                    "stimulus_onset__s": record.get("stim_onset", ""),
                    "stimulus_offset__s": record.get("stim_offset", ""),
                    "tone_frequency__Hz": _tone_freq_to_hz(record.get("tone_freq", "")),
                    "tone_intensity__dB": _tone_intensity_to_db(record.get("tone_intensity", "")),
                    "action": action,
                    "reaction_time__s": _missing_numeric_token(record.get("reaction_time", "")),
                    "correct": correct,
                    "trial_type": trial_type,
                }
            )
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


def _missing_numeric_token(raw: object) -> str:
    text = str(raw).strip()
    if text.lower() in {"", "nan", "na", "none", "null"}:
        return "NaN"
    return text


def _tone_freq_to_hz(raw: object) -> str:
    """Legacy '4kHz' / bare 4 (kHz digit) → Hz for header tone_frequency__Hz."""
    import re

    text = str(raw).strip()
    if text.lower() in {"", "nan", "na", "none", "null"}:
        return "NaN"
    match = re.fullmatch(r"(?i)\s*([+-]?\d+(?:\.\d+)?)\s*khz\s*", text)
    if match:
        return str(int(float(match.group(1)) * 1000))
    match = re.fullmatch(r"(?i)\s*([+-]?\d+(?:\.\d+)?)\s*hz\s*", text)
    if match:
        value = float(match.group(1))
        return str(int(value)) if value.is_integer() else str(value)
    try:
        value = float(text)
    except ValueError:
        return "NaN"
    if value >= 100:
        return str(int(value)) if value.is_integer() else str(value)
    return str(int(value * 1000))


def _tone_intensity_to_db(raw: object) -> str:
    import re

    text = str(raw).strip()
    if text.lower() in {"", "nan", "na", "none", "null"}:
        return "NaN"
    match = re.fullmatch(r"(?i)\s*([+-]?\d+(?:\.\d+)?)\s*db\s*", text)
    if match:
        value = float(match.group(1))
        return str(int(value)) if value.is_integer() else str(value)
    try:
        value = float(text)
    except ValueError:
        return "NaN"
    return str(int(value)) if value.is_integer() else str(value)


def _canonical_trial_behavior(record: dict[str, str]) -> tuple[str, str, str]:
    """Map legacy output/correct/trial_type to canonical action/correct/trial_type."""
    output_raw = str(record.get("output", "")).strip()
    correct_raw = str(record.get("correct", "")).strip().lower()
    trial_type_raw = str(record.get("trial_type", "")).strip().lower()

    if correct_raw == "early_press" or trial_type_raw == "early_press" or output_raw.lower() == "nan":
        return "early_press", "", "aborted"

    action = output_raw
    if action.lower() in {"nan", "na", "none", "null"}:
        action = ""

    if correct_raw in {"correct", "1", "true"}:
        correct = "correct"
    elif correct_raw in {"error", "incorrect", "0", "false"}:
        correct = "incorrect"
    else:
        correct = ""

    if trial_type_raw in {"hit", "miss", "fa", "cr", "aborted"}:
        trial_type = trial_type_raw
    elif trial_type_raw in {"", "nan", "na", "none", "null"}:
        trial_type = ""
    else:
        trial_type = trial_type_raw

    return action, correct, trial_type


def main() -> None:
    if OUT_DATASET.exists():
        shutil.rmtree(OUT_DATASET)
    session_dir = OUT_DATASET / SESSION_DIRNAME
    session_dir.mkdir(parents=True)

    build_session_info(session_dir)
    build_spike_times(session_dir)
    build_lfp(session_dir)
    build_spike_waves(session_dir)
    build_beh_events(session_dir)
    build_trial_info(session_dir)

    readme = OUT_DATASET / "README.md"
    readme.write_text(
        f"""# `{DATASET_ID}` — canonical SurLab format demo

Small single-session demo that follows **current** SurLab naming and layout
(minimal filenames, dunder units, time×channels LFP, prefixed `lick_behEvents`).

Session folder: `{SESSION_DIRNAME}/`

Built from a subset of `SeqBias_AstroBlock_NPX` plus synthetic LFP/behEvents.
The older `SeqBias_AstroBlock_NPX` tree remains as a **legacy** example only.

Rebuild:

```bat
python developer_scripts/build_surlab_format_demo.py
```
""",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_DATASET}")


if __name__ == "__main__":
    main()
