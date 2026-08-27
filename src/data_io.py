"""Load SurLab array and metadata files.

Demo archives may use legacy metadata/schema keys; a small alias map normalizes
on read for spikeTimes only. Canonical names in sur_nwb_conversion_table.csv remain the
spec for new exports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


def load_json(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_numeric_array(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npz":
        archive = np.load(path, allow_pickle=True)
        if len(archive.files) == 1:
            return np.asarray(archive[archive.files[0]])
        for preferred_key in ("data", "timestamps", "spikeTimes"):
            if preferred_key in archive.files:
                return np.asarray(archive[preferred_key])
        return np.asarray(archive[archive.files[0]])

    import scipy.io as sio

    mat = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
    for key, value in mat.items():
        if not key.startswith("_"):
            return np.asarray(value)
    raise ValueError(f"No array variable found in {path}")


def squeeze_object_array(array: np.ndarray) -> List[np.ndarray]:
    """Convert MATLAB cell/object layout to a list of 1D float arrays."""
    flat = np.asarray(array).ravel()
    series: List[np.ndarray] = []
    for item in flat:
        values = np.asarray(item, dtype=float).ravel()
        series.append(values)
    return series


def load_spike_times_by_unit(path: Path) -> List[np.ndarray]:
    raw = load_numeric_array(path)
    if raw.dtype == object or raw.ndim >= 1:
        return squeeze_object_array(raw)
    return [np.asarray(raw, dtype=float).ravel()]


def normalize_schema_keys(schema: Dict[str, object]) -> Dict[str, object]:
    """Map common legacy schema keys to canonical table field names."""
    aliases = {
        "sampFreq": "sample_frequency__Hz",
        "data_unit_meas": "data_unit_measurement",
    }
    normalized = dict(schema)
    for legacy_key, canonical_key in aliases.items():
        if canonical_key not in normalized and legacy_key in normalized:
            normalized[canonical_key] = normalized[legacy_key]
    return normalized


def normalize_metadata_row(row: Dict[str, str]) -> Dict[str, str]:
    aliases = {
        "spikesorting_ID": "spike_sorting_ID",
        "depth": "depth__um",
    }
    normalized = dict(row)
    for legacy_key, canonical_key in aliases.items():
        if canonical_key not in normalized and legacy_key in normalized:
            normalized[canonical_key] = normalized[legacy_key]
    return normalized


def save_spike_times_npz(path: Path, spike_series: List[np.ndarray], array_key: str = "spikeTimes") -> None:
    """Write SurLab spikeTimes layout: (1, n_units) object array of 1D float arrays."""
    path.parent.mkdir(parents=True, exist_ok=True)
    unit_count = len(spike_series)
    container = np.empty((1, unit_count), dtype=object)
    for index, values in enumerate(spike_series):
        container[0, index] = np.asarray(values, dtype=float).ravel()
    np.savez(path, **{array_key: container})


def save_json_file(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
