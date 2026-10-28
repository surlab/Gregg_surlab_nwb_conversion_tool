"""Load SurLab array and metadata files.

Demo archives may use legacy metadata/schema keys; a small alias map normalizes
on read for spikeTimes only. Canonical names in sur_nwb_conversion_table.csv remain the
spec for new exports.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

_COORDINATE_NUMBER_PATTERN = re.compile(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_MATLAB_SKIP_KEYS = {"#refs#", "#subsystem#"}
_PREFERRED_ARRAY_KEYS = ("data", "timestamps", "spikeTimes")


def load_json(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_numeric_array(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npz":
        archive = np.load(path, allow_pickle=True)
        if len(archive.files) == 1:
            return np.asarray(archive[archive.files[0]])
        for preferred_key in _PREFERRED_ARRAY_KEYS:
            if preferred_key in archive.files:
                return np.asarray(archive[preferred_key])
        return np.asarray(archive[archive.files[0]])
    return _load_matlab_array(path)


def _first_named_array(mapping: Dict[str, object], skip_prefix: str = "_") -> np.ndarray:
    for preferred_key in _PREFERRED_ARRAY_KEYS:
        if preferred_key in mapping:
            return np.asarray(mapping[preferred_key])
    for key, value in mapping.items():
        if skip_prefix and str(key).startswith(skip_prefix):
            continue
        if str(key) in _MATLAB_SKIP_KEYS:
            continue
        return np.asarray(value)
    raise ValueError("No array variable found")


def _load_matlab_array(path: Path) -> np.ndarray:
    """Load a .mat file (v5 via scipy, v7.3/HDF5 via h5py)."""
    import scipy.io as sio

    try:
        mat = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
    except NotImplementedError:
        logger.info("MATLAB v7.3 (HDF5) file; loading with h5py: %s", path)
        return load_matlab_v73_array(path)
    try:
        return _first_named_array(mat, skip_prefix="_")
    except ValueError as exc:
        raise ValueError(f"No array variable found in {path}") from exc


def load_matlab_v73_array(path: Path) -> np.ndarray:
    """Read a MATLAB v7.3 MAT-file (HDF5). Requires h5py.

    Numeric arrays are transposed to MATLAB shape (HDF5 stores Fortran order).
    Cell arrays of numeric vectors become an object array of 1-D arrays.
    """
    try:
        import h5py
    except ImportError as exc:
        raise ImportError(
            f"{path} is a MATLAB v7.3 (HDF5) .mat file. Install h5py to load it: pip install h5py"
        ) from exc

    with h5py.File(path, "r") as handle:
        return _h5_first_array(handle, handle)


def _h5_first_array(group, root) -> np.ndarray:
    import h5py

    for preferred_key in _PREFERRED_ARRAY_KEYS:
        if preferred_key in group:
            return _h5_decode(root, group[preferred_key])
    for key in group.keys():
        if key in _MATLAB_SKIP_KEYS:
            continue
        return _h5_decode(root, group[key])
    raise ValueError(f"No array variable found in MATLAB v7.3 file {group.name}")


def _h5_decode(root, obj) -> np.ndarray:
    import h5py

    if isinstance(obj, h5py.Group):
        return _h5_first_array(obj, root)
    if not isinstance(obj, h5py.Dataset):
        return np.asarray(obj)

    if h5py.check_dtype(ref=obj.dtype) is not None:
        refs = np.array(obj[()])
        cells = []
        for ref in np.atleast_1d(refs).ravel():
            if ref:
                cells.append(np.asarray(_h5_decode(root, root[ref])).ravel())
            else:
                cells.append(np.asarray([], dtype=float))
        container = np.empty(len(cells), dtype=object)
        for index, values in enumerate(cells):
            container[index] = values
        if refs.ndim >= 2:
            container = container.reshape(tuple(reversed(refs.shape))).T
        return np.squeeze(container)

    values = np.asarray(obj[()])
    if values.ndim >= 2:
        values = values.T
    return np.squeeze(values)


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


def parse_coordinate_value(raw: object) -> Union[float, str]:
    """Parse a coordinate cell from metadata CSV (numeric or numeric string).

    Accepts plain floats (``405.0``), numeric strings (``"405.0"``), or strings
    with a leading number (``"405 px"``). Returns NaN for empty/NA tokens.
    """
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "na", "n/a"}:
        return float("nan")
    match = _COORDINATE_NUMBER_PATTERN.match(text)
    if match:
        return float(match.group())
    return text


def parse_coordinate_list(raw: object) -> List[float]:
    """Parse a 1-D list of coordinates from a metadata CSV cell.

    Accepts a single scalar (``405.0``), space/comma-separated lists
    (``2 3 4 2 3 4``), or JSON/bracket arrays. Returns empty list when absent.
    """
    import math

    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        values: List[float] = []
        for item in raw:
            parsed = parse_coordinate_value(item)
            if isinstance(parsed, float) and not math.isnan(parsed):
                values.append(parsed)
        return values

    text = str(raw).strip()
    if not text or text.lower() in {"nan", "na", "n/a"}:
        return []

    if text.startswith("["):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, list):
                return parse_coordinate_list(loaded)
        except json.JSONDecodeError:
            inner = text.strip("[]").strip()
            if inner:
                return parse_coordinate_list(inner)

    parts = [part for part in re.split(r"[\s,;]+", text) if part.strip()]
    if len(parts) > 1:
        values = []
        for part in parts:
            parsed = parse_coordinate_value(part)
            if isinstance(parsed, float) and not math.isnan(parsed):
                values.append(parsed)
        return values

    parsed = parse_coordinate_value(text)
    if isinstance(parsed, float) and not math.isnan(parsed):
        return [parsed]
    return []


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
        "roi_x_coordinate": "roi_x_coordinates",
        "roi_y_coordinate": "roi_y_coordinates",
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


def save_numeric_array_npz(path: Path, array: np.ndarray, array_key: str = "data") -> None:
    """Write one numeric array under ``array_key`` (SurLab .npz convention)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **{array_key: np.asarray(array)})
