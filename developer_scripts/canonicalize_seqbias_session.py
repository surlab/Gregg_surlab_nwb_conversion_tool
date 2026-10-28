"""Rewrite SeqBias AstroDREADD25_20240702 (+ dataset sessionInfo) to current SurLab.

Leaves binary .mat arrays in place (possibly renamed to minimal stems).
Does not invent missing LFP data files.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATASET = ROOT / "demo_data" / "SeqBias_AstroBlock_NPX"
SESSION = DATASET / "AstroDREADD25_20240702"
DATASET_ID = "SeqBias_AstroBlock_NPX"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _parse_tone_hz(raw: str) -> str:
    """Map legacy tone labels to numeric Hz matching header tone_frequency__Hz."""
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
    # Bare number: treat as already-Hz only if large; else assume legacy kHz digit.
    try:
        value = float(text)
    except ValueError:
        return "NaN"
    if value >= 100:
        return str(int(value)) if value.is_integer() else str(value)
    # Small integers from SeqBias / stripped demos were kHz labels (4, 12).
    return str(int(value * 1000))


def _parse_intensity_db(raw: str) -> str:
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


def _missing_numeric(raw: str) -> str:
    text = str(raw).strip()
    if text.lower() in {"", "nan", "na", "none", "null"}:
        return "NaN"
    return text


def _parse_sess_date(raw: str) -> str:
    text = str(raw).strip()
    # MM-DD-YYYY → YYYY-MM-DD
    match = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", text)
    if match:
        month, day, year = match.groups()
        return f"{year}-{month}-{day}"
    return text


def _age_days(raw: str) -> str:
    """Unknown age → empty cell (not token NaN; age__days is optional numeric)."""
    text = str(raw).strip()
    if text.upper() in {"", "U", "UNKNOWN", "NAN", "NA"}:
        return ""
    return text


def _rename_mat(old_glob: str, new_name: str) -> None:
    matches = sorted(SESSION.glob(old_glob))
    if not matches:
        print(f"  skip rename (missing): {old_glob}")
        return
    source = matches[0]
    dest = SESSION / new_name
    if source.resolve() == dest.resolve():
        return
    if dest.exists():
        dest.unlink()
    shutil.move(str(source), str(dest))
    print(f"  renamed {source.name} -> {dest.name}")


def build_session_info_rows(legacy_rows: list[dict]) -> list[dict]:
    out = []
    for record in legacy_rows:
        animal = record.get("animal_ID") or record.get("animalID") or ""
        session = record.get("session_ID") or record.get("sessID") or ""
        # Flags: files exist for spikeTimes/spikeWaves/lfp/trialInfo on the one session.
        has_session_folder = (DATASET / f"{animal}_{session}").is_dir()
        lfp_flag = "1" if has_session_folder else (record.get("lfp") or "0")
        # Prefer presence of LFP files over legacy 0 when this is the on-disk session.
        if has_session_folder and list(SESSION.glob("lfp_timestamps*")):
            lfp_flag = "1"
        out.append(
            {
                "institution": record.get("institution", "MIT"),
                "lab": record.get("lab", "SurLab"),
                "experimenter": record.get("experimenter", ""),
                "animal_ID": animal,
                "session_ID": session,
                "session_date": _parse_sess_date(record.get("session_date") or record.get("sess_date") or ""),
                "species": record.get("species", "Mus musculus"),
                "sex": record.get("sex", "U"),
                "age__days": _age_days(record.get("age__days") or record.get("age") or ""),
                "strain": record.get("strain", ""),
                "area": record.get("area", ""),
                "condition": record.get("condition", ""),
                "related_publication": record.get("related_publication", ""),
                "zero_time": record.get("zero_time", "spikeTimes"),
                "spikeTimes": record.get("spikeTimes", "1"),
                "spikeWaves": record.get("spikeWaves", "1"),
                "lfp": lfp_flag,
                "trialInfo": record.get("trialInfo") or record.get("infoTrials") or "1",
                "spikeTimes_probe": "Neuropixel1.0",
                "spikeTimes_acquisition_software": "SpikeGLX",
                "spikeTimes_sorting_software": "Kilosort",
                "spikeTimes_sample_frequency__Hz": "30000",
                "spikeTimes_data_unit_measurement": "time__s",
                "spikeTimes_filter_type": "bandpass",
                "spikeTimes_filter_cutoff_low__Hz": "300",
                "spikeTimes_filter_cutoff_high__Hz": "9000",
                "lfp_probe": "Neuropixel1.0",
                "lfp_sample_frequency__Hz": "2500",
                "lfp_data_unit_measurement": "amplitude__V",
                "spikeWaves_probe": "Neuropixel1.0",
                "spikeWaves_data_unit_measurement": "amplitude__au",
            }
        )
    return out


def rewrite_session_info() -> None:
    legacy_dataset = DATASET / "sessionsInfo_SeqBias_AstroBlock_NPX_examp.csv"
    with legacy_dataset.open(encoding="utf-8", newline="") as handle:
        legacy_rows = list(csv.DictReader(handle))
    rows = build_session_info_rows(legacy_rows)
    headers = list(rows[0].keys())
    _write_csv(DATASET / f"sessionInfo_{DATASET_ID}.csv", headers, rows)

    # Session-local single row
    target = [row for row in rows if row["animal_ID"] == "AstroDREADD25" and row["session_ID"] == "20240702"]
    _write_csv(SESSION / "sessionInfo_single_session.csv", headers, target)

    # Remove legacy sessionInfo names to avoid dual discovery ambiguity.
    for path in [
        legacy_dataset,
        SESSION / "sessionsInfo_SeqBias_AstroBlock_NPX_examp_AstroDREADD25_20240702.csv",
    ]:
        if path.exists():
            path.unlink()
            print(f"  removed legacy {path.name}")


def rewrite_trial_info() -> None:
    legacy = SESSION / "trialInfo_SeqBias_AstroBlock_NPX_examp_AstroDREADD25_20240702.csv"
    rows = []
    with legacy.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            action_raw = str(record.get("output", "")).strip()
            correct_raw = str(record.get("correct", "")).strip().lower()
            trial_type_raw = str(record.get("trial_type", "")).strip().lower()

            if correct_raw == "early_press" or trial_type_raw == "early_press" or action_raw.lower() == "nan":
                action = "early_press"
                correct = ""
                trial_type = "aborted"
            else:
                action = "" if action_raw.lower() in {"nan", "na", "none", "null", ""} else action_raw
                if correct_raw in {"correct", "1", "true"}:
                    correct = "correct"
                elif correct_raw in {"error", "incorrect", "0", "false"}:
                    correct = "incorrect"
                else:
                    correct = ""
                if trial_type_raw in {"hit", "miss", "fa", "cr", "aborted"}:
                    trial_type = trial_type_raw
                else:
                    trial_type = trial_type_raw if trial_type_raw not in {"nan", ""} else ""

            rows.append(
                {
                    "start_time__s": record.get("start_time", ""),
                    "stop_time__s": record.get("stop_time", ""),
                    "stimulus_onset__s": record.get("stim_onset", ""),
                    "stimulus_offset__s": record.get("stim_offset", ""),
                    "tone_frequency__Hz": _parse_tone_hz(record.get("tone_freq", "")),
                    "tone_intensity__dB": _parse_intensity_db(record.get("tone_intensity", "")),
                    "action": action,
                    "reaction_time__s": _missing_numeric(record.get("reaction_time", "")),
                    "correct": correct,
                    "trial_type": trial_type,
                }
            )
    headers = [
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
    ]
    _write_csv(SESSION / "trialInfo.csv", headers, rows)
    legacy.unlink()
    print(f"  wrote trialInfo.csv ({len(rows)} trials); removed legacy trialInfo")


def rewrite_spike_times_metadata() -> None:
    legacy = next(SESSION.glob("spikeTimes_metadata*.csv"))
    rows = []
    with legacy.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            rows.append(
                {
                    "unit_ID": record.get("unit_ID", ""),
                    "depth__um": record.get("depth__um") or record.get("depth", ""),
                    "area": record.get("area", ""),
                    "spike_sorting_ID": record.get("spike_sorting_ID") or record.get("spikesorting_ID", ""),
                    "quality": record.get("quality", ""),
                }
            )
    _write_csv(
        SESSION / "spikeTimes_metadata.csv",
        ["unit_ID", "depth__um", "area", "spike_sorting_ID", "quality"],
        rows,
    )
    if legacy.name != "spikeTimes_metadata.csv":
        legacy.unlink()


def rewrite_spike_waves_metadata() -> None:
    legacy = next(SESSION.glob("spikeWaves_metadata*.csv"))
    rows = []
    with legacy.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            # No area on spikeWaves (region lives on spikeTimes only).
            rows.append(
                {
                    "unit_ID": record.get("unit_ID", ""),
                    "primary_channel": record.get("primary_channel") or record.get("unit_ID", ""),
                }
            )
    _write_csv(SESSION / "spikeWaves_metadata.csv", ["unit_ID", "primary_channel"], rows)
    if legacy.name != "spikeWaves_metadata.csv":
        legacy.unlink()


def rewrite_lfp_metadata() -> None:
    legacy = next(SESSION.glob("lfp_metadata*.csv"))
    rows = []
    with legacy.open(encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            channel = record.get("channel_ID") or record.get("unit_ID", "")
            rows.append(
                {
                    "channel_ID": channel,
                    "channel_label": record.get("channel_label") or f"ch{channel}",
                    "area": record.get("area", ""),
                    "depth__um": record.get("depth__um") or record.get("depth", ""),
                    "good_channel": record.get("good_channel", ""),
                }
            )
    _write_csv(
        SESSION / "lfp_metadata.csv",
        ["channel_ID", "channel_label", "area", "depth__um", "good_channel"],
        rows,
    )
    if legacy.name != "lfp_metadata.csv":
        legacy.unlink()


def rewrite_schemas() -> None:
    # spikeTimes
    legacy = next(SESSION.glob("spikeTimes_schema*.json"))
    with legacy.open(encoding="utf-8") as handle:
        old = json.load(handle)
    n_units = int(old.get("Xsize") or old.get("X_size") or 309)
    payload = {
        "data_unit_measurement": "time__s",
        "sample_frequency__Hz": float(old.get("sampFreq") or old.get("sample_frequency__Hz") or 30000),
        "probe": old.get("probe", "Neuropixel1.0"),
        "acquisition_software": "SpikeGLX",
        "sorting_software": old.get("sorting_software", "Kilosort"),
        "filter_type": "bandpass",
        "filter_cutoff_low__Hz": 300.0,
        "filter_cutoff_high__Hz": 9000.0,
        "X_dim": "units",
        "Y_dim": "spikes",
        "X_size": n_units,
    }
    _write_json(SESSION / "spikeTimes_schema.json", payload)
    if legacy.name != "spikeTimes_schema.json":
        legacy.unlink()

    # spikeWaves — sampFreq was MATLAB [] ; omit unknown rate or use 30000
    legacy = next(SESSION.glob("spikeWaves_schema*.json"))
    with legacy.open(encoding="utf-8") as handle:
        old = json.load(handle)
    samp = old.get("sampFreq", old.get("sample_frequency__Hz"))
    if isinstance(samp, list) or samp in (None, "", []):
        samp_hz = 30000.0
    else:
        samp_hz = float(samp)
    payload = {
        "data_unit_measurement": "amplitude__au",
        "sample_frequency__Hz": samp_hz,
        "probe": old.get("probe", "Neuropixel1.0"),
        "X_dim": "waveform_sample",
        "Y_dim": "unit",
        "X_size": int(old.get("Xsize") or old.get("X_size") or 82),
        "Y_size": int(old.get("Ysize") or old.get("Y_size") or 309),
    }
    _write_json(SESSION / "spikeWaves_schema.json", payload)
    if legacy.name != "spikeWaves_schema.json":
        legacy.unlink()

    # lfp — canonical time × channels (after transpose_lfp_array)
    legacy_matches = list(SESSION.glob("lfp_schema*.json"))
    old: dict = {}
    if legacy_matches:
        legacy = legacy_matches[0]
        with legacy.open(encoding="utf-8") as handle:
            old = json.load(handle)
    n_channels = int(old.get("Xsize") or old.get("X_size") or old.get("Y_size") or 384)
    n_time = int(float(old.get("Ysize") or old.get("Y_size") or old.get("X_size") or 0))
    # If schema already time×channels, keep sizes; else swap legacy channels×time.
    if str(old.get("X_dim", "")).lower() in {"time", "time [s]"}:
        n_time = int(float(old.get("X_size") or n_time))
        n_channels = int(old.get("Y_size") or n_channels)
    elif str(old.get("X_dim", "")).lower().startswith("channel"):
        n_channels = int(old.get("X_size") or n_channels)
        n_time = int(float(old.get("Y_size") or n_time))
    payload = {
        "data_unit_measurement": "amplitude__V",
        "sample_frequency__Hz": float(old.get("sampFreq") or old.get("sample_frequency__Hz") or 2500),
        "probe": old.get("probe", "Neuropixel1.0"),
        "X_dim": "time",
        "Y_dim": "channel",
        "X_size": n_time,
        "Y_size": n_channels,
    }
    _write_json(SESSION / "lfp_schema.json", payload)
    for path in legacy_matches:
        if path.name != "lfp_schema.json":
            path.unlink()


def rename_binary_stems() -> None:
    _rename_mat("spikeTimes_data*.mat", "spikeTimes_data.mat")
    _rename_mat("spikeWaves_data*.mat", "spikeWaves_data.mat")
    _rename_mat("spikeWaves_timestamps*.mat", "spikeWaves_timestamps.mat")
    _rename_mat("lfp_timestamps*.mat", "lfp_timestamps.mat")
    matches = list(SESSION.glob("lfp_data*.mat"))
    if matches:
        _rename_mat("lfp_data*.mat", "lfp_data.mat")


def transpose_lfp_to_time_channels() -> None:
    """Rewrite LFP array to canonical (n_time, n_channels); prefer .npz."""
    import numpy as np

    from src.data_io import load_numeric_array, save_numeric_array_npz

    candidates = list(SESSION.glob("lfp_data.mat")) + list(SESSION.glob("lfp_data.npz"))
    if not candidates:
        print("  skip LFP transpose (no lfp_data.mat/.npz)")
        return
    source = candidates[0]
    print(f"  loading {source.name} …")
    data = load_numeric_array(source)
    if data.ndim != 2:
        raise ValueError(f"Unexpected LFP ndim {data.ndim} in {source}")
    n0, n1 = data.shape
    # channels × time → time × channels when first axis looks like channel count
    if n0 < n1 and n0 <= 4096:
        print(f"  transpose {data.shape} -> ({n1}, {n0})")
        data = np.ascontiguousarray(data.T)
    else:
        print(f"  already time×channels-like shape {data.shape}")

    dest = SESSION / "lfp_data.npz"
    print(f"  writing {dest.name} shape={data.shape} …")
    save_numeric_array_npz(dest, data.astype(np.float64, copy=False), array_key="data")
    if source.suffix.lower() == ".mat" and source.exists():
        source.unlink()
        print(f"  removed legacy {source.name}")
    # Align schema sizes to written array
    schema_path = SESSION / "lfp_schema.json"
    schema = {
        "data_unit_measurement": "amplitude__V",
        "sample_frequency__Hz": 2500.0,
        "probe": "Neuropixel1.0",
        "X_dim": "time",
        "Y_dim": "channel",
        "X_size": int(data.shape[0]),
        "Y_size": int(data.shape[1]),
    }
    if schema_path.exists():
        with schema_path.open(encoding="utf-8") as handle:
            old = json.load(handle)
        schema["sample_frequency__Hz"] = float(old.get("sample_frequency__Hz") or 2500.0)
        schema["probe"] = old.get("probe", "Neuropixel1.0")
        schema["data_unit_measurement"] = old.get("data_unit_measurement", "amplitude__V")
    _write_json(schema_path, schema)
    print(f"  wrote lfp_schema.json X_size={schema['X_size']} Y_size={schema['Y_size']}")


def clear_age_nan_in_session_info() -> None:
    """Replace age__days token NaN with empty cell in existing sessionInfo CSVs."""
    paths = [
        DATASET / f"sessionInfo_{DATASET_ID}.csv",
        SESSION / "sessionInfo_single_session.csv",
    ]
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
            fieldnames = list(rows[0].keys()) if rows else []
        changed = False
        for row in rows:
            if str(row.get("age__days", "")).strip().upper() in {"NAN", "U", "UNKNOWN", "NA"}:
                row["age__days"] = ""
                changed = True
        if changed and fieldnames:
            _write_csv(path, fieldnames, rows)
            print(f"  cleared age__days NaN/U in {path.name}")


def main() -> None:
    if not SESSION.is_dir():
        raise SystemExit(f"Missing session dir: {SESSION}")
    legacy_info = DATASET / "sessionsInfo_SeqBias_AstroBlock_NPX_examp.csv"
    if legacy_info.exists():
        print("Rewriting sessionInfo…")
        rewrite_session_info()
    else:
        print("Clearing age__days placeholders in existing sessionInfo…")
        clear_age_nan_in_session_info()
    legacy_trial = SESSION / "trialInfo_SeqBias_AstroBlock_NPX_examp_AstroDREADD25_20240702.csv"
    if legacy_trial.exists():
        print("Rewriting trialInfo…")
        rewrite_trial_info()
    if list(SESSION.glob("spikeTimes_metadata_*.csv")) or not (SESSION / "spikeTimes_metadata.csv").exists():
        print("Rewriting metadata CSVs…")
        rewrite_spike_times_metadata()
        rewrite_spike_waves_metadata()
        rewrite_lfp_metadata()
    print("Rewriting schemas…")
    rewrite_schemas()
    print("Renaming binary stems…")
    rename_binary_stems()
    print("Transposing LFP to time×channels…")
    transpose_lfp_to_time_channels()
    print("Done.")


if __name__ == "__main__":
    main()
