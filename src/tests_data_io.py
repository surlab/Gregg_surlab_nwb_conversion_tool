"""Tests for MATLAB / npz array loading."""

from pathlib import Path

import numpy as np
import pytest

from src.data_io import load_matlab_v73_array, load_numeric_array


def test_load_matlab_v73_transposes_to_matlab_shape(tmp_path: Path) -> None:
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "lfp_data.mat"
    stored = np.arange(8, dtype=float).reshape(2, 4)  # HDF5 / Fortran layout
    with h5py.File(path, "w") as handle:
        handle.create_dataset("data", data=stored)

    loaded = load_matlab_v73_array(path)
    np.testing.assert_array_equal(loaded, stored.T)


def test_load_numeric_array_falls_back_to_v73(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "lfp_timestamps.mat"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("timestamps", data=np.arange(5, dtype=float))

    def _raise_v73(*_args, **_kwargs):
        raise NotImplementedError("Please use HDF reader for matlab v7.3 files, e.g. h5py")

    monkeypatch.setattr("scipy.io.loadmat", _raise_v73)
    loaded = load_numeric_array(path)
    np.testing.assert_array_equal(loaded, np.arange(5, dtype=float))
